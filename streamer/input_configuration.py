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
import platform

from . import bitrate_configuration
from . import configuration

from typing import List, Dict, Any, Optional


class InputNotFound(configuration.ConfigError):
  """An error raised when an input stream is not found."""

  def __init__(self, input):
    super().__init__(input.__class__, 'track_num',
                     getattr(input.__class__, 'track_num'))
    self.input = input

  def __str__(self):
    return ('In {}, {} track #{} was'
            ' not found in "{}"').format(self.class_name,
                                         self.input.media_type.value,
                                         self.input.track_num,
                                         self.input.name)

class InputType(enum.Enum):
  FILE = 'file'
  """A track from a file.  Usable only with VOD."""

  LOOPED_FILE = 'looped_file'
  """A track from a file, looped forever by FFmpeg.  Usable only with live.

  Does not support media_type of 'text'.
  """

  WEBCAM = 'webcam'
  """A webcam device.  Usable only with live.

  The device path should be given in the name field.  For example, on Linux,
  this might be /dev/video0.

  Only supports media_type of 'video'.
  """

  MICROPHONE = 'microphone'
  """A microphone device.  Usable only with live.

  The device path should given in the name field.  For example, on Linux, this
  might be "default".

  Only supports media_type of 'audio'.
  """

  EXTERNAL_COMMAND = 'external_command'
  """An external command that generates a stream of audio or video.

  The command should be given in the name field, using shell quoting rules.
  The command should send its generated output to the path in the environment
  variable $SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT, which Shaka Streamer set to
  the path to the output pipe.

  May require the user of extra_input_args if FFmpeg can't guess the format or
  framerate.

  Does not support media_type of 'text'.
  """

class MediaType(enum.Enum):
  AUDIO = 'audio'
  VIDEO = 'video'
  TEXT = 'text'


