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

"""A module to contain auto-detection logic; based on ffprobe."""

import subprocess

from . import input_configuration
from . import metadata

# Alias a few classes to avoid repeating namespaces later.
InputType = input_configuration.InputType

# These cannot be probed by ffprobe.
TYPES_WE_CANT_PROBE = [
  InputType.EXTERNAL_COMMAND,
  InputType.RAW_IMAGES,
  InputType.WEBCAM,  # TODO: Can we actually probe webcam inputs? Needs testing.
]


def _probe(input, field):
  """Autodetect some feature of the input, if possible, using ffprobe.

  Args:
    input (Input): An input object from input_configuration.
    field (str): A field to pass to ffprobe's -show_entries option.

  Returns:
    The requested field from ffprobe as a string, or None if this fails.
  """

  if input.input_type in TYPES_WE_CANT_PROBE:
    # Not supported for this type.
    return None

  command = [
      # Probe this input file
      'ffprobe', input.name,
      # Specifically, this stream
      '-select_streams', input.get_stream_specifier(),
      # Show the needed metadata only
      '-show_entries', field,
      # Print the metadata in a compact form, which is easier to parse
      '-of', 'compact=p=0:nk=1'
  ]

  output_bytes = subprocess.check_output(command, stderr=subprocess.DEVNULL)
  # The output is either the language code or just a blank line.
  output_string = output_bytes.decode('utf-8').strip()
  # After stripping the newline, we can fall back to None if it's empty.
  return output_string or None


def get_language(input):
  """Returns the autodetected the language of the input."""
  return _probe(input, 'stream_tags=language')

def get_interlaced(input):
  """Returns True if we detect that the input is interlaced."""
  interlaced_string = _probe(input, 'stream=field_order')

  # These constants represent the order of the fields (2 fields per frame) of
  # different types of interlaced video.  They can be found in
  # https://www.ffmpeg.org/ffmpeg-codecs.html under the description of the
  # field_order option.  Anything else (including None) should be considered
  # progressive (non-interlaced) video.
  return interlaced_string in [
    'tt',
    'bb',
    'tb',
    'bt',
  ]

def get_frame_rate(input):
  """Returns the autodetected frame rate of the input."""

  frame_rate_string = _probe(input, 'stream=r_frame_rate')
  if frame_rate_string is None:
    return None

  # This string is the framerate in the form of a fraction, such as '24/1' or
  # '30000/1001'.  We must split it into pieces and do the division to get a
  # float.
  fraction = frame_rate_string.split('/')
  if len(fraction) == 1:
    frame_rate = float(fraction)
  else:
    frame_rate = float(fraction[0]) / float(fraction[1])

  # The detected frame rate for interlaced content is twice what it should be.
  # It's actually the field rate, where it takes two interlaced fields to make
  # a frame.  Because we have to know if it's interlaced already, we must
  # assert that is_interlaced has been set before now.
  assert input.is_interlaced is not None
  if input.is_interlaced:
    frame_rate /= 2.0

  return frame_rate

def get_resolution(input):
  """Returns the autodetected resolution of the input."""

  resolution_string = _probe(input, 'stream=width,height')
  if resolution_string is None:
    return None

  # This is the resolution of the video in the form of 'WIDTH|HEIGHT'.  For
  # example, '1920|1080'.  We have to split up width and height and match that
  # to a named resolution.
  width_string, height_string = resolution_string.split('|')
  width, height = int(width_string), int(height_string)
  input_resolution = (width, height)

  for key, value in metadata.RESOLUTION_MAP.items():
    resolution = (value.width, value.height)
    frame_rate = value.frame_rate

    # The first bucket this fits into is the one.
    if input_resolution <= resolution and input.frame_rate <= frame_rate:
      return input_configuration.Resolution(key)

  return None

