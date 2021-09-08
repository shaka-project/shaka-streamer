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

from streamer.output_stream import OutputStream
from streamer.pipeline_configuration import EncryptionMode, PipelineConfig
from streamer.util import is_url
from typing import List, Optional, Union

# Alias a few classes to avoid repeating namespaces later.
ManifestFormat = pipeline_configuration.ManifestFormat
StreamingMode = pipeline_configuration.StreamingMode

class SegmentError(Exception):
  """Raise when segment is incompatible with format."""
  pass

def build_path(output_location, sub_path):
  """Handle annoying edge cases with paths for cloud upload.
  If a path has two slashes, GCS will create an intermediate directory named "".
  So we have to be careful in how we construct paths to avoid this.
  """
  # ControllerNode should have already stripped trailing slashes from the output
  # location.

  # Sometimes the segment dir is empty.  This handles that special case.
  if not sub_path:
    return output_location

  if is_url(output_location):
    # Don't use os.path.join, since URLs must use forward slashes and Streamer
    # could be used on Windows.
    return output_location + '/' + sub_path

  return os.path.join(output_location, sub_path)


class PackagerNode(node_base.PolitelyWaitOnFinish):

  def __init__(self,
               pipeline_config: PipelineConfig,
               output_location: str,
               output_streams: List[OutputStream],
               index: int,
               hermetic_packager: Optional[str]) -> None:
    super().__init__()
    self._pipeline_config: PipelineConfig = pipeline_config
    self.output_location: str = output_location
    self._segment_dir: str = build_path(
        output_location, pipeline_config.segment_folder)
    self.output_streams: List[OutputStream] = output_streams
    self._index = index
    # If a hermetic packager is passed, use it.
    self._packager = hermetic_packager or 'packager'

  def start(self) -> None:
    args = [
        self._packager,
    ]

    args += [self._setup_stream(stream) for stream in self.output_streams]

    if self._pipeline_config.quiet:
      args += [
          '--quiet',  # Only output error logs
      ]

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
          # NOTE: This must not be set below 3, or the first segment in an HLS
          # playlist may become unavailable before the playlist is updated.
          '--preserved_segments_outside_live_window', '3',
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
      packager_log_file = 'PackagerNode-' + str(self._index) + '.log'
      stdout = open(packager_log_file, 'w')

    self._process: subprocess.Popen = self._create_process(
        args,
        stderr=subprocess.STDOUT,
        stdout=stdout)

  def _setup_stream(self, stream: OutputStream) -> str:

    dict = {
        'in': stream.ipc_pipe.read_end(),
        'stream': stream.type.value,
    }

    if stream.input.skip_encryption:
      dict['skip_encryption'] = str(stream.input.skip_encryption)

    if stream.input.drm_label:
      dict['drm_label'] = stream.input.drm_label

    # Note: Shaka Packager will not accept 'und' as a language, but Shaka
    # Player will fill that in if the language metadata is missing from the
    # manifest/playlist.
    if stream.input.language and stream.input.language != 'und':
      dict['language'] = stream.input.language

    if self._pipeline_config.segment_per_file:
      dict['init_segment'] = build_path(
        self._segment_dir,
        stream.get_init_seg_file().write_end())
      dict['segment_template'] = build_path(
        self._segment_dir,
        stream.get_media_seg_file().write_end())
    else:
      dict['output'] = build_path(
        self._segment_dir,
        stream.get_single_seg_file().write_end())

    if stream.is_dash_only():
      dict['dash_only'] = '1'

    # The format of this argument to Shaka Packager is a single string of
    # key=value pairs separated by commas.
    return ','.join(key + '=' + value for key, value in dict.items())

  def _setup_manifest_format(self) -> List[str]:
    args: List[str] = []
    if ManifestFormat.DASH in self._pipeline_config.manifest_format:
      if self._pipeline_config.utc_timings:
        args += [
            '--utc_timings',
            ','.join(timing.scheme_id_uri + '=' +
                     timing.value for timing in self._pipeline_config.utc_timings)
        ]
      if self._pipeline_config.low_latency_dash_mode:
        args += [
            '--low_latency_dash_mode=true',
        ]
      if self._pipeline_config.streaming_mode == StreamingMode.VOD:
        args += [
            '--generate_static_live_mpd',
        ]
      args += [
          # Generate DASH manifest file.
          '--mpd_output',
          os.path.join(self.output_location, self._pipeline_config.dash_output),
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
          os.path.join(self.output_location, self._pipeline_config.hls_output),
      ]
    return args

  def _setup_encryption_keys(self) -> List[str]:
    # Sets up encryption keys for raw encryption mode
    keys = []
    for key in self._pipeline_config.encryption.keys:
      key_str = ''
      if key.label:
        key_str = 'label=' + key.label + ':'
      key_str += 'key_id=' + key.key_id + ':key=' + key.key
      keys.append(key_str)
    return keys

  def _setup_encryption(self) -> List[str]:
    # Sets up encryption of content.

    encryption = self._pipeline_config.encryption

    args = []

    if encryption.encryption_mode == EncryptionMode.WIDEVINE:
      args = [
        '--enable_widevine_encryption',
        '--key_server_url', encryption.key_server_url,
        '--content_id', encryption.content_id,
        '--signer', encryption.signer,
        '--aes_signing_key', encryption.signing_key,
        '--aes_signing_iv', encryption.signing_iv,
      ]
    elif encryption.encryption_mode == EncryptionMode.RAW:
      # raw key encryption mode
      args = [
        '--enable_raw_key_encryption',
        '--keys',
        ','.join(self._setup_encryption_keys()),
      ]
      if encryption.iv:
        args.extend(['--iv', encryption.iv])
      if encryption.pssh:
        args.extend(['--pssh', encryption.pssh])

    # Common arguments
    args.extend([
      '--protection_scheme',
      encryption.protection_scheme.value,
      '--clear_lead', str(encryption.clear_lead),
    ])

    if encryption.protection_systems:
      args.extend([
        '--protection_systems', ','.join(
          [p.value for p in encryption.protection_systems]
        )
      ])

    return args
