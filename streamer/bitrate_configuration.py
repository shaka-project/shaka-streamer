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
from typing import Any, Dict, Tuple


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
    elif self == AudioCodec.AAC:
      return 'mp4'
    else:
      assert False, 'No mapping for output format for codec {}'.format(
          self.value)


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

  AV1 = 'av1'
  """AV1."""

  def is_hardware_accelerated(self) -> bool:
    """Returns True if this codec is hardware accelerated."""
    return self.value.startswith('hw:')

  def get_base_codec(self) -> 'VideoCodec':
    """Returns an instance of the same codec without hardware acceleration."""
    if self.is_hardware_accelerated():
      value_without_prefix = self.value.split(':')[1]
      return VideoCodec(value_without_prefix)

    return self

  def get_ffmpeg_codec_string(self, hwaccel_api: str) -> str:
    """Returns a codec string accepted by FFmpeg for this codec."""
    if self.is_hardware_accelerated():
      assert hwaccel_api, 'No hardware encoding support on this platform!'
      return self.get_base_codec().value + '_' + hwaccel_api

    return self.value

  def get_output_format(self) -> str:
    """Returns an FFmpeg output format suitable for this codec."""
    # TODO: consider VP9 in mp4 by default
    # TODO(#31): add support for configurable output format per-codec
    if self.get_base_codec() == VideoCodec.VP9:
      return 'webm'
    elif self.get_base_codec() == VideoCodec.H264:
      return 'mp4'
    elif self.get_base_codec() == VideoCodec.AV1:
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
  'stereo': AudioChannelLayout({
    'max_channels': 2,
    'bitrates': {
      'aac': '128k',
      'opus': '64k',
    },
  }),
  'surround': AudioChannelLayout({
    'max_channels': 6,
    'bitrates': {
      'aac': '192k',
      'opus': '96k',
    },
  }),
}


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
    'bitrates': {
      'h264': '108k',
      'vp9': '96k',
      'av1': '72k',
    },
  }),
  '240p': VideoResolution({
    'max_width': 426,
    'max_height': 240,
    'bitrates': {
      'h264': '242k',
      'vp9': '151k',
      'av1': '114k',
    },
  }),
  '360p': VideoResolution({
    'max_width': 640,
    'max_height': 360,
    'bitrates': {
      'h264': '400k',
      'vp9': '277k',
      'av1': '210k',
    },
  }),
  '480p': VideoResolution({  # NTSC analog broadcast TV resolution
    'max_width': 854,
    'max_height': 480,
    'bitrates': {
      'h264': '1M',
      'vp9': '512k',
      'av1': '389k',
    },
  }),
  '576p': VideoResolution({  # PAL analog broadcast TV resolution
    'max_width': 1024,
    'max_height': 576,
    'bitrates': {
      'h264': '1.5M',
      'vp9': '768k',
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
      'av1': '512k',
    },
  }),
  '720p-hfr': VideoResolution({
    'max_width': 1280,
    'max_height': 720,
    'bitrates': {
      'h264': '3M',
      'vp9': '2M',
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
      'av1': '850k',
    },
  }),
  '1080p-hfr': VideoResolution({
    'max_width': 1920,
    'max_height': 1080,
    'bitrates': {
      'h264': '5M',
      'vp9': '3M',
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
      'av1': '3.5M',
    },
  }),
  '1440p-hfr': VideoResolution({
    'max_width': 2560,
    'max_height': 1440,
    'bitrates': {
      'h264': '14M',
      'vp9': '9M',
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
      'av1': '6M',
    },
  }),
  '4k-hfr': VideoResolution({
    'max_width': 4096,
    'max_height': 2160,
    'bitrates': {
      'h264': '25M',
      'vp9': '18M',
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
      'av1': '12M',
    },
  }),
  '8k-hfr': VideoResolution({
    'max_width': 8192,
    'max_height': 4320,
    'bitrates': {
      'h264': '60M',
      'vp9': '36M',
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