class Input(configuration.Base):
  """An object representing a single input stream to Shaka Streamer."""

  input_type = configuration.Field(InputType, default=InputType.FILE).cast()
  """The type of the input."""

  name = configuration.Field(str, required=True).cast()
  """Name of the input.

  With input_type set to 'file', this is a path to a file name.

  With input_type set to 'looped_file', this is a path to a file name to be
  looped indefinitely in FFmpeg.

  With input_type set to 'webcam', this is which webcam.  On Linux, this is a
  path to the device node for the webcam, such as '/dev/video0'.  On macOS, this
  is a device name, such as 'default'.

  With input_type set to 'external_command', this is an external command that
  generates a stream of audio or video.  The command will be parsed using shell
  quoting rules.  The command should send its generated output to the path in
  the environment variable $SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT, which Shaka
  Streamer set to the path to the output pipe.
  """

  extra_input_args = configuration.Field(str, default='').cast()
  """Extra input arguments needed by FFmpeg to understand the input.

  This allows you to take inputs that cannot be understand or detected
  automatically by FFmpeg.

  This string will be parsed using shell quoting rules.
  """

  media_type = configuration.Field(MediaType, required=True).cast()
  """The media type of the input stream."""

  frame_rate = configuration.Field(float).cast()
  """The frame rate of the input stream, in frames per second.

  Only valid for media_type of 'video'.

  Can be auto-detected for some input types, but may be required for others.
  For example, required for input_type of 'external_command'.
  """

  resolution = configuration.Field(
      bitrate_configuration.VideoResolutionName).cast()
  """The name of the input resolution (1080p, etc).

  Only valid for media_type of 'video'.

  Can be auto-detected for some input types, but may be required for others.
  For example, required for input_type of 'external_command'.
  """

  channel_layout = configuration.Field(
      bitrate_configuration.AudioChannelLayoutName).cast()
  """The name of the input channel layout (stereo, surround, etc)."""

  track_num = configuration.Field(int, default=0).cast()
  """The track number of the input.

  The track number is specific to the media_type.  For example, if there is one
  video track and two audio tracks, media_type of 'audio' and track_num of '0'
  indicates the first audio track, not the first track overall in that file.

  If unspecified, track_num will default to 0, meaning the first track matching
  the media_type field will be used.
  """

  is_interlaced = configuration.Field(bool).cast()
  """True if the input video is interlaced.

  Only valid for media_type of 'video'.

  If true, the video will be deinterlaced during transcoding.

  Can be auto-detected for some input types, but may be default to False for
  others.  For example, an input_type of 'external_command', it will default to
  False.
  """

  language = configuration.Field(str).cast()
  """The language of an audio or text stream.

  With input_type set to 'file' or 'looped_file', this will be auto-detected.
  Otherwise, it will default to 'und' (undetermined).
  """

  start_time = configuration.Field(str).cast()
  """The start time of the slice of the input to use.

  Only valid for VOD and with input_type set to 'file'.

  Not supported with media_type of 'text'.
  """

  end_time = configuration.Field(str).cast()
  """The end time of the slice of the input to use.

  Only valid for VOD and with input_type set to 'file'.

  Not supported with media_type of 'text'.
  """

  drm_label = configuration.Field(str).cast()
  """Optional value for a custom DRM label, which defines the encryption key
  applied to the stream. If not provided, the DRM label is derived from stream
  type (video, audio), resolutions, etc. Note that it is case sensitive.

  Applies to 'raw' encryption_mode only."""

  skip_encryption = configuration.Field(int, default=0).cast()
  """If set, no encryption of the stream will be made"""

  # TODO: Figure out why mypy 0.720 and Python 3.7.5 don't correctly deduce the
  # type parameter here if we don't specify it explicitly with brackets after
  # "Field".
  filters = configuration.Field[List[str]](List[str], default=[]).cast()
  """A list of FFmpeg filter strings to add to the transcoding of this input.

  Each filter is a single string.  For example, 'pad=1280:720:20:20'.

  Not supported with media_type of 'text'.
  """


  def __init__(self, *args) -> None:
    super().__init__(*args)

    # FIXME: A late import to avoid circular dependency issues between these two
    # modules.
    from . import autodetect

    if not autodetect.is_present(self):
      raise InputNotFound(self)

    def require_field(name: str) -> None:
      """Raise MissingRequiredField if the named field is still missing."""
      if getattr(self, name) is None:
        raise configuration.MissingRequiredField(
            self.__class__, name, getattr(self.__class__, name))

    def disallow_field(name: str, reason: str) -> None:
      """Raise MalformedField if the named field is present."""
      if getattr(self, name):
        raise configuration.MalformedField(
            self.__class__, name, getattr(self.__class__, name), reason)

    if self.media_type == MediaType.VIDEO:
      # These fields are required for video inputs.
      # We will attempt to auto-detect them if possible.
      if self.is_interlaced is None:
        self.is_interlaced = autodetect.get_interlaced(self)

      if self.frame_rate is None:
        self.frame_rate = autodetect.get_frame_rate(self)
      require_field('frame_rate')

      if self.resolution is None:
        self.resolution = autodetect.get_resolution(self)
      require_field('resolution')

    if self.media_type == MediaType.AUDIO:
      if self.language is None:
        self.language = autodetect.get_language(self) or 'und'

      if self.channel_layout is None:
        self.channel_layout = autodetect.get_channel_layout(self)
      require_field('channel_layout')

    if self.media_type == MediaType.TEXT:
      if self.language is None:
        self.language = autodetect.get_language(self) or 'und'
      # Text streams are only supported in plain file inputs.
      if self.input_type != InputType.FILE:
        reason = 'text streams are not supported in input_type "{}"'.format(
            self.input_type.value)
        disallow_field('input_type', reason)

      # These fields are not supported with text, because we don't process or
      # transcode it.
      reason = 'not supported with media_type "text"'
      disallow_field('start_time', reason)
      disallow_field('end_time', reason)
      disallow_field('filters', reason)

    if self.input_type != InputType.FILE:
      # These fields are only valid for file inputs.
      reason = 'only valid when input_type is "file"'
      disallow_field('start_time', reason)
      disallow_field('end_time', reason)


  def reset_name(self, pipe_path: str) -> None:
    """Set the name to a pipe path into which this input's contents are fed.
    """

    self.name = pipe_path

  def get_stream_specifier(self) -> str:
    """Get an FFmpeg stream specifier for this input.

    For example, the first video track would be "v:0", and the 3rd text track
    would be "s:2".  Note that all track numbers are per media type in this
    format, not overall track numbers from the input file, and that they are
    indexed starting at 0.

    See also http://ffmpeg.org/ffmpeg.html#Stream-specifiers
    """

    if self.media_type == MediaType.VIDEO:
      return 'v:{}'.format(self.track_num)
    elif self.media_type == MediaType.AUDIO:
      return 'a:{}'.format(self.track_num)
    elif self.media_type == MediaType.TEXT:
      return 's:{}'.format(self.track_num)

    assert False, 'Unrecognized media_type!  This should not happen.'

  def get_input_args(self) -> List[str]:
    """Get any required input arguments for this input.

    These are like hard-coded extra_input_args for certain input types.
    This means users don't have to know much about FFmpeg options to handle
    these common cases.

    Note that for types which support autodetect, these arguments must be
    understood by ffprobe as well as ffmpeg.
    """
    args_matrix: Dict[InputType, Dict[str, List[str]]] = {
        InputType.WEBCAM: {
            'Linux': [
                # Treat the input as a video4linux device, which is how
                # webcams show up on Linux.
                '-f', 'video4linux2',
            ],
            'Darwin': [
                # Webcams on macOS use FFmpeg's avfoundation input format.  With
                # this, you also have to specify an input framerate, unfortunately.
                '-f', 'avfoundation',
                '-framerate', '30',
            ],
            'Windows': [
                # Treat the input as a directshow input device.
                '-f', 'dshow',
            ],
        },
        InputType.MICROPHONE: {
            'Linux': [
                # PulseAudio input device.
                '-f', 'pulse',
            ],
            'Darwin': [
                # AVFoundation also works as an audio input device.
                '-f', 'avfoundation',
            ],
            'Windows': [
                # Directshow also works as an audio input device.
                '-f', 'dshow',
            ],
        },
    }

    args_for_input_type = args_matrix.get(self.input_type)
    # If the input's type wasn't of what interests us.
    if not args_for_input_type:
      return []

    args = args_for_input_type.get(platform.system())
    assert args, '{} is not supported on this platform!'.format(self.input_type.value)

    return args

  def get_resolution(self) -> bitrate_configuration.VideoResolution:
    return bitrate_configuration.VideoResolution.get_value(self.resolution)

  def get_channel_layout(self) -> bitrate_configuration.AudioChannelLayout:
    return bitrate_configuration.AudioChannelLayout.get_value(self.channel_layout)

