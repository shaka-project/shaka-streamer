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

from . import cloud_node
from . import external_command_node
from . import input_configuration
from . import metadata
from . import node_base
from . import packager_node
from . import pipeline_configuration
from . import transcoder_node

# Alias a few classes to avoid repeating namespaces later.
InputConfig = input_configuration.InputConfig
InputType = input_configuration.InputType
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

  def start(self, output_dir, input_config_dict, pipeline_config_dict,
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

    # Check that Shaka Packager version is 2.1 or above.
    _check_version('Packager', ['packager', '-version'], (2, 1))

    input_config = InputConfig(input_config_dict)
    pipeline_config = PipelineConfig(pipeline_config_dict)
    self._pipeline_config = pipeline_config

    # External command inputs need to be processed by an additional node before
    # being transcoded.  In this case, the input doesn't have a filename that
    # FFmpeg can read, so we generate an intermediate pipe for that node to
    # write to.  TranscoderNode will then instruct FFmpeg to read from that
    # pipe for this input.
    for input in input_config.inputs:
      if input.input_type == InputType.EXTERNAL_COMMAND:
        command_output = self._create_pipe()
        command_node = external_command_node.ExternalCommandNode(
            input.name, command_output)
        self._nodes.append(command_node)
        input.set_pipe(command_output)

    # TODO: This is unnecessary.  Just process each input in turn.
    media_outputs = {
        'audio': [],
        'video': [],
        'text': [],
    }

    # Sorting the media by type.  So all the audio streams are in one list,
    # all the video stream are in one list, etc.
    for media in input_config.inputs:
      media_type = media.media_type.value
      media_outputs[media_type].append(media)

    audio_outputs = []
    for i in media_outputs['audio']:
      audio_outputs.extend(self._add_audio(i,
                                           pipeline_config.channels,
                                           pipeline_config.audio_codecs))

    video_outputs = []
    for i in media_outputs['video']:
      video_outputs.extend(self._add_video(i,
                                           pipeline_config.resolutions,
                                           pipeline_config.video_codecs))

    # Process input through a transcoder node using ffmpeg.
    ffmpeg_node = transcoder_node.TranscoderNode(audio_outputs,
                                                 video_outputs,
                                                 input_config,
                                                 pipeline_config)

    self._nodes.append(ffmpeg_node)

    # Process input through a packager node using Shaka Packager.
    package_node = packager_node.PackagerNode(audio_outputs,
                                              video_outputs,
                                              media_outputs['text'],
                                              output_dir,
                                              pipeline_config)
    self._nodes.append(package_node)

    if bucket_url:
      cloud_temp_dir = os.path.join(self._temp_dir, 'cloud')
      os.mkdir(cloud_temp_dir)

      push_to_cloud = cloud_node.CloudNode(output_dir, bucket_url,
                                           cloud_temp_dir)
      self._nodes.append(push_to_cloud)

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

  def _add_audio(self, input, channels, codecs):
    audio_outputs = []
    language = input.language or self._probe_language(input)
    for codec in codecs:
      codec = codec.value
      audio_outputs.append(metadata.Metadata(self._create_pipe(),
                                             channels=channels, codec=codec,
                                             language=language))
    return audio_outputs

  def _add_video(self, input, resolutions, codecs):
    video_outputs = []
    for codec in codecs:
      codec = codec.value
      hardware_encoding = False
      if codec.startswith('hw:'):
        hardware_encoding = True
        codec = codec.split(':')[1]

      # TODO: on ingest, convert the resolution string into a value from the map
      in_res = input.resolution.value
      for out_res in resolutions:
        out_res = out_res.value
        # Only going to output lower or equal resolution videos.
        # Upscaling is costly and does not do anything.
        if (metadata.RESOLUTION_MAP[in_res] >=
            metadata.RESOLUTION_MAP[out_res]):
          video_outputs.append(metadata.Metadata(self._create_pipe(),
                                                 resolution_name=out_res,
                                                 codec=codec,
                                                 hardware=hardware_encoding))

    return video_outputs

  # TODO: Move to input_configuration
  def _probe_language(self, input):
    # ffprobe {input}: list out metadata of input
    # -show_entries stream=index:stream_tags=language: list out tracks with
    # stream and language information
    # -select_streams {track}: Only return stream/language information for
    # specified track.
    # -of compact=p=0:nk=1: Specify no keys printed and don't print the name
    # at the beginning of each line.
    command = ['ffprobe', input.name, '-show_entries',
               'stream=index:stream_tags=language', '-select_streams',
               str(input.track_num), '-of', 'compact=p=0:nk=1']

    lang_str = subprocess.check_output(
        command, stderr=subprocess.DEVNULL).decode('utf-8')
    # The regex is looking for a string that is of the format number|language.
    # Once it finds a number| match, it will copy the string until the end of
    # the line.
    lang_match = re.search(r'\d+\|(.*$)', lang_str)
    if lang_match:
      return lang_match.group(1)
    return 'und'

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
