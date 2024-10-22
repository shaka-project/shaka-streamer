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

class ProtectionSystem(enum.Enum):
  WIDEVINE = 'Widevine'
  FAIRPLAY = 'FairPlay'
  PLAYREADY = 'PlayReady'
  MARLIN = 'Marlin'
  COMMON = 'CommonSystem'

class EncryptionMode(enum.Enum):
  WIDEVINE = 'widevine'
  """Widevine key server mode"""

  RAW = 'raw'
  """Raw key mode"""

class UtcTimingPair(configuration.Base):
  """An object containing the attributes for a DASH MPD UTCTiming 
  element"""

  # TODO: Use an enum for scheme_id_uri to simplify the config input
  scheme_id_uri = configuration.Field(str).cast()
  """SchemeIdUri attribute to be used for the UTCTiming element"""

  value = configuration.Field(str).cast()
  """Value attribute to be used for the UTCTiming element"""

class RawKeyConfig(configuration.Base):
  """An object representing a list of keys for Raw key encryption"""

  label = configuration.Field(str).cast()
  """An arbitary string or a predefined DRM label like AUDIO, SD, HD, etc.
  If not specified, indicates the default key and key_id."""

  key_id = configuration.Field(configuration.HexString, required=True).cast()
  """A key identifier as a 32-digit hex string"""

  key = configuration.Field(configuration.HexString, required=True).cast()
  """The encryption key to use as a 32-digit hex string"""


class EncryptionConfig(configuration.Base):
  """An object representing the encryption config for Shaka Streamer."""

  enable = configuration.Field(bool, default=False).cast()
  """If true, encryption is enabled.

  Otherwise, all other encryption settings are ignored.
  """

  encryption_mode = configuration.Field(
    EncryptionMode, default=EncryptionMode.WIDEVINE).cast()
  """Encryption mode to use. By default it is widevine but can be changed
  to raw."""

  protection_systems = configuration.Field(List[ProtectionSystem]).cast()
  """Protection Systems to be generated. Supported protection systems include
  Widevine, PlayReady, FairPlay, Marin and CommonSystem.
  """

  pssh = configuration.Field(configuration.HexString).cast()
  """One or more concatenated PSSH boxes in hex string format. If this and
  `protection_systems` is not specified, a v1 common PSSH box will be
  generated.
  
  Applies to 'raw' encryption_mode only.
  """

  iv = configuration.Field(configuration.HexString).cast()
  """IV in hex string format. If not specified, a random IV will be
  generated.
  
  Applies to 'raw' encryption_mode only.
  """

  keys = configuration.Field(List[RawKeyConfig]).cast()
  """A list of encryption keys to use.
  
  Applies to 'raw' encryption_mode only."""

  content_id = configuration.Field(
      configuration.HexString, default=RANDOM_CONTENT_ID).cast()
  """The content ID, in hex.

  If omitted, a random content ID will be chosen for you.
  
  Applies to 'widevine' encryption_mode only.
  """

  key_server_url = configuration.Field(str, default=UAT_SERVER).cast()
  """The URL of your key server.

  This is used to generate an encryption key.  By default, it is Widevine's UAT
  server.
  
  Applies to 'widevine' encryption_mode only.
  """

  signer = configuration.Field(str, default=WIDEVINE_TEST_ACCOUNT).cast()
  """The name of the signer when authenticating to the key server.

  Applies to 'widevine' encryption_mode only.

  Defaults to the Widevine test account.
  """

  signing_key = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_KEY).cast()
  """The signing key, in hex, when authenticating to the key server.

  Applies to 'widevine' encryption_mode only.

  Defaults to the Widevine test account's key.
  """

  signing_iv = configuration.Field(
      configuration.HexString, default=WIDEVINE_TEST_SIGNING_IV).cast()
  """The signing IV, in hex, when authenticating to the key server.

  Applies to 'widevine' encryption_mode only.

  Defaults to the Widevine test account's IV.
  """

  protection_scheme = configuration.Field(ProtectionScheme,
                                          default=ProtectionScheme.CENC).cast()
  """The protection scheme (cenc or cbcs) to use when encrypting."""

  clear_lead = configuration.Field(int, default=10).cast()
  """The seconds of unencrypted media at the beginning of the stream."""

  def __init__(self, *args) -> None:
    super().__init__(*args)

    # Don't do any further checks if encryption is disabled
    if not self.enable:
      return

    if self.encryption_mode == EncryptionMode.WIDEVINE:
      field_names = ['keys', 'pssh', 'iv']
      for field_name in field_names:
        if getattr(self, field_name):
          field = getattr(self.__class__, field_name)
          reason = 'cannot be set when encryption_mode is "%s"' % \
                   self.encryption_mode
          raise configuration.MalformedField(
            self.__class__, field_name, field, reason)
    elif self.encryption_mode == EncryptionMode.RAW:
      # Check at least one key has been specified
      if not self.keys:
        field = self.__class__.keys
        reason = 'at least one key must be specified'
        raise configuration.MalformedField(
          self.__class__, 'keys', field, reason)

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
      List[bitrate_configuration.VideoResolutionName]).cast()
  """A list of resolution names to encode.

  Any resolution greater than the input resolution will be ignored, to avoid
  upscaling the content.  This also allows you to reuse a pipeline config for
  multiple inputs.

  If not set, it will default to a list of all the (VideoResolutionName)s
  defined in the bitrate configuration.
  """

  channel_layouts = configuration.Field(
      List[bitrate_configuration.AudioChannelLayoutName]).cast()
  """A list of channel layouts to encode.

  Any channel count greater than the input channel count will be ignored.

  If not set, it will default to a list of all the (AudioChannelLayoutName)s
  defined in the bitrate configuration.
  """

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

  # TODO: Generalize this to low_latency_mode once LL-HLS is supported by Packager
  low_latency_dash_mode = configuration.Field(bool, default=False).cast()
  """If true, stream in low latency mode for DASH."""

  utc_timings = configuration.Field(List[UtcTimingPair]).cast()
  """UTCTiming schemeIdUri and value pairs for the DASH MPD.

  If multiple UTCTiming pairs are provided for redundancy,
  list the pairs in the order of preference.

  Must be set for LL-DASH streaming.
  """


  def __init__(self, *args) -> None:

    # Set the default values of the resolutions and channel_layouts
    # to the values we have in the bitrate configuration.
    # We need the 'type: ignore' here because mypy thinks these variables are lists
    # of VideoResolutionName and AudioChannelLayoutName and not Field variables.
    self.__class__.resolutions.default = list(  # type: ignore
      bitrate_configuration.VideoResolution.keys())
    self.__class__.channel_layouts.default = list(  # type: ignore
      bitrate_configuration.AudioChannelLayout.keys())

    super().__init__(*args)

    if self.streaming_mode == StreamingMode.LIVE and not self.segment_per_file:
      field = self.__class__.segment_per_file
      reason = 'must be true when streaming_mode is "live"'
      raise configuration.MalformedField(
          self.__class__, 'segment_per_file', field, reason)

  def get_resolutions(self) -> List[bitrate_configuration.VideoResolution]:
    VideoResolution = bitrate_configuration.VideoResolution  # alias
    return [VideoResolution.get_value(name) for name in self.resolutions]

  def get_channel_layouts(self) -> List[bitrate_configuration.AudioChannelLayout]:
    AudioChannelLayout = bitrate_configuration.AudioChannelLayout # alias
    return [AudioChannelLayout.get_value(name) for name in self.channel_layouts]