class SinglePeriod(configuration.Base):
  """An object representing a single period in a multiperiod inputs list."""

  inputs = configuration.Field(List[Input], required=True).cast()

class InputConfig(configuration.Base):
  """An object representing the entire input config to Shaka Streamer."""

  multiperiod_inputs_list = configuration.Field(List[SinglePeriod]).cast()
  """A list of SinglePeriod objects"""

  inputs = configuration.Field(List[Input]).cast()
  """A list of Input objects"""

  def __init__(self, dictionary: Dict[str, Any]):
    """A constructor to check that either inputs or mutliperiod_inputs_list is provided,
    and produce a helpful error message in case both or none are provided.

    We need these checks before passing the input dictionary to the configuration.Base constructor,
    because it does not check for this 'exclusive or-ing' relationship between fields.
    """

    assert isinstance(dictionary, dict), """Malformed Input Config File,
    See some examples at https://github.com/google/shaka-streamer/tree/master/config_files.
    """

    if (dictionary.get('inputs') is not None
        and dictionary.get('multiperiod_inputs_list') is not None):
      raise configuration.ConflictingFields(
        InputConfig, 'inputs', 'multiperiod_inputs_list')

    # Because these fields are not marked as required at the class level
    # , we need to check ourselves that one of them is provided.
    if not dictionary.get('inputs') and not dictionary.get('multiperiod_inputs_list'):
      raise configuration.MissingRequiredExclusiveFields(
        InputConfig, 'inputs', 'multiperiod_inputs_list')

    super().__init__(dictionary)

