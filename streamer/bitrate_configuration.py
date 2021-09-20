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

import enum
import math
import re

from . import configuration
from typing import Dict, Tuple


class BitrateString(configuration.ValidatingType, str):
  """A wrapper that can be used in Field() to require a bitrate string."""

  @staticmethod
  def name() -> str:
    return 'bitrate string'

  @staticmethod
  def validate(value: str) -> None:
    if type(value) is not str:
      raise TypeError()
    if not re.match(r'^[\d\.]+(?:[kM])?$', value):
      raise ValueError('not a bitrate string (e.g. 500k or 7.5M)')


class AudioCodec(enum.Enum):

  AAC: str = 'aac'
  OPUS: str = 'opus'
  AC3: str = 'ac3'
  EAC3: str = 'eac3'

  def is_hardware_accelerated(self) -> bool:
    """Returns True if this codec is hardware accelerated."""
    return False

  def get_ffmpeg_codec_string(self, hwaccel_api: str) -> str:
    """Returns a codec string accepted by FFmpeg for this codec."""
    # FFmpeg warns:
    #   The encoder 'opus' is experimental but experimental codecs are not
    #   enabled, add '-strict -2' if you want to use it. Alternatively use the
    #   non experimental encoder 'libopus'.
    if self == AudioCodec.OPUS:
      return 'libopus'

    return self.value

  def get_output_format(self) -> str:
    """Returns an FFmpeg output format suitable for this codec."""
    # TODO: consider Opus in mp4 by default
    # TODO(#31): add support for configurable output format per-codec
    if self == AudioCodec.OPUS:
      return 'webm'
    elif (self == AudioCodec.AAC) or (self == AudioCodec.AC3) or (self == AudioCodec.EAC3):
      return 'mp4'
    else:
      assert False, 'No mapping for output format for codec {}'.format(
          self.value)


class VideoCodec(enum.Enum):

  H264 = 'h264'
  """H264, also known as AVC."""

  VP9 = 'vp9'
  """VP9."""

  AV1 = 'av1'
  """AV1."""
  
  HEVC = 'hevc'
  """HEVC, also known as h.265"""

  def __init__(self, value):
    # Set all the codecs not to be hardware accelerated at the begining.
    self._hw_acc = False

  @classmethod
  def _missing_(cls, value: object) -> 'VideoCodec':
    if isinstance(value, str) and value.startswith('hw:'):
      obj = cls(value[3:])
      # Overwrite the _hw_acc variable for this codec.
      obj._hw_acc = True
      return obj
    return super()._missing_(value)

  def is_hardware_accelerated(self) -> bool:
    """Returns True if this codec is hardware accelerated."""
    return self._hw_acc

  def get_ffmpeg_codec_string(self, hwaccel_api: str) -> str:
    """Returns a codec string accepted by FFmpeg for this codec."""
    if self._hw_acc:
      assert hwaccel_api, 'No hardware encoding support on this platform!'
      return self.value + '_' + hwaccel_api

    return self.value

  def get_output_format(self) -> str:
    """Returns an FFmpeg output format suitable for this codec."""
    # TODO: consider VP9 in mp4 by default
    # TODO(#31): add support for configurable output format per-codec
    if self == VideoCodec.VP9:
      return 'webm'
    elif self in {VideoCodec.H264, VideoCodec.HEVC}:
      return 'mp4'
    elif self == VideoCodec.AV1:
      return 'mp4'
    else:
      assert False, 'No mapping for output format for codec {}'.format(
          self.value)


class AudioChannelLayout(configuration.RuntimeMap):

  max_channels = configuration.Field(type=int, required=True).cast()
  """The maximum number of channels in this layout.

  For example, the maximum number of channels for stereo is 2.
  """

  bitrates = configuration.Field(
      Dict[AudioCodec, BitrateString], required=True).cast()
  """A map of audio codecs to the target bitrate for this channel layout.

  For example, in stereo, AAC can have a different bitrate from Opus.

  This value is a string in bits per second, with the suffix 'k' or 'M' for
  kilobits per second or megabits per second.

  For example, this could be '500k' or '7.5M'.
  """

  def _sortable_properties(self) -> Tuple[float]:
    """Return a tuple of properties we can sort on."""
    return (self.max_channels,)


DEFAULT_AUDIO_CHANNEL_LAYOUTS = {
  'mono': AudioChannelLayout({
    'max_channels': 1,
    'bitrates': {
      'aac': '64k',
      'opus': '32k',
      'ac3': '96k',
      'eac3': '48k',
    },
  }),
  'stereo': AudioChannelLayout({
    'max_channels': 2,
    'bitrates': {
      'aac': '128k',
      'opus': '64k',
      'ac3': '192k',
      'eac3': '96k',
    },
  }),
  'surround': AudioChannelLayout({
    'max_channels': 6,
    'bitrates': {
      'aac': '256k',
      'opus': '128k',
      'ac3': '384k',
      'eac3': '192k',
    },
  }),
}

class AudioChannelLayoutName(configuration.RuntimeMapKeyValidator):
  """A type which will only allow valid AudioChannelLayout names at runtime."""

  map_class = AudioChannelLayout


