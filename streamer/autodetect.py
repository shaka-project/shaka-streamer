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

import json
import shlex
import subprocess
import time

from streamer.bitrate_configuration import (
    AudioChannelLayout, AudioChannelLayoutName,
    VideoResolution, VideoResolutionName)
from streamer.input_configuration import Input, InputType
from typing import Optional, List, Tuple, Dict

# These cannot be probed by ffprobe.
TYPES_WE_CANT_PROBE = [
  InputType.EXTERNAL_COMMAND,
]

# This module level variable might be set by the controller node
# if the user chooses to use the shaka streamer bundled binaries.
hermetic_ffprobe: Optional[str] = None

def _probe(media_input: Input, field: str) -> Optional[str]:
  """Autodetect some feature of the input, if possible, using ffprobe.

  Args:
    input (Input): An input object from input_configuration.
    field (str): A field to pass to ffprobe's -show_entries option.

  Returns:
    The requested field from ffprobe as a string, or None if this fails.
  """

  if media_input.input_type in TYPES_WE_CANT_PROBE:
    # Not supported for this type.
    return None

  args: List[str] = [
      # Probe this input file
      hermetic_ffprobe or 'ffprobe',
      media_input.name,
  ]

  # Add any required input arguments for this input type
  args += media_input.get_input_args()

  args += [
      # Specifically, this stream
      '-select_streams', media_input.get_stream_specifier(),
      # Show the needed metadata only
      '-show_entries', field,
      # Print the metadata in a compact form, which is easier to parse
      '-of', 'compact=p=0:nk=1'
  ]

  print('+ ' + ' '.join([shlex.quote(arg) for arg in args]))

  output_bytes: bytes = subprocess.check_output(args, stderr=subprocess.DEVNULL)
  # The output is either some probe information or just a blank line.
  output_string: str = output_bytes.decode('utf-8').strip()
  # With certain container formats, ffprobe returns a duplicate
  # output and some empty lines in between. Issue #119
  output_string = output_string.split('\n', maxsplit=1)[0]
  # After stripping the newline, we can fall back to None if it's empty.
  probe_output: Optional[str] = output_string or None

  # Webcams on Linux seem to behave badly if the device is rapidly opened and
  # closed.  Therefore, sleep for 1 second after a webcam probe.
  if media_input.input_type == InputType.WEBCAM:
    time.sleep(1)

  return probe_output

def is_present(media_input: Input) -> bool:
  """Returns true if the stream for this input is indeed found.

  If we can't probe this input type, assume it is present."""

  return bool(_probe(media_input, 'stream=index') or
              media_input.input_type in TYPES_WE_CANT_PROBE)

def get_language(media_input: Input) -> Optional[str]:
  """Returns the autodetected the language of the input."""
  return _probe(media_input, 'stream_tags=language')

def get_interlaced(media_input: Input) -> bool:
  """Returns True if we detect that the input is interlaced."""
  interlaced_string = _probe(media_input, 'stream=field_order')

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

def get_frame_rate(media_input: Input) -> Optional[float]:
  """Returns the autodetected frame rate of the input."""

  frame_rate_string = _probe(media_input, 'stream=avg_frame_rate')
  if frame_rate_string is None:
    return None

  # This string is the framerate in the form of a fraction, such as '24/1' or
  # '30000/1001'.  Occasionally, there is a pipe after the framerate, such as
  # '32700/1091|'.  We must split it into pieces and do the division to get a
  # float.
  fraction = frame_rate_string.rstrip('|').split('/')
  if len(fraction) == 1:
    frame_rate = float(fraction[0])
  else:
    frame_rate = float(fraction[0]) / float(fraction[1])

  # The detected frame rate for interlaced content is twice what it should be.
  # It's actually the field rate, where it takes two interlaced fields to make
  # a frame.  Because we have to know if it's interlaced already, we must
  # assert that is_interlaced has been set before now.
  assert media_input.is_interlaced is not None
  if media_input.is_interlaced:
    frame_rate /= 2.0

  return frame_rate

