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
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Optional, Tuple, Union
from streamer import __version__
from streamer.cloud_node import CloudNode
from streamer.bitrate_configuration import BitrateConfig, AudioChannelLayout, VideoResolution
from streamer.external_command_node import ExternalCommandNode
from streamer import autodetect
from streamer.input_configuration import InputConfig, InputType, MediaType, Input
from streamer.node_base import NodeBase, ProcessStatus
from streamer.output_stream import AudioOutputStream, OutputStream, TextOutputStream, VideoOutputStream
from streamer.packager_node import PackagerNode
from streamer.pipeline_configuration import ManifestFormat, PipelineConfig, StreamingMode
from streamer.transcoder_node import TranscoderNode
from streamer.periodconcat_node import PeriodConcatNode
import streamer.subprocessWindowsPatch  # side-effects only
from streamer.util import is_url
from streamer.pipe import Pipe


class ControllerNode(object):
  """Controls all other nodes and manages shared resources."""

  def __init__(self) -> None:
    global_temp_dir = tempfile.gettempdir()

    # The docs state that if any of prefix, suffix, or dir are specified, all
    # must be specified (and not None).  Create a temp dir of our own, inside
    # the global temp dir, and with a name that indicates who made it.
    self._temp_dir: str = tempfile.mkdtemp(
        dir=global_temp_dir, prefix='shaka-live-', suffix='')

    self._nodes: List[NodeBase] = []

  def __del__(self) -> None:
    # Clean up named pipes by removing the temp directory we placed them in.
    shutil.rmtree(self._temp_dir)

  def __enter__(self) -> 'ControllerNode':
    return self

  def __exit__(self, *unused_args) -> None:
    self.stop()

  def start(self, output_location: str,
            input_config_dict: Dict[str, Any],
            pipeline_config_dict: Dict[str, Any],
            bitrate_config_dict: Dict[Any, Any] = {},
            bucket_url: Union[str, None] = None,
            check_deps: bool = True,
            use_hermetic: bool = True) -> 'ControllerNode':
    """Create and start all other nodes.

    :raises: `RuntimeError` if the controller has already started.
    :raises: :class:`streamer.configuration.ConfigError` if the configuration is
             invalid.
    """

    if use_hermetic:
      try:
        import streamer_binaries # type: ignore
      except ImportError as ex:
        # If the package couldn't be imported.
        raise RuntimeError(
            'shaka-streamer-binaries was not found.\n'
            '  Install it with `pip install shaka-streamer-binaries`.\n'
            '  Alternatively, use the `--use-system-binaries` option if you '
            'want to use the system wide binaries of ffmpeg/ffprobe/packager.'
        ) from None

    if self._nodes:
      raise RuntimeError('Controller already started!')

    if check_deps:
      # If we are using the hermetic binaries, check the module version.  We
      # must match on the first two digits, but the last one can vary between
      # the two modules.
      if use_hermetic:
        def shorten_version(version: str) -> str:
          """Shorten a version string to the first two digits."""
          components = version.split('.')
          return '.'.join(components[0:2])

        def next_short_version(version: str) -> str:
          """Shorten a version to two digits, then increase the second."""
          components = version.split('.')
          components[1] = str(int(components[1]) + 1)
          return '.'.join(components[0:2])

        streamer_short_version = shorten_version(__version__)
        streamer_binaries_short_version = shorten_version(
            streamer_binaries.__version__)

        if streamer_binaries_short_version != streamer_short_version:
          # This is the recommended install command.  It installs the most
          # recent version of the binary package that matches the current
          # version of streamer itself.  This is much easier to do in nodejs
          # dependencies, because you can use a specifier like "1.2.x", but in
          # Python, you have to use a specifier like ">=1.2,<1.3".
          pip_command = "pip3 install 'shaka-streamer-binaries>={},<{}'".format(
              streamer_short_version, next_short_version(__version__))

          raise VersionError(
              'shaka-streamer-binaries', 'version does not match',
              streamer_short_version,
              exact_match=True,
              addendum='Install with: {}'.format(pip_command))
      else:
        # Check that ffmpeg version is 4.1 or above.
        _check_command_version('FFmpeg', ['ffmpeg', '-version'], (4, 1))

        # Check that ffprobe version (used for autodetect features) is 4.1 or
        # above.
        _check_command_version('ffprobe', ['ffprobe', '-version'], (4, 1))

        # Check that Shaka Packager version is 2.6.0 or above.
        _check_command_version('Shaka Packager', ['packager', '-version'],
                               (2, 6, 0))

      if bucket_url:
        # Check that the Google Cloud SDK is at least v212, which introduced
        # gsutil 4.33 with an important rsync bug fix.
        # https://cloud.google.com/sdk/docs/release-notes
        # https://github.com/GoogleCloudPlatform/gsutil/blob/master/CHANGES.md
        # This is only required if the user asked for upload to cloud storage.
        _check_command_version('Google Cloud SDK', ['gcloud', '--version'],
                               (212, 0, 0))


    if bucket_url:
      # If using cloud storage, make sure the user is logged in and can access
      # the destination, independent of the version check above.
      CloudNode.check_access(bucket_url)

    self.hermetic_ffmpeg: Optional[str] = None
    self.hermetic_packager: Optional[str] = None
    if use_hermetic:
      self.hermetic_ffmpeg = streamer_binaries.ffmpeg
      self.hermetic_packager = streamer_binaries.packager
      autodetect.hermetic_ffprobe = streamer_binaries.ffprobe

    # Define resolutions and bitrates before parsing other configs.
    bitrate_config = BitrateConfig(bitrate_config_dict)

    # Now that the definitions have been parsed, register the maps of valid
    # resolutions and channel layouts so that InputConfig and PipelineConfig
    # can be validated accordingly.
    VideoResolution.set_map(bitrate_config.video_resolutions)
    AudioChannelLayout.set_map(bitrate_config.audio_channel_layouts)

    self._input_config = InputConfig(input_config_dict)
    self._pipeline_config = PipelineConfig(pipeline_config_dict)

    if not is_url(output_location):
      # Check if the directory for outputted Packager files exists, and if it
      # does, delete it and remake a new one.
      if os.path.exists(output_location):
        shutil.rmtree(output_location)
      os.mkdir(output_location)
    else:
      # Check some restrictions and other details on HTTP output.
      if not self._pipeline_config.segment_per_file:
        raise RuntimeError(
            'For HTTP PUT uploads, the pipeline segment_per_file setting ' +
            'must be set to True!')

      if bucket_url:
        raise RuntimeError(
            'Cloud bucket upload is incompatible with HTTP PUT support.')

      if self._input_config.multiperiod_inputs_list:
        # TODO: Edit Multiperiod input list implementation to support HTTP outputs
        raise RuntimeError(
            'Multiperiod input list support is incompatible with HTTP outputs.')

    if self._pipeline_config.low_latency_dash_mode:
      # Check some restrictions on LL-DASH packaging.
      if ManifestFormat.DASH not in self._pipeline_config.manifest_format:
        raise RuntimeError(
            'low_latency_dash_mode is only compatible with DASH ouputs. ' +
            'manifest_format must include DASH')

      if not self._pipeline_config.utc_timings:
        raise RuntimeError(
            'For low_latency_dash_mode, the utc_timings must be set.')

    # Note that we remove the trailing slash from the output location, because
    # otherwise GCS would create a subdirectory whose name is "".
    output_location = output_location.rstrip('/')

    if self._input_config.inputs:
      # InputConfig contains inputs only.
      self._append_nodes_for_inputs_list(self._input_config.inputs,
                                         output_location)
    else:
      # InputConfig contains multiperiod_inputs_list only.
      # Create one Transcoder node and one Packager node for each period.
      for i, singleperiod in enumerate(self._input_config.multiperiod_inputs_list):
        sub_dir_name = 'period_' + str(i + 1)
        self._append_nodes_for_inputs_list(singleperiod.inputs,
                                           output_location,
                                           sub_dir_name, i + 1)

      if self._pipeline_config.streaming_mode == StreamingMode.VOD:
        packager_nodes = [node for node in self._nodes if isinstance(node, PackagerNode)]
        self._nodes.append(PeriodConcatNode(
          self._pipeline_config,
          packager_nodes,
          output_location))

    if bucket_url:
      cloud_temp_dir = os.path.join(self._temp_dir, 'cloud')
      os.mkdir(cloud_temp_dir)

      packager_nodes = [node for node in self._nodes if isinstance(node, PackagerNode)]
      self._nodes.append(CloudNode(output_location,
                                   bucket_url,
                                   cloud_temp_dir,
                                   packager_nodes,
                                   self.is_vod()))

    for node in self._nodes:
      node.start()

    return self

  def _append_nodes_for_inputs_list(self, inputs: List[Input],
                                    output_location: str,
                                    period_dir: Optional[str] = None,
                                    index: int = 0) -> None:
    """A common method that creates Transcoder and Packager nodes for a list of Inputs passed to it.

    Args:
      inputs (List[Input]): A list of Input streams.
      output_location (str): A path were the packager will write outputs in.
      period_dir (Optional[str]): A subdirectory name where a single period will be outputted to.
      If passed, this indicates that inputs argument is one period in a list of periods.
      index (int): The index of the current Transcoder/Packager nodes.
    """

    outputs: List[OutputStream] = []
    for input in inputs:
      # External command inputs need to be processed by an additional node
      # before being transcoded.  In this case, the input doesn't have a
      # filename that FFmpeg can read, so we generate an intermediate pipe for
      # that node to write to.  TranscoderNode will then instruct FFmpeg to
      # read from that pipe for this input.
      if input.input_type == InputType.EXTERNAL_COMMAND:
        command_output = Pipe.create_ipc_pipe(self._temp_dir)
        self._nodes.append(ExternalCommandNode(
            input.name, command_output.write_end()))
        # reset the name of the input to be the output pipe path - which the
        # transcoder node will read from - instead of a shell command.
        input.reset_name(command_output.read_end())

      if input.media_type == MediaType.AUDIO:
        for audio_codec in self._pipeline_config.audio_codecs:
          for output_channel_layout in self._pipeline_config.get_channel_layouts():
            # We won't upmix a lower channel count input to a higher one.
            # Skip channel counts greater than the input channel count.
            if input.get_channel_layout() < output_channel_layout:
              continue

            outputs.append(AudioOutputStream(input,
                                             self._temp_dir,
                                             audio_codec,
                                             output_channel_layout))

      elif input.media_type == MediaType.VIDEO:
        for video_codec in self._pipeline_config.video_codecs:
          for output_resolution in self._pipeline_config.get_resolutions():
            # Only going to output lower or equal resolution videos.
            # Upscaling is costly and does not do anything.
            if input.get_resolution() < output_resolution:
              continue

            outputs.append(VideoOutputStream(input,
                                             self._temp_dir,
                                             video_codec,
                                             output_resolution))

      elif input.media_type == MediaType.TEXT:
        if input.name.endswith('.vtt') or input.name.endswith('.ttml'):
          # If the input is a VTT or TTML file, pass it directly to the packager
          # without any intermediate processing or any named pipe.
          # TODO: Test TTML inputs
          skip_transcoding = True  # Bypass transcoder
        else:
          # Otherwise, the input is something like an mkv file with text tracks
          # in it.  These will be extracted by the transcoder and passed in a
          # pipe to the packager.
          skip_transcoding = False

        outputs.append(TextOutputStream(input,
                                        self._temp_dir,
                                        skip_transcoding))

    self._nodes.append(TranscoderNode(inputs,
                                      self._pipeline_config,
                                      outputs,
                                      index,
                                      self.hermetic_ffmpeg))
    
    # If the inputs list was a period in multiperiod_inputs_list, create a nested directory
    # and put that period in it.
    if period_dir:
      output_location = os.path.join(output_location, period_dir)
      os.mkdir(output_location)

    self._nodes.append(PackagerNode(self._pipeline_config,
                                    output_location,
                                    outputs,
                                    index,
                                    self.hermetic_packager))

  def check_status(self) -> ProcessStatus:
    """Checks the status of all the nodes.

    If one node is errored, this returns Errored; otherwise if one node is running,
    this returns Running; this only returns Finished if all nodes are finished.
    If there are no nodes, this returns Finished.
    """
    if not self._nodes:
      return ProcessStatus.Finished

    value = max(node.check_status().value for node in self._nodes)
    return ProcessStatus(value)

  def stop(self) -> None:
    """Stop all nodes."""
    status = self.check_status()
    for node in self._nodes:
      node.stop(status)
    self._nodes = []

  def is_vod(self) -> bool:
    """Returns True if the pipeline is running in VOD mode.

    :rtype: bool
    """

    return self._pipeline_config.streaming_mode == StreamingMode.VOD

  def is_low_latency_dash_mode(self) -> bool:
    """Returns True if the pipeline is running in LL-DASH mode.

    :rtype: bool
    """

    return self._pipeline_config.low_latency_dash_mode

