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

import base64
import enum
import os
import platform
import shlex

from . import bitrate_configuration
from . import configuration

from typing import List


# A randomly-chosen content ID in hex.
RANDOM_CONTENT_ID = base64.b16encode(os.urandom(16)).decode('UTF-8')

# The Widevine UAT server URL.
UAT_SERVER = 'https://license.uat.widevine.com/cenc/getcontentkey/widevine_test'

# Credentials for the Widevine test account.
WIDEVINE_TEST_ACCOUNT = 'widevine_test'
WIDEVINE_TEST_SIGNING_KEY = '1ae8ccd0e7985cc0b6203a55855a1034afc252980e970ca90e5202689f947ab9'
WIDEVINE_TEST_SIGNING_IV = 'd58ce954203b7c9a9a9d467f59839249'

# The default hardware acceleration API to use, per platform.
if platform.system() == 'Linux':
  DEFAULT_HWACCEL_API = 'vaapi'
elif platform.system() == 'Darwin':  # AKA macOS
  DEFAULT_HWACCEL_API = 'videotoolbox'
else:
  DEFAULT_HWACCEL_API = ''


class StreamingMode(enum.Enum):
  LIVE = 'live'
  """Indicates a live stream, which has no end."""

  VOD = 'vod'
  """Indicates a video-on-demand (VOD) stream, which is finite."""

class ManifestFormat(enum.Enum):
  DASH = 'dash'
  HLS = 'hls'

class ProtectionScheme(enum.Enum):
  CENC = 'cenc'
  """AES-128-CTR mode."""

  CBCS = 'cbcs'
  """AES-128-CBC mode with pattern encryption."""


class EncryptionConfig(configuration.Base):
  """An object representing the encryption config for Shaka Streamer."""

  enable = configuration.Field(bool, default=False).cast()
  """If true, encryption is enabled.

  Otherwise, all other encryption settings are ignored.
  """

  content_id = configuration.Field(
      configuration.HexString, default=RANDOM_CONTENT_ID).cast()
  """The content ID, in hex.

  If omitted, a random content ID will be chosen for you.
  """

  key_server_url = configuration.Field(str, default=UAT_SERVER).cast()
  """The URL of your key server.

  This is used to generate an encryption key.  By default, it is Widevine's UAT
  server.
  """

  signer = configuration.Field(str, default=WIDEVINE_TEST_ACCOUNT).cast()
  """The name of the signer when authenticating to the key server.

  Defaults to the Widevine test account.
  """

  signing_key = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_KEY).cast()
  """The signing key, in hex, when authenticating to the key server.

  Defaults to the Widevine test account's key.
  """

  signing_iv = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_IV).cast()
  """The signing IV, in hex, when authenticating to the key server.

  Defaults to the Widevine test account's IV.
  """

  protection_scheme = configuration.Field(ProtectionScheme,
                                          default=ProtectionScheme.CENC).cast()
  """The protection scheme (cenc or cbcs) to use when encrypting."""

  clear_lead = configuration.Field(int, default=10).cast()
  """The seconds of unencrypted media at the beginning of the stream."""


class PipelineConfig(configuration.Base):
  """An object representing the entire pipeline config for Shaka Streamer."""

  streaming_mode = configuration.Field(StreamingMode, required=True).cast()
  """The streaming mode, which can be either 'vod' or 'live'."""

  quiet = configuration.Field(bool, default=False).cast()
  """If true, reduce the level of output.

  Only errors will be shown in quiet mode.
  """

  debug_logs = configuration.Field(bool, default=False).cast()
  """If true, output simple log files from each node.

  No control is given over log filenames.  Logs are written to the current
  working directory.  We do not yet support log rotation.  This is meant only
  for debugging.
  """

  hwaccel_api = configuration.Field(str, default=DEFAULT_HWACCEL_API).cast()
  """The FFmpeg hardware acceleration API to use with hardware codecs.

  A per-platform default will be chosen if this field is omitted.

  See documentation here: https://trac.ffmpeg.org/wiki/HWAccelIntro
  """

  resolutions = configuration.Field(
      List[bitrate_configuration.VideoResolutionName],
      required=True).cast()
  """A list of resolution names to encode.

  Any resolution greater than the input resolution will be ignored, to avoid
  upscaling the content.  This also allows you to reuse a pipeline config for
  multiple inputs.
  """

  # TODO(joeyparrish): Default to whatever is in the input.
  channels = configuration.Field(int, default=2).cast()
  """The number of audio channels to encode."""

  audio_codecs = configuration.Field(
      List[bitrate_configuration.AudioCodec],
      default=[bitrate_configuration.AudioCodec.AAC]).cast()
  """The audio codecs to encode with."""

  video_codecs = configuration.Field(
      List[bitrate_configuration.VideoCodec],
      default=[bitrate_configuration.VideoCodec.H264]).cast()
  """The video codecs to encode with.

  Note that the prefix "hw:" indicates that a hardware encoder should be
  used.
  """

  manifest_format = configuration.Field(List[ManifestFormat],
                                        default=[
                                            ManifestFormat.DASH,
                                            ManifestFormat.HLS,
                                        ]).cast()
  """A list of manifest formats (dash or hls) to create.

  By default, this will create both.
  """

  dash_output = configuration.Field(str, default='dash.mpd').cast()
  """Output filename for the DASH manifest, if created."""

  hls_output = configuration.Field(str, default='hls.m3u8').cast()
  """Output filename for the HLS master playlist, if created."""

  segment_folder = configuration.Field(str, default='').cast()
  """Sub-folder for segment output (or blank for none)."""

  segment_size = configuration.Field(float, default=4).cast()
  """The length of each segment in seconds."""

  segment_per_file = configuration.Field(bool, default=True).cast()
  """If true, force each segment to be in a separate file.

  Must be true for live content.
  """

  availability_window = configuration.Field(int, default=300).cast()
  """The number of seconds a segment remains available."""

  presentation_delay = configuration.Field(int, default=30).cast()
  """How far back from the live edge the player should be, in seconds."""

  update_period = configuration.Field(int, default=8).cast()
  """How often the player should fetch a new manifest, in seconds."""

  encryption = configuration.Field(EncryptionConfig,
                                   default=EncryptionConfig({})).cast()
  """Encryption settings."""


  def __init__(self, *args) -> None:
    super().__init__(*args)

    if self.streaming_mode == StreamingMode.LIVE and not self.segment_per_file:
      field = self.__class__.segment_per_file
      reason = 'must be true when streaming_mode is "live"'
      raise configuration.MalformedField(
          self.__class__, 'segment_per_file', field, reason)

  def get_resolutions(self) -> List[bitrate_configuration.VideoResolution]:
    VideoResolution = bitrate_configuration.VideoResolution  # alias
    return [VideoResolution.get_value(name) for name in self.resolutions]