def get_resolution(media_input: Input) -> Optional[VideoResolutionName]:
  """Returns the autodetected resolution of the input."""

  resolution_string = _probe(media_input, 'stream=width,height')
  if resolution_string is None:
    return None

  # This is the resolution of the video in the form of 'WIDTH|HEIGHT'.  For
  # example, '1920|1080'.  Occasionally, there is a pipe after the resolution,
  # such as '1920|1080|'.  We have to split up width and height and match that
  # to a named resolution.
  width_string, height_string = resolution_string.rstrip('|').split('|')
  width, height = int(width_string), int(height_string)

  for bucket in VideoResolution.sorted_values():
    # The first bucket this fits into is the one.
    if (width <= bucket.max_width and height <= bucket.max_height and
        media_input.frame_rate <= bucket.max_frame_rate):
      return bucket.get_key()

  return None

def get_channel_layout(media_input: Input) -> Optional[AudioChannelLayoutName]:
  """Returns the autodetected channel count of the input."""

  channel_count_string = _probe(media_input, 'stream=channels')
  if channel_count_string is None:
    return None

  channel_count = int(channel_count_string)
  for bucket in AudioChannelLayout.sorted_values():
    if channel_count <= bucket.max_channels:
      return bucket.get_key()

  return None

def get_forced_subtitle(media_input: Input) -> bool:
  """Returns the forced subtitle value of the input."""

  forced_subtitle_string = _probe(media_input, 'disposition=forced')

  if forced_subtitle_string is None:
    return False

  # ffprobe reports disposition flags in compact format (p=0:nk=1) as
  # pipe-separated values without keys, e.g. for a forced subtitle stream:
  #   subtitle|2|0|0|0|0|0|0|0|1|0|...
  # The "forced" disposition field is output as the plain string "1" when
  # forced, and "0" otherwise. We must check for exactly "1" rather than
  # using bool(), which would return True for any non-empty string.
  return forced_subtitle_string == '1'

def get_tracks(filename: str) -> List[Tuple[str, int]]:
  """Probes *filename* and returns one tuple per detectable stream.

  Args:
    filename: Path to the media file.

  Returns:
    List of (media_type_value, track_num) where media_type_value is the
    string value of the MediaType enum ('audio', 'video', or 'text') and
    track_num is a zero-based index that counts only within that type.
    Streams of unknown codec_type ('data', 'attachment', …) are skipped.
  """

  # Map ffprobe codec_type strings → MediaType enum string values.
  # We return string values (not MediaType instances) so
  # _expand_autodetect_inputs can put them straight into the raw dict
  # without importing MediaType here.
  codec_type_to_value: Dict[str, str] = {
    'audio':    'audio',
    'video':    'video',
    'subtitle': 'text',
  }

  args: List[str] = [
    hermetic_ffprobe or 'ffprobe',
    '-show_entries',
    'stream=codec_type:stream_disposition=attached_pic',
    '-of',
    'json',
    filename,
  ]

  print('+ ' + ' '.join([shlex.quote(arg) for arg in args]))

  try:
    output_bytes = subprocess.check_output(args, stderr=subprocess.DEVNULL)
    data = json.loads(output_bytes)
  except (subprocess.CalledProcessError, json.JSONDecodeError):
    return []

  type_counts: Dict[str, int] = {'audio': 0, 'video': 0, 'text': 0}
  tracks: List[Tuple[str, int]] = []

  for stream in data.get('streams', []):
    codec_type = stream.get('codec_type')
    disposition = stream.get('disposition', {})

    if disposition.get('attached_pic') == 1:
      continue

    media_type_value = codec_type_to_value.get(codec_type)

    if media_type_value is None:
      continue

    track_num = type_counts[media_type_value]
    type_counts[media_type_value] += 1

    tracks.append((media_type_value, track_num))

  return tracks
