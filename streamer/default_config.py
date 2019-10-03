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

"""A file with the default configs."""

import base64
import os

from . import metadata

INPUT_DEFAULT_CONFIG = {
  # List of inputs. Each one is a dictionary.
  'inputs': [
    {
      # Name of the input file.
      # For input_type == 'external_command', this is the command to be
      # executed, which should follow shell quoting rules.
      'name': 'test_assets/BigBuckBunny.1080p.mp4',
      # Type of input. To be used only for live. Can be looped_file, raw_images
      # or webcam.
      'input_type': 'looped_file',
      # For input_type == 'external_command', extra input arguments needed to
      # understand the output of the external command.  This allows you the
      # external command to output almost anything ffmpeg could ingest.
      'extra_input_args': '',
      # The type of media for the input. Can be audio or video.
      'media_type': 'video',
      # Frame rate per second.
      'frame_rate': 24.0,
      # The input resolution.
      'resolution': '1080p',
      # The track number.
      'track_num': 0,
      # Whether or not the video is interlaced.
      'is_interlaced': False,
      # Language of the audio stream.
      # TODO: Add different default config input entries for audio, video and
      # text entries so that fields match up with each type of entry.
      'language': 'und',
      # Start time of VOD input to encode.
      'start_time': '',
      # End time of VOD input to encode.
      'end_time': '',
      # An arbitrary set of filters to pass to ffmpeg for this input.
      # For example, 'pad=1280:720:20:20'.
      'filters': [],
    },
  ],
}

# Contains sets of valid values for certain fields in the inputs list.
INPUT_VALID_VALUES = {
  'input_type': {'raw_images', 'looped_file', 'webcam', 'external_command'},
  'media_type': {'audio', 'video', 'text'},
}

OUTPUT_DEFAULT_CONFIG = {
  # Mode of streaming. Can either be live or vod.
  'streaming_mode': 'live',
  # If true, reduce the level of output.  Only errors will be shown in quiet
  # mode.
  'quiet': False,
  # If true, output simple log files from each node.  No control is given over
  # log filenames.  Logs are written to the current working directory.  We do
  # not yet support log rotation.  This is meant only for debugging.
  'debug_logs': False,

  'transcoder': {
    # A list of resolutions to encode.
    'resolutions': [
      '720p',
      '480p',
    ],
    # The number of audio channels to encode with.
    'channels': 2,
    # The codecs to encode with.
    'audio_codecs': [
      'aac',
    ],
    'video_codecs': [
      'h264',
    ],
  },
  'packager': {
    # Manifest format (dash, hls).
    'manifest_format': [
      'dash',
      'hls',
    ],
    # Output filenames for DASH manifest & HLS master playlist.
    'dash_output': 'dash.mpd',
    'hls_output': 'hls.m3u8',
    # Sub-folder for segment output (or blank for none).
    'segment_folder': '',

    # Length of each segment in seconds.
    'segment_size': 4,
    # Forces the use of SegmentTemplate in DASH.
    'segment_per_file': True,
    # Availability window, or the number of seconds a segment remains available.
    'availability_window': 300,
    # Presentation delay, or how far back from the edge the player should be.
    'presentation_delay': 30,
    # Update period, or how often the player should fetch a new manifest.
    'update_period': 8,

    'encryption': {
      # Enables encryption.
      # If disabled, the following settings are ignored.
      'enable': False,
      # Content identifier that identifies which encryption key to use.
      'content_id': base64.b16encode(os.urandom(16)).decode('UTF-8'),
      # Key server url.  An encryption key is generated from this server.
      'key_server_url': 'https://license.uat.widevine.com/cenc/getcontentkey/widevine_test',
      # The name of the signer.
      'signer': 'widevine_test',
      # AES signing key in hex string.
      'signing_key': '1ae8ccd0e7985cc0b6203a55855a1034afc252980e970ca90e5202689f947ab9',
      # AES signing iv in hex string.
      'signing_iv': 'd58ce954203b7c9a9a9d467f59839249',
      # Protection scheme (cenc or cbcs)
      # These are different methods of using a block cipher to encrypt media.
      'protection_scheme': 'cenc',
      # Seconds of unencrypted media at the beginning of the stream.
      'clear_lead': 10,
    },
  },
}

# Contains sets of valid values for certain fields in the output config.
OUTPUT_VALID_VALUES = {
  'streaming_mode': {'live', 'vod'},
  'manifest_format': {'dash', 'hls'},
  'protection_scheme': {'cenc', 'cbcs'},
  'resolutions': metadata.RESOLUTION_MAP.keys(),
  'audio_codecs': {'aac', 'opus'},
  'video_codecs': {'h264', 'vp9', 'hw:h264', 'hw:vp9'},
}
