# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Top-level module API.

If you'd like to import Shaka Streamer as a Python module and build it into
your own application, this is the top-level API you can use for that.  You may
also want to look at the source code to the command-line front end script
`shaka-streamer`.
"""


import os
import re
import shutil
import string
import subprocess
import tempfile
import uuid

from . import bitrate_configuration
from . import cloud_node
from . import external_command_node
from . import input_configuration
from . import node_base
from . import output_stream
from . import packager_node
from . import pipeline_configuration
from . import transcoder_node

# Alias a few classes to avoid repeating namespaces later.
BitrateConfig = bitrate_configuration.BitrateConfig

InputConfig = input_configuration.InputConfig
InputType = input_configuration.InputType
MediaType = input_configuration.MediaType

AudioOutputStream = output_stream.AudioOutputStream
TextOutputStream = output_stream.TextOutputStream
VideoOutputStream = output_stream.VideoOutputStream

PipelineConfig = pipeline_configuration.PipelineConfig
StreamingMode = pipeline_configuration.StreamingMode


class ControllerNode(object):
  """Controls all other nodes and manages shared resources."""

  def __init__(self):
    global_temp_dir = tempfile.gettempdir()

    # The docs state that if any of prefix, suffix, or dir are specified, all
    # must be specified (and not None).  Create a temp dir of our own, inside
    # the global temp dir, and with a name that indicates who made it.
    self._temp_dir = tempfile.mkdtemp(
        dir=global_temp_dir, prefix='shaka-live-', suffix='')

    self._nodes = []

  def __del__(self):
    # Clean up named pipes by removing the temp directory we placed them in.
    shutil.rmtree(self._temp_dir)

  def __enter__(self):
    return self

  def __exit__(self, *unused_args):
    self.stop()

  def _create_pipe(self):
    """Create a uniquely-named named pipe in the node's temp directory.

    Raises:
      RuntimeError: If the platform doesn't have mkfifo.
    Returns:
      The path to the named pipe, as a string.
    """

    # TODO(#8): mkfifo only works on Unix.  We would need a special case for a
    # Windows port some day.

    if not hasattr(os, 'mkfifo'):
      raise RuntimeError('Platform not supported due to lack of mkfifo')

    # Since the tempfile module creates actual files, use uuid to generate a
    # filename, then call mkfifo to create the named pipe.
    unique_name = str(uuid.uuid4())
    path = os.path.join(self._temp_dir, unique_name)

    readable_by_owner_only = 0o600  # Unix permission bits
    os.mkfifo(path, mode=readable_by_owner_only)

    return path

  def start(self, output_dir,
            input_config_dict, pipeline_config_dict,
            bitrate_config_dict={},
            bucket_url=None):
    """Create and start all other nodes.

    :raises: `RuntimeError` if the controller has already started.
    :raises: :class:`streamer.configuration.ConfigError` if the configuration is
             invalid.
    """

    if self._nodes:
      raise RuntimeError('Controller already started!')

    # Check that ffmpeg version is 4.1 or above.
    _check_version('FFmpeg', ['ffmpeg', '-version'], (4, 1))

    # Check that ffprobe version (used for autodetect features) is 4.1 or above.
    _check_version('ffprobe', ['ffprobe', '-version'], (4, 1))

    # Check that Shaka Packager version is 2.1 or above.
    _check_version('Shaka Packager', ['packager', '-version'], (2, 1))

    # Define resolutions and bitrates before parsing other configs.
    bitrate_config = BitrateConfig(bitrate_config_dict)

    # Now that the definitions have been parsed, register the maps of valid
    # resolutions and channel layouts so that InputConfig and PipelineConfig
    # can be validated accordingly.
    bitrate_configuration.Resolution.set_map(bitrate_config.video_resolutions)
    bitrate_configuration.ChannelLayout.set_map(
        bitrate_config.audio_channel_layouts)

    input_config = InputConfig(input_config_dict)
    pipeline_config = PipelineConfig(pipeline_config_dict)
    self._pipeline_config = pipeline_config

    outputs = []
    for input in input_config.inputs:
      # External command inputs need to be processed by an additional node
      # before being transcoded.  In this case, the input doesn't have a
      # filename that FFmpeg can read, so we generate an intermediate pipe for
      # that node to write to.  TranscoderNode will then instruct FFmpeg to
      # read from that pipe for this input.
      if input.input_type == InputType.EXTERNAL_COMMAND:
        command_output = self._create_pipe()
        self._nodes.append(external_command_node.ExternalCommandNode(
            input.name, command_output))
        input.set_pipe(command_output)

      if input.media_type == MediaType.AUDIO:
        for codec in pipeline_config.audio_codecs:
          outputs.append(AudioOutputStream(self._create_pipe(),
                                           input,
                                           codec,
                                           pipeline_config.channels))

      elif input.media_type == MediaType.VIDEO:
        for codec in pipeline_config.video_codecs:
          for output_resolution in pipeline_config.resolutions:
            # Only going to output lower or equal resolution videos.
            # Upscaling is costly and does not do anything.
            if input.resolution < output_resolution:
              continue

            outputs.append(VideoOutputStream(self._create_pipe(),
                                             input,
                                             codec,
                                             output_resolution))

      elif input.media_type == MediaType.TEXT:
        outputs.append(TextOutputStream(input))

    self._nodes.append(transcoder_node.TranscoderNode(input_config,
                                                      pipeline_config,
                                                      outputs))

    self._nodes.append(packager_node.PackagerNode(pipeline_config,
                                                  output_dir,
                                                  outputs))

    if bucket_url:
      cloud_temp_dir = os.path.join(self._temp_dir, 'cloud')
      os.mkdir(cloud_temp_dir)

      self._nodes.append(cloud_node.CloudNode(output_dir,
                                              bucket_url,
                                              cloud_temp_dir,
                                              self.is_vod()))

    for node in self._nodes:
      node.start()
    return self

  def check_status(self):
    """Checks the status of all the nodes.

    :rtype: streamer.node_base.ProcessStatus

    If one node is errored, this returns Errored; otherwise if one node is
    finished, this returns Finished; this only returns Running if all nodes are
    running.  If there are no nodes, this returns Finished.
    """
    if not self._nodes:
      return node_base.ProcessStatus.Finished

    value = max(node.check_status().value for node in self._nodes)
    return node_base.ProcessStatus(value)

  def stop(self):
    """Stop all nodes."""
    for node in self._nodes:
      node.stop()
    self._nodes = []

  def is_vod(self):
    """Returns True if the pipeline is running in VOD mode.

    :rtype: bool
    """

    return self._pipeline_config.streaming_mode == StreamingMode.VOD

class VersionError(Exception):
  """A version error for one of Shaka Streamer's external dependencies.

  Raised when a dependency (like FFmpeg) is missing or not new enough to work
  with Shaka Streamer.  See also :doc:`prerequisites`.
  """

  pass

def _check_version(name, command, minimum_version):
  min_version_string = '.'.join([str(x) for x in minimum_version])

  try:
    version_string = str(subprocess.check_output(command))
  except (subprocess.CalledProcessError, OSError) as e:
    if isinstance(e, subprocess.CalledProcessError):
      print(e.stdout, file=sys.stderr)
    raise FileNotFoundError(name + ' not installed! Please install version ' +
                            min_version_string + ' or higher of ' + name + '.')

  version_match = re.search(r'([0-9]+)\.([0-9]+)\.([0-9]+)', version_string)

  if version_match == None:
    raise VersionError(name + ' version not found in string output!')

  version = (int(version_match.group(1)), int(version_match.group(2)))
  if version < minimum_version:
    raise VersionError(name + ' not installed! Please install version ' +
                       min_version_string + ' or higher of ' + name + '.')