class VersionError(Exception):
  """A version error for one of Shaka Streamer's external dependencies.

  Raised when a dependency (like FFmpeg) is missing or not new enough to work
  with Shaka Streamer.  See also :doc:`prerequisites`.
  """

  def __init__(self,
               name: str,
               problem: str,
               required_version: str,
               exact_match: bool = False,
               addendum: str = ''):
    or_higher = '' if exact_match else ' or higher'
    message = '{0} {1}! Please install version {2}{3} of {0}.'.format(
        name, problem, required_version, or_higher)
    if addendum:
      message += '\n' + addendum
    super().__init__(message)

def _check_command_version(name: str,
                           command: List[str],
                           minimum_version: Tuple[int, ...]) -> None:
  minimum_version_string = '.'.join(str(x) for x in minimum_version)

  try:
    version_string = str(subprocess.check_output(command))
  except (subprocess.CalledProcessError, OSError) as e:
    if isinstance(e, subprocess.CalledProcessError):
      print(e.stdout, file=sys.stderr)
    raise VersionError(name, 'not found', minimum_version_string) from None

  # Matches two or more numbers (one or more digits each) separated by dots.
  # For example: 4.1.3 or 7.2 or 216.999.8675309
  version_match = re.search(r'[0-9]+(?:\.[0-9]+)+', version_string)

  if version_match:
    version = tuple([int(piece) for piece in version_match.group(0).split('.')])
    if version < minimum_version:
      raise VersionError(name, 'out of date', minimum_version_string)
  else:
    raise RuntimeError(name + ' version could not be parsed!')
