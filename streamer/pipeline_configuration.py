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
import shlex

from . import configuration
from . import metadata


# A runtime-created enum for valid resolutions, based on the |metadata| module.
Resolution = configuration.enum_from_keys('Resolution', metadata.RESOLUTION_MAP)

# A randomly-chosen content ID in hex.
RANDOM_CONTENT_ID = base64.b16encode(os.urandom(16)).decode('UTF-8')

# The Widevine UAT server URL.
UAT_SERVER = 'https://license.uat.widevine.com/cenc/getcontentkey/widevine_test'

# Credentials for the Widevine test account.
WIDEVINE_TEST_ACCOUNT = 'widevine_test'
WIDEVINE_TEST_SIGNING_KEY = '1ae8ccd0e7985cc0b6203a55855a1034afc252980e970ca90e5202689f947ab9'
WIDEVINE_TEST_SIGNING_IV = 'd58ce954203b7c9a9a9d467f59839249'


class StreamingMode(enum.Enum):
  LIVE = 'live'
  """Indicates a live stream, which has no end."""

  VOD = 'vod'
  """Indicates a video-on-demand (VOD) stream, which is finite."""

class AudioCodec(enum.Enum):
  AAC = 'aac'
  OPUS = 'opus'

# TODO: ideally, we wouldn't have to explicitly list hw: variants
class VideoCodec(enum.Enum):
  H264 = 'h264'
  """H264, also known as AVC."""

  HARDWARE_H264 = 'hw:h264'
  """H264 with hardware encoding."""

  VP9 = 'vp9'
  """VP9."""

  HARDWARE_VP9 = 'hw:vp9'
  """VP9 with hardware encoding."""

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

  enable = configuration.Field(bool, default=False)
  """If true, encryption is enabled.

  Otherwise, all other encryption settings are ignored.
  """

  content_id = configuration.Field(
      configuration.HexString, default=RANDOM_CONTENT_ID)
  """The content ID, in hex.

  If omitted, a random content ID will be chosen for you.
  """

  key_server_url = configuration.Field(str, default=UAT_SERVER)
  """The URL of your key server.

  This is used to generate an encryption key.  By default, it is Widevine's UAT
  server.
  """

  signer = configuration.Field(str, default=WIDEVINE_TEST_ACCOUNT)
  """The name of the signer when authenticating to the key server.

  Defaults to the Widevine test account.
  """

  signing_key = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_KEY)
  """The signing key, in hex, when authenticating to the key server.

  Defaults to the Widevine test account's key.
  """

  signing_iv = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_IV)
  """The signing IV, in hex, when authenticating to the key server.

  Defaults to the Widevine test account's IV.
  """

  protection_scheme = configuration.Field(ProtectionScheme,
                                          default=ProtectionScheme.CENC)
  """The protection scheme (cenc or cbcs) to use when encrypting."""

  clear_lead = configuration.Field(int, default=10)
  """The seconds of unencrypted media at the beginning of the stream."""


class PipelineConfig(configuration.Base):
  """An object representing the entire pipeline config for Shaka Streamer."""

  streaming_mode = configuration.Field(StreamingMode, required=True)
  """The streaming mode, which can be either 'vod' or 'live'."""

  quiet = configuration.Field(bool, default=False)
  """If true, reduce the level of output.

  Only errors will be shown in quiet mode.
  """

  debug_logs = configuration.Field(bool, default=False)
  """If true, output simple log files from each node.

  No control is given over log filenames.  Logs are written to the current
  working directory.  We do not yet support log rotation.  This is meant only
  for debugging.
  """

  resolutions = configuration.Field(list, subtype=Resolution,
                                    default=[
                                        Resolution._720p,
                                        Resolution._480p,
                                    ])
  """A list of resolution names to encode.

  Any resolution greater than the input resolution will be ignored, to avoid
  upscaling the content.  By default, will encode in 480p and 720p.
  """

  # TODO(joeyparrish): Default to whatever is in the input.
  channels = configuration.Field(int, default=2)
  """The number of audio channels to encode."""

  audio_codecs = configuration.Field(list, subtype=AudioCodec,
                                     default=[AudioCodec.AAC])
  """The audio codecs to encode with."""

  video_codecs = configuration.Field(list, subtype=VideoCodec,
                                     default=[VideoCodec.H264])
  """The video codecs to encode with.

  Note that the prefix "hw:" indicates that a hardware encoder should be
  used.
  """

  manifest_format = configuration.Field(list, subtype=ManifestFormat,
                                        default=[
                                            ManifestFormat.DASH,
                                            ManifestFormat.HLS,
                                        ])
  """A list of manifest formats (dash or hls) to create.

  By default, this will create both.
  """

  dash_output = configuration.Field(str, default='dash.mpd')
  """Output filename for the DASH manifest, if created."""

  hls_output = configuration.Field(str, default='hls.m3u8')
  """Output filename for the HLS master playlist, if created."""

  segment_folder = configuration.Field(str, default='')
  """Sub-folder for segment output (or blank for none)."""

  segment_size = configuration.Field(float, default=4)
  """The length of each segment in seconds."""

  segment_per_file = configuration.Field(bool, default=True)
  """If true, force each segment to be in a separate file.

  Must be true for live content.
  """

  availability_window = configuration.Field(int, default=300)
  """The number of seconds a segment remains available."""

  presentation_delay = configuration.Field(int, default=30)
  """How far back from the live edge the player should be, in seconds."""

  update_period = configuration.Field(int, default=8)
  """How often the player should fetch a new manifest, in seconds."""

  encryption = configuration.Field(EncryptionConfig,
                                   default=EncryptionConfig({}))
  """Encryption settings."""


  def __init__(self, *args):
    super().__init__(*args)

    if self.streaming_mode == StreamingMode.LIVE and not self.segment_per_file:
      field = self.__class__.segment_per_file
      reason = 'must be true when streaming_mode is "live"'
      raise configuration.MalformedField(
          self.__class__, 'segment_per_file', field, reason)

