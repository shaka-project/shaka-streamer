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

"""A module that maps channels to its respective bitrate and resolutions to its
respective height, bitrate and profile."""

class ChannelData():

  def __init__(self, aac_bitrate, opus_bitrate):
    self.aac_bitrate = aac_bitrate
    self.opus_bitrate = opus_bitrate

class ResolutionData():

  def __init__(self, width, height, h264_bitrate, vp9_bitrate, h264_profile):
    self.width = width
    self.height = height
    self.h264_bitrate = h264_bitrate
    self.vp9_bitrate = vp9_bitrate
    self.h264_profile = h264_profile

  def __eq__(self, other):
    return self.height == other.height

  def __ne__(self, other):
    return not self.__eq__(other)

  def __ge__(self, other):
    return self.height >= other.height

# A map of channels to ChannelData objects which contains the AAC and Opus
# bitrate information of a given channel.
CHANNEL_MAP = {
    2: ChannelData(128, 64),
    6: ChannelData(192, 96),
}

# A map of resolutions to ResolutionData objects which contain
# the height and H264 bitrate of a given resolution.
RESOLUTION_MAP = {
    '144p': ResolutionData(256, 144, '108k', '95k', 'baseline'),
    '240p': ResolutionData(426, 240, '242k', '150k', 'main'),
    '360p': ResolutionData(640, 360, '400k', '276k', 'main'),
    '480p': ResolutionData(854, 480, '2M', '750k', 'main'),
    '576p': ResolutionData(1024, 576, '2.5M', '1M', 'main'),
    '720p': ResolutionData(1280, 720, '3M', '2M', 'main'),
    '720p-hfr': ResolutionData(1280, 720, '4M', '4M', 'main'),
    '1080p': ResolutionData(1920, 1080, '5M', '4M', 'high'),
    '1080p-hfr': ResolutionData(1920, 1080, '6M', '6M', 'high'),
    '2k': ResolutionData(2560, 1440, '9M', '6M', 'high'),
    '2k-hfr': ResolutionData(2560, 1440, '14M', '9M', 'high'),
    '4k': ResolutionData(3840, 2160, '17M', '12M', 'uhd'),
    '4k-hfr': ResolutionData(3840, 2160, '25M', '18M', 'uhd'),
}

class Metadata():

  def __init__(self, pipe, channels = None, res_string = None,
               audio_codec = None, video_codec = None, lang=None,
               hardware=None):
    self.pipe = pipe
    if channels:
      self.channels = channels
      self.audio_codec = audio_codec
      self.channel_data = CHANNEL_MAP[channels]
      self.lang = lang
    if res_string:
      self.res = res_string
      self.video_codec = video_codec
      self.resolution_data = RESOLUTION_MAP[res_string]
      self.hardware = hardware
