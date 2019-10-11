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

"""Maps channels and resolutions to bitrate, size, and profile."""

class ChannelData(object):

  def __init__(self, aac_bitrate, opus_bitrate):
    self.aac_bitrate = aac_bitrate
    self.opus_bitrate = opus_bitrate

class ResolutionData(object):

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
# TODO(joeyparrish): Break this down into a multi-level map involving codec.
CHANNEL_MAP = {
    2: ChannelData('128k', '64k'),
    6: ChannelData('192k', '96k'),
}

# A map of resolutions to ResolutionData objects which contain
# the height and bitrate of a given resolution.
# TODO(joeyparrish): Break this down into a multi-level map involving codec.
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

class Metadata(object):
  def __init__(self, pipe, channels=None, resolution_name=None,
               codec=None, language=None, hardware=False):
    self.pipe = pipe
    self.channels = channels
    self.codec = codec
    self.language = language
    self.resolution_name = resolution_name
    self.hardware = hardware

    # TODO(joeyparrish): Use constants for codec & format names
    if channels:
      self.type = 'audio'
      # TODO(joeyparrish): channel_data is a weak variable name.
      self.channel_data = CHANNEL_MAP[channels]
      if self.codec == 'aac':
        self.bitrate = self.channel_data.aac_bitrate
        self.format = 'mp4'
      elif self.codec == 'opus':
        self.bitrate = self.channel_data.opus_bitrate
        self.format = 'webm'

    if resolution_name:
      self.type = 'video'
      # TODO(joeyparrish): resolution_data is a weak variable name.
      self.resolution_data = RESOLUTION_MAP[resolution_name]
      if self.codec == 'h264':
        self.bitrate = self.resolution_data.h264_bitrate
        self.format = 'mp4'
      elif self.codec == 'vp9':
        self.bitrate = self.resolution_data.vp9_bitrate
        self.format = 'webm'

  def fill_template(self, template, **kwargs):
    """Fill in a template string using **kwargs and values in self."""
    value_map = {}
    # First take any values from this object itself.
    value_map.update(self.__dict__)
    # Then fill in any values from kwargs.
    value_map.update(kwargs)
    # Now fill in the template with these values.
    return template.format(**value_map)