class VideoResolution(configuration.RuntimeMap):

  max_width = configuration.Field(type=int, required=True).cast()
  """The maximum width in pixels for this named resolution."""

  max_height = configuration.Field(type=int, required=True).cast()
  """The maximum height in pixels for this named resolution."""

  max_frame_rate = configuration.Field(type=float, default=math.inf).cast()
  """The maximum frame rate in frames per second for this named resolution.

  By default, the max frame rate is unlimited.
  """

  bitrates = configuration.Field(
      Dict[VideoCodec, BitrateString], required=True).cast()
  """A map of video codecs to the target bitrate for this resolution.

  For example, in 1080p, H264 can have a different bitrate from VP9.

  This value is a string in bits per second, with the suffix 'k' or 'M' for
  kilobits per second or megabits per second.

  For example, this could be '500k' or '7.5M'.
  """

  def _sortable_properties(self) -> Tuple[int, int, float]:
    """Return a tuple of properties we can sort on."""
    return (self.max_width, self.max_height, self.max_frame_rate)


class VideoResolutionName(configuration.RuntimeMapKeyValidator):
  """A type which will only allow valid VideoResolution names at runtime."""

  map_class = VideoResolution


# Default bitrates and resolutions are tracked internally at
# go/shaka-streamer-bitrates
# These are common resolutions, and the bitrates per codec are derived from
# internal encoding guidelines.
DEFAULT_VIDEO_RESOLUTIONS = {
  '144p': VideoResolution({
    'max_width': 256,
    'max_height': 144,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '108k',
      'vp9': '96k',
      'hevc': '96k',
      'av1': '72k',
    },
  }),
  '240p': VideoResolution({
    'max_width': 426,
    'max_height': 240,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '242k',
      'vp9': '151k',
      'hevc': '151k',
      'av1': '114k',
    },
  }),
  '360p': VideoResolution({
    'max_width': 640,
    'max_height': 360,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '400k',
      'vp9': '277k',
      'hevc': '277k',
      'av1': '210k',
    },
  }),
  '480p': VideoResolution({  # NTSC analog broadcast TV resolution
    'max_width': 854,
    'max_height': 480,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '1M',
      'vp9': '512k',
      'hevc': '512k',
      'av1': '389k',
    },
  }),
  '576p': VideoResolution({  # PAL analog broadcast TV resolution
    'max_width': 1024,
    'max_height': 576,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '1.5M',
      'vp9': '768k',
      'hevc': '768k',
      'av1': '450k',
    },
  }),
  '720p': VideoResolution({
    'max_width': 1280,
    'max_height': 720,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '2M',
      'vp9': '1M',
      'hevc': '1M',
      'av1': '512k',
    },
  }),
  '720p-hfr': VideoResolution({
    'max_width': 1280,
    'max_height': 720,
    'bitrates': {
      'h264': '3M',
      'vp9': '2M',
      'hevc': '2M',
      'av1': '778k',
    },
  }),
  '1080p': VideoResolution({
    'max_width': 1920,
    'max_height': 1080,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '4M',
      'vp9': '2M',
      'hevc': '2M',
      'av1': '850k',
    },
  }),
  '1080p-hfr': VideoResolution({
    'max_width': 1920,
    'max_height': 1080,
    'bitrates': {
      'h264': '5M',
      'vp9': '3M',
      'hevc': '3M',
      'av1': '1M',
    },
  }),
  '1440p': VideoResolution({
    'max_width': 2560,
    'max_height': 1440,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '9M',
      'vp9': '6M',
      'hevc': '6M',
      'av1': '3.5M',
    },
  }),
  '1440p-hfr': VideoResolution({
    'max_width': 2560,
    'max_height': 1440,
    'bitrates': {
      'h264': '14M',
      'vp9': '9M',
      'hevc': '9M',
      'av1': '5M',
    },
  }),
  '4k': VideoResolution({
    'max_width': 4096,
    'max_height': 2160,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '17M',
      'vp9': '12M',
      'hevc': '12M',
      'av1': '6M',
    },
  }),
  '4k-hfr': VideoResolution({
    'max_width': 4096,
    'max_height': 2160,
    'bitrates': {
      'h264': '25M',
      'vp9': '18M',
      'hevc': '18M',
      'av1': '9M',
    },
  }),
  '8k': VideoResolution({
    'max_width': 8192,
    'max_height': 4320,
    'max_frame_rate': 30,
    'bitrates': {
      'h264': '40M',
      'vp9': '24M',
      'hevc': '24M',
      'av1': '12M',
    },
  }),
  '8k-hfr': VideoResolution({
    'max_width': 8192,
    'max_height': 4320,
    'bitrates': {
      'h264': '60M',
      'vp9': '36M',
      'hevc': '36M',
      'av1': '18M',
    },
  }),
}


class BitrateConfig(configuration.Base):

  audio_channel_layouts = configuration.Field(
      Dict[str, AudioChannelLayout],
      default=DEFAULT_AUDIO_CHANNEL_LAYOUTS).cast()
  """A map of named channel layouts.

  For example, the key would be a name like "stereo", and the value would be an
  object with all the parameters of how stereo audio would be encoded (2
  channels max, bitrates, etc.).
  """

  video_resolutions = configuration.Field(
      Dict[str, VideoResolution], default=DEFAULT_VIDEO_RESOLUTIONS).cast()
  """A map of named resolutions.

  For example, the key would be a name like "1080p", and the value would be an
  object with all the parameters of how 1080p video would be encoded (max size,
  bitrates, etc.)
  """
