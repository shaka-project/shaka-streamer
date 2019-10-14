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

"""Contains information about each output stream."""

from . import bitrate_configuration
from . import input_configuration

# Alias a few classes to avoid repeating namespaces later.
ChannelLayout = bitrate_configuration.ChannelLayout
MediaType = input_configuration.MediaType


class OutputStream(object):
  """Base class for output streams."""

  def fill_template(self, template, **kwargs):
    """Fill in a template string using **kwargs and features of the output."""

    value_map = {}
    # First take any feature values from this object.
    value_map.update(self._features)
    # Then fill in any values from kwargs.
    value_map.update(kwargs)
    # Now fill in the template with these values.
    return template.format(**value_map)

  def is_hardware_accelerated(self):
    """Returns True if this output stream uses hardware acceleration."""
    return self.codec and self.codec.is_hardware_accelerated()

  def get_ffmpeg_codec_string(self, hwaccel_api):
    """Returns a codec string accepted by FFmpeg for this stream's codec."""
    return self.codec and self.codec.get_ffmpeg_codec_string(hwaccel_api)


class AudioOutputStream(OutputStream):

  def __init__(self, pipe, input, codec, channels):
    self.type = MediaType.AUDIO
    self.pipe = pipe
    self.input = input
    self.codec = codec

    # TODO: Make channels an input feature instead of an output feature
    self.channels = channels

    # Until we make channels an input feature, match this output feature to a
    # specific channel layout.  Use the first one the output channels fit into.
    self.layout = None
    for layout in ChannelLayout.sorted_values():
      if self.channels <= layout.max_channels:
        self.layout = layout
        break

    assert self.layout, 'Unable to find audio layout for {} channels'.format(
        self.channels)

    # The features that will be used to generate the output filename.
    self._features = {
      'language': input.language,
      'channels': self.channels,
      'bitrate': self.get_bitrate(),
      'format': self.codec.get_output_format(),
    }

  def get_bitrate(self):
    """Returns the bitrate for this stream."""
    return self.layout.bitrates[self.codec]


class VideoOutputStream(OutputStream):

  def __init__(self, pipe, input, codec, resolution):
    self.type = MediaType.VIDEO
    self.pipe = pipe
    self.input = input
    self.codec = codec
    self.resolution = resolution

    # The features that will be used to generate the output filename.
    self._features = {
      'resolution_name': self.resolution.get_key(),
      'bitrate': self.get_bitrate(),
      'format': self.codec.get_output_format(),
    }

  def get_bitrate(self):
    """Returns the bitrate for this stream."""
    return self.resolution.bitrates[self.codec.get_base_codec()]


class TextOutputStream(OutputStream):

  def __init__(self, input):
    self.type = MediaType.TEXT
    # We don't transcode or process text yet, so this isn't really a pipe.
    # But assigning the input name to pipe for text allows PackagerNode to be
    # ignorant of these details.
    self.pipe = input.name
    self.input = input
    # We don't have a codec per se for text, but we'd like to generically
    # process OutputStream objects in ways that are easier with this attribute
    # set, so set it to None.
    self.codec = None

    # The features that will be used to generate the output filename.
    self._features = {
      'language': input.language,
      'format': 'mp4',
    }

