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

"""Controls other modules and shared resources.

This is the main module, which instantiates and starts other modules, and which
manages shared resources like named pipes."""

import os
import re
import shutil
import string
import subprocess
import tempfile
import uuid

from . import input_configuration
from . import loop_input_node
from . import metadata
from . import packager_node
from . import pipeline_configuration
from . import transcoder_node

class VersionError(Exception):
  """Raised when a version is not new enough to work with Shaka Streamer."""
  pass

class ControllerNode(object):

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

  def _create_pipe(self):
    """Create a uniquely-named named pipe in the node's temp directory.

    Raises:
      RuntimeError: If the platform doesn't have mkfifo.
    Returns:
      The path to the named pipe, as a string.
    """

    # TODO: mkfifo only works on Unix.  We would need a special case for a
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

  def start(self, output_dir, input_config_dict, pipeline_config_dict, bucket_url=None):
    """Create and start all other nodes."""
    if self._nodes:
      raise RuntimeError('Controller already started!')

    # Check that ffmpeg version is 4.1 or above.
    check_version('FFmpeg', ['ffmpeg', '-version'], (4, 1))

    # Check that Shaka Packager version is 2.1 or above.
    check_version('Packager', ['packager', '-version'], (2, 1))

    input_config = input_configuration.InputConfig(input_config_dict)

    pipeline_config = pipeline_configuration.PipelineConfig(
        pipeline_config_dict)
    self.pipeline_config = pipeline_config

    # Some inputs get processed by Shaka Streamer before being transcoded, so
    # this array will keep track of the input paths to pass to the transcoder.
    # Some will be input files/devices, while others will be named pipes.
    # TODO(joeyparrish): put input paths into input_config.inputs
    input_paths = []

    for i in input_config.inputs:
      if pipeline_config.mode == 'live':
        i.check_input_type()
        if i.get_input_type() == 'looped_file':
          loop_output = self._create_pipe()
          input_node = loop_input_node.LoopInputNode(i.get_name(), loop_output)
          self._nodes.append(input_node)
          input_paths.append(loop_output)

        elif i.get_input_type() == 'raw_images':
          input_paths.append(i.get_name())

        elif i.get_input_type() == 'webcam':
          input_paths.append(i.get_name())

      elif pipeline_config.mode == 'vod':
        input_paths.append(i.get_name())

    assert len(input_config.inputs) == len(input_paths)

    media_outputs = {
        'audio': [],
        'video': [],
        'text': [],
    }

    # Sorting the media by type.  So all the audio streams are in one list,
    # all the video stream are in one list, etc.
    for media in input_config.inputs:
      media.check_entry()
      media_type = media.get_media_type()
      media_outputs[media_type].append(media)

    audio_outputs = []
    for i in media_outputs['audio']:
      audio_outputs.extend(self._add_audio(i, pipeline_config.transcoder['channels'],
                                           pipeline_config.transcoder['audio_codecs']))

    video_outputs = []
    for i in media_outputs['video']:
      video_outputs.extend(self._add_video(i,
                                           pipeline_config.transcoder['resolutions'],
                                           pipeline_config.transcoder['video_codecs']))

    # Process input through a transcoder node using ffmpeg.
    ffmpeg_node = transcoder_node.TranscoderNode(input_paths,
                                                 audio_outputs,
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
      # Import the cloud node late, so that the cloud deps are optional.
      from . import cloud_node
      push_to_cloud = cloud_node.CloudNode(output_dir, bucket_url,
                                           self._temp_dir)
      self._nodes.append(push_to_cloud)

    for node in self._nodes:
      node.start()

  def is_running(self):
    """Return True if we have nodes and all of them are still running."""
    return self._nodes and all(n.is_running() for n in self._nodes)

  def stop(self):
    """Stop all nodes."""
    for node in self._nodes:
      node.stop()
    self._nodes = []

  def _add_audio(self, input, channels, codecs):
    audio_outputs = []
    language = input.get_language() or self._probe_language(input)
    for codec in codecs:
      audio_outputs.append(metadata.Metadata(self._create_pipe(),
                                             channels=channels, codec=codec,
                                             language=language))
    return audio_outputs

  def _add_video(self, input, resolutions, codecs):
    video_outputs = []
    for codec in codecs:
      hardware_encoding = False
      if codec.startswith('hw:'):
        hardware_encoding = True
        codec = codec.split(':')[1]
      in_res = input.get_resolution()
      for out_res in resolutions:
        # Only going to output lower or equal resolution videos.
        # Upscaling is costly and does not do anything.
        if (metadata.RESOLUTION_MAP[in_res] >=
            metadata.RESOLUTION_MAP[out_res]):
          video_outputs.append(metadata.Metadata(self._create_pipe(),
                                                 resolution_name=out_res,
                                                 codec=codec,
                                                 hardware=hardware_encoding))
    return video_outputs

  def _probe_language(self, input):
    # ffprobe {input}: list out metadata of input
    # -show_entries stream=index:stream_tags=language: list out tracks with
    # stream and language information
    # -select_streams {track}: Only return stream/language information for
    # specified track.
    # -of compact=p=0:nk=1: Specify no keys printed and don't print the name
    # at the beginning of each line.
    command = ['ffprobe', input.get_name(), '-show_entries',
               'stream=index:stream_tags=language', '-select_streams',
               str(input.get_track()), '-of', 'compact=p=0:nk=1']

    lang_str = subprocess.check_output(command).decode('utf-8')
    # The regex is looking for a string that is of the format number|language.
    # Once it finds a number| match, it will copy the string until the end of
    # the line.
    lang_match = re.search(r'\d+\|(.*$)', lang_str)
    if lang_match:
      return lang_match.group(1)
    return 'und'

  def is_vod(self):
    return self.pipeline_config.mode == 'vod'

def check_version(name, command, minimum_version):
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
