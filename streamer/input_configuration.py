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
import shlex

from . import configuration
from . import metadata


class InputType(enum.Enum):
  FILE = 'file'
  """A track from a file.  Usable only with VOD."""

  LOOPED_FILE = 'looped_file'
  """A track from a file, looped forever by FFmpeg.  Usable only with live."""

  WEBCAM = 'webcam'
  """A webcam device.  Usable only with live.

  The device path should be given in the name field.  For example, on Linux,
  this might be /dev/video0.
  """

  RAW_IMAGES = 'raw_images'
  """A file or pipe with a sequence of raw images.

  Requires the specification of frame_rate.  May require the use of
  extra_input_args if FFmpeg can't guess the format.
  """

  EXTERNAL_COMMAND = 'external_command'
  """An external command that generates a stream of audio or video.

  The command should be given in the name field, using shell quoting rules.
  The command should send its generated output to the path in the environment
  variable $SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT, which Shaka Streamer set to
  the path to the output pipe.

  May require the user of extra_input_args if FFmpeg can't guess the format or
  framerate.
  """

class MediaType(enum.Enum):
  AUDIO = 'audio'
  VIDEO = 'video'
  TEXT = 'text'


# A runtime-created enum for valid resolutions, based on the |metadata| module.
Resolution = configuration.enum_from_keys('Resolution', metadata.RESOLUTION_MAP)


class Input(configuration.Base):
  """An object representing a single input stream to Shaka Streamer."""

  input_type = configuration.Field(InputType, default=InputType.FILE)
  """The type of the input."""

  name = configuration.Field(str, required=True)
  """Name of the input.

  With input_type set to 'file', this is a path to a file name.

  With input_type set to 'looped_file', this is a path to a file name to be
  looped indefinitely in FFmpeg.

  With input_type set to 'webcam', this is a path to the device node for the
  webcam.  For example, on Linux, this might be /dev/video0.

  With input_type set to 'raw_images', this is a path to a file or pipe
  containing a sequence of raw images.

  With input_type set to 'external_command', this is an external command that
  generates a stream of audio or video.  The command will be parsed using shell
  quoting rules.  The command should send its generated output to the path in
  the environment variable $SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT, which Shaka
  Streamer set to the path to the output pipe.
  """

  extra_input_args = configuration.Field(str, default='')
  """Extra input arguments needed by FFmpeg to understand the input.

  This allows you to take inputs that cannot be understand or detected
  automatically by FFmpeg.

  This string will be parsed using shell quoting rules.
  """

  media_type = configuration.Field(MediaType, required=True)
  """The media type of the input stream."""

  # TODO: detect frame rate if not given, require only for raw_images
  frame_rate = configuration.Field(float)
  """The frame rate of the input stream, in frames per second.

  Required for media_type of 'video'.
  """

  # TODO: detect resolution if not given
  # TODO: support custom resolutions
  resolution = configuration.Field(Resolution)
  """The name of the input resolution (1080p, etc).

  Required for media_type of 'video'.
  """

  # TODO: detect track number based on media_type
  track_num = configuration.Field(int, default=0)
  """The track number of the input.  Defaults to 0.

  For multiplexed input files, video is usually track 0, and the first audio
  track is usually track 1.  This may vary, though.
  """

  is_interlaced = configuration.Field(bool, default=False)
  """True if the input video is interlaced.

  If true, the video will be deinterlaced during transcoding.
  """

  language = configuration.Field(str)
  """The language of an audio or text stream.

  With input_type set to 'file' or 'looped_file', this will be auto-detected.
  Otherwise, it will default to 'und' (undetermined).
  """

  start_time = configuration.Field(str)
  """The start time of the slice of the input to use.

  Only valid for VOD and with input_type set to 'file'.
  """

  end_time = configuration.Field(str)
  """The end time of the slice of the input to use.

  Only valid for VOD and with input_type set to 'file'.
  """

  filters = configuration.Field(list, subtype=str, default=[])
  """A list of FFmpeg filter strings to add to the transcoding of this input.

  Each filter is a single string.  For example, 'pad=1280:720:20:20'.
  """


  def __init__(self, *args):
    super().__init__(*args)

    if self.media_type == MediaType.VIDEO:
      # These fields are required for video inputs.
      if self.frame_rate is None:
        raise configuration.MissingRequiredField(
            self.__class__, 'frame_rate', self.__class__.frame_rate)

      if self.resolution is None:
        raise configuration.MissingRequiredField(
            self.__class__, 'resolution', self.__class__.resolution)

    if self.input_type != InputType.FILE:
      # These fields are only valid for file inputs.
      reason = 'only valid when input_type is "file"'

      if self.start_time:
        field = self.__class__.start_time
        raise configuration.MalformedField(
            self.__class__, 'start_time', field, reason)

      if self.end_time:
        field = self.__class__.end_time
        raise configuration.MalformedField(
            self.__class__, 'end_time', field, reason)

    # This needs to be parsed into an argument array.  Note that shlex.split on
    # an empty string will produce an empty array.
    self.extra_input_args = shlex.split(self.extra_input_args)

    # A path to a pipe into which this input's contents are fed.
    # None for most input types.
    self._pipe = None

  def set_pipe(self, pipe):
    """Set the path to a pipe into which this input's contents are fed.

    If set, this is what TranscoderNode will read from instead of .name.
    """
    self._pipe = pipe

  def get_path_for_transcode(self):
    """Get the path which the transcoder will use to read the input.

    For some input types, this is a named pipe.  For others, this is .name.
    """
    return self._pipe or self.name


class InputConfig(configuration.Base):
  """An object representing the entire input config to Shaka Streamer."""

  inputs = configuration.Field(list, subtype=Input, required=True)
  """A list of Input objects, one per input stream."""

