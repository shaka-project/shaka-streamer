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

from streamer.bitrate_configuration import AudioCodec, VideoCodec, VideoResolution
from streamer.input_configuration import Input, MediaType
from typing import Any, Dict, Union

# Alias a few classes to avoid repeating namespaces later.
ChannelLayout = bitrate_configuration.ChannelLayout


class OutputStream(object):
  """Base class for output streams."""

  def __init__(self,
               type: MediaType,
               pipe: str,
               input: Input,
               codec: Union[AudioCodec, VideoCodec, None]) -> None:
    self.type: MediaType = type
    self.pipe: str = pipe
    self.input: Input = input
    self.codec: Union[AudioCodec, VideoCodec, None] = codec
    self._features: Dict[str, Any] = {}

  def fill_template(self, template: str, **kwargs) -> str:
    """Fill in a template string using **kwargs and features of the output."""

    value_map: Dict[str, str] = {}
    # First take any feature values from this object.
    value_map.update(self._features)
    # Then fill in any values from kwargs.
    value_map.update(kwargs)
    # Now fill in the template with these values.
    return template.format(**value_map)

  def is_hardware_accelerated(self) -> bool:
    """Returns True if this output stream uses hardware acceleration."""
    if self.codec:
      return self.codec.is_hardware_accelerated()
    return False

  def get_ffmpeg_codec_string(self, hwaccel_api: str) -> str:
    """Returns a codec string accepted by FFmpeg for this stream's codec."""
    assert self.codec is not None
    return self.codec.get_ffmpeg_codec_string(hwaccel_api)


class AudioOutputStream(OutputStream):

  def __init__(self,
               pipe: str,
               input: Input,
               codec: AudioCodec,
               channels: int) -> None:

    super().__init__(MediaType.AUDIO, pipe, input, codec)
    # Override the codec type and specify that it's an audio codec
    self.codec: AudioCodec = codec

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

  def get_bitrate(self) -> str:
    """Returns the bitrate for this stream."""
    assert self.layout is not None
    return self.layout.bitrates[self.codec]


class VideoOutputStream(OutputStream):

  def __init__(self,
               pipe: str,
               input: Input,
               codec: VideoCodec,
               resolution: VideoResolution) -> None:
    super().__init__(MediaType.VIDEO, pipe, input, codec)
    # Override the codec type and specify that it's an audio codec
    self.codec: VideoCodec = codec
    self.resolution = resolution

    # The features that will be used to generate the output filename.
    self._features = {
      'resolution_name': self.resolution.get_key(),
      'bitrate': self.get_bitrate(),
      'format': self.codec.get_output_format(),
    }

  def get_bitrate(self) -> str:
    """Returns the bitrate for this stream."""
    return self.resolution.bitrates[self.codec.get_base_codec()]


class TextOutputStream(OutputStream):

  def __init__(self, input):
    super().__init__(
        MediaType.TEXT,
        # We don't transcode or process text yet,
        # so this isn't really a pipe.
        # But assigning the input name to pipe for
        # text allows PackagerNode to be
        # ignorant of these details.
        input.name,
        input,
        # We don't have a codec per se for text,
        # but we'd like to generically
        # process OutputStream objects in ways that
        # are easier with this attribute set, so set it to None.
        None)


    # The features that will be used to generate the output filename.
    self._features = {
      'language': input.language,
      'format': 'mp4',
    }

