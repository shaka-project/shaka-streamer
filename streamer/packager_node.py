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

"""A module that feeds information from two named pipes into shaka-packager."""

import os
import subprocess

from . import input_configuration
from . import node_base
from . import pipeline_configuration

# Alias a few classes to avoid repeating namespaces later.
MediaType = input_configuration.MediaType

ManifestFormat = pipeline_configuration.ManifestFormat
StreamingMode = pipeline_configuration.StreamingMode


INIT_SEGMENT = {
  MediaType.AUDIO: '{dir}/audio_{language}_{channels}c_{bitrate}_init.{format}',
  MediaType.VIDEO: '{dir}/video_{resolution_name}_{bitrate}_init.{format}',
  MediaType.TEXT: '{dir}/text_{language}_init.{format}',
}

MEDIA_SEGMENT = {
  MediaType.AUDIO: '{dir}/audio_{language}_{channels}c_{bitrate}_$Number$.{format}',
  MediaType.VIDEO: '{dir}/video_{resolution_name}_{bitrate}_$Number$.{format}',
  MediaType.TEXT: '{dir}/text_{language}_$Number$.{format}',
}

SINGLE_SEGMENT = {
  MediaType.AUDIO: '{dir}/audio_{language}_{channels}c_{bitrate}.{format}',
  MediaType.VIDEO: '{dir}/video_{resolution_name}_{bitrate}.{format}',
  MediaType.TEXT: '{dir}/text_{language}.{format}',
}

class SegmentError(Exception):
  """Raise when segment is incompatible with format."""
  pass


class PackagerNode(node_base.NodeBase):

  def __init__(self, pipeline_config, output_dir, output_streams):
    super().__init__()
    self._pipeline_config = pipeline_config
    self._output_dir = output_dir
    self._segment_dir = os.path.join(output_dir, pipeline_config.segment_folder)
    self._output_streams = output_streams

  def start(self):
    args = [
        'packager',
    ]

    args += [self._setup_stream(stream) for stream in self._output_streams]

    args += [
        # Segment duration given in seconds.
        '--segment_duration', str(self._pipeline_config.segment_size),
    ]

    if self._pipeline_config.streaming_mode == StreamingMode.LIVE:
      args += [
          # Number of seconds the user can rewind through backwards.
          '--time_shift_buffer_depth',
          str(self._pipeline_config.availability_window),
          # Number of segments preserved outside the current live window.
          '--preserved_segments_outside_live_window', '1',
          # Number of seconds of content encoded/packaged that is ahead of the
          # live edge.
          '--suggested_presentation_delay',
          str(self._pipeline_config.presentation_delay),
          # Number of seconds between manifest updates.
          '--minimum_update_period',
          str(self._pipeline_config.update_period),
      ]

    args += self._setup_manifest_format()

    if self._pipeline_config.encryption.enable:
      args += self._setup_encryption()

    stdout = None
    if self._pipeline_config.debug_logs:
      # Log by writing all Packager output to a file.  Unlike the logging
      # system in ffmpeg, this will stop any Packager output from getting to
      # the screen.
      stdout = open('PackagerNode.log', 'w')

    self._process = self._create_process(args,
                                         stderr=subprocess.STDOUT,
                                         stdout=stdout)

  def _setup_stream(self, stream):
    dict = {
        'in': stream.pipe,
        'stream': stream.type.value,
    }

    # Note: Shaka Packager will not accept 'und' as a language, but Shaka
    # Player will fill that in if the language metadata is missing from the
    # manifest/playlist.
    if stream.input.language and stream.input.language != 'und':
      dict['language'] = stream.input.language

    if self._pipeline_config.segment_per_file:
      dict['init_segment'] = stream.fill_template(
          INIT_SEGMENT[stream.type],
          dir=self._segment_dir)
      dict['segment_template'] = stream.fill_template(
          MEDIA_SEGMENT[stream.type],
          dir=self._segment_dir)
    else:
      dict['output'] = stream.fill_template(
          SINGLE_SEGMENT[stream.type],
          dir=self._segment_dir)

    # The format of this argument to Shaka Packager is a single string of
    # key=value pairs separated by commas.
    return ','.join(key + '=' + value for key, value in dict.items())

  def _setup_manifest_format(self):
    args = []
    if ManifestFormat.DASH in self._pipeline_config.manifest_format:
      if self._pipeline_config.streaming_mode == StreamingMode.VOD:
        args += [
            '--generate_static_mpd',
        ]
      args += [
          # Generate DASH manifest file.
          '--mpd_output',
          os.path.join(self._output_dir, self._pipeline_config.dash_output),
      ]
    if ManifestFormat.HLS in self._pipeline_config.manifest_format:
      if self._pipeline_config.streaming_mode == StreamingMode.LIVE:
        args += [
            '--hls_playlist_type', 'LIVE',
        ]
      else:
        args += [
            '--hls_playlist_type', 'VOD',
        ]
      args += [
          # Generate HLS playlist file(s).
          '--hls_master_playlist_output',
          os.path.join(self._output_dir, self._pipeline_config.hls_output),
      ]
    return args

  def _setup_encryption(self):
    # Sets up encryption of content.
    args = [
      '--enable_widevine_encryption',
      '--key_server_url', self._pipeline_config.encryption.key_server_url,
      '--content_id', self._pipeline_config.encryption.content_id,
      '--signer', self._pipeline_config.encryption.signer,
      '--aes_signing_key', self._pipeline_config.encryption.signing_key,
      '--aes_signing_iv', self._pipeline_config.encryption.signing_iv,
      '--protection_scheme',
      self._pipeline_config.encryption.protection_scheme.value,
      '--clear_lead', str(self._pipeline_config.encryption.clear_lead),
    ]
    return args
