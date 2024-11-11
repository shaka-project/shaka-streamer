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

from streamer.bitrate_configuration import AudioCodec, AudioChannelLayout, VideoCodec, VideoResolution
from streamer.input_configuration import Input, MediaType
from streamer.pipe import Pipe
from typing import Dict, Union


class OutputStream(object):
  """Base class for output streams."""

  def __init__(self,
               type: MediaType,
               input: Input,
               codec: Union[AudioCodec, VideoCodec, None],
               pipe_dir: str,
               skip_transcoding: bool = False,
               pipe_suffix: str = '') -> None:

    self.type: MediaType = type
    self.skip_transcoding = skip_transcoding
    self.input: Input = input
    self.features: Dict[str, str] = {}
    self.codec: Union[AudioCodec, VideoCodec, None] = codec

    if self.skip_transcoding:
      # If skip_transcoding is specified, let the Packager read from a plain
      # file instead of an IPC pipe.
      self.ipc_pipe = Pipe.create_file_pipe(self.input.name, mode='r')
    else:
      self.ipc_pipe = Pipe.create_ipc_pipe(pipe_dir, pipe_suffix)

  def is_hardware_accelerated(self) -> bool:
    """Returns True if this output stream uses hardware acceleration."""
    if self.codec:
      return self.codec.is_hardware_accelerated()
    return False

  def get_ffmpeg_codec_string(self, hwaccel_api: str) -> str:
    """Returns a codec string accepted by FFmpeg for this stream's codec."""
    assert self.codec is not None
    return self.codec.get_ffmpeg_codec_string(hwaccel_api)

  def is_dash_only(self) -> bool:
    """Returns True if the output format is restricted to DASH protocol"""
    if self.codec is not None:
      return self.codec.get_output_format() == 'webm'
    return False

  def get_init_seg_file(self) -> Pipe:
    INIT_SEGMENT = {
      MediaType.AUDIO: 'audio_{language}_{channels}c_{bitrate}_{codec}_init.{format}',
      MediaType.VIDEO: 'video_{resolution_name}_{bitrate}_{codec}_init.{format}',
      MediaType.TEXT: 'text_{language}_init.{format}',
    }
    path_templ = INIT_SEGMENT[self.type].format(**self.features)
    return Pipe.create_file_pipe(path_templ, mode='w')

  def get_media_seg_file(self) -> Pipe:
    MEDIA_SEGMENT = {
      MediaType.AUDIO: 'audio_{language}_{channels}c_{bitrate}_{codec}_$Number$.{format}',
      MediaType.VIDEO: 'video_{resolution_name}_{bitrate}_{codec}_$Number$.{format}',
      MediaType.TEXT: 'text_{language}_$Number$.{format}',
    }
    path_templ = MEDIA_SEGMENT[self.type].format(**self.features)
    return Pipe.create_file_pipe(path_templ, mode='w')

  def get_single_seg_file(self) -> Pipe:
    SINGLE_SEGMENT = {
      MediaType.AUDIO: 'audio_{language}_{channels}c_{bitrate}_{codec}.{format}',
      MediaType.VIDEO: 'video_{resolution_name}_{bitrate}_{codec}.{format}',
      MediaType.TEXT: 'text_{language}.{format}',
    }
    path_templ = SINGLE_SEGMENT[self.type].format(**self.features)
    return Pipe.create_file_pipe(path_templ, mode='w')


class AudioOutputStream(OutputStream):

  def __init__(self,
               input: Input,
               pipe_dir: str,
               codec: AudioCodec,
               channel_layout: AudioChannelLayout) -> None:

    super().__init__(MediaType.AUDIO, input, codec, pipe_dir)
    # Override the codec type and specify that it's an audio codec
    self.codec: AudioCodec = codec
    self.layout = channel_layout

    # The features that will be used to generate the output filename.
    self.features = {
      'language': input.language,
      'channels': str(self.layout.max_channels),
      'bitrate': self.get_bitrate(),
      'format': self.codec.get_output_format(),
      'codec': self.codec.value,
    }

  def get_bitrate(self) -> str:
    """Returns the bitrate for this stream."""
    return self.layout.bitrates[self.codec]


class VideoOutputStream(OutputStream):

  def __init__(self,
               input: Input,
               pipe_dir: str,
               codec: VideoCodec,
               resolution: VideoResolution) -> None:
    super().__init__(MediaType.VIDEO, input, codec, pipe_dir)
    # Override the codec type and specify that it's an audio codec
    self.codec: VideoCodec = codec
    self.resolution = resolution

    # The features that will be used to generate the output filename.
    self.features = {
      'resolution_name': self.resolution.get_key(),
      'bitrate': self.get_bitrate(),
      'format': self.codec.get_output_format(),
      'codec': self.codec.value,
    }

  def get_bitrate(self) -> str:
    """Returns the bitrate for this stream."""
    return self.resolution.bitrates[self.codec]


class TextOutputStream(OutputStream):

  def __init__(self,
               input: Input,
               pipe_dir: str,
               skip_transcoding: bool):
    # We don't have a codec per se for text, but we'd like to generically
    # process OutputStream objects in ways that are easier with this attribute
    # set, so set it to None.
    codec = None

    super().__init__(MediaType.TEXT, input, codec, pipe_dir,
                     skip_transcoding, pipe_suffix='.vtt')

    # The features that will be used to generate the output filename.
    self.features = {
      'language': input.language,
      'format': 'mp4',
    }
