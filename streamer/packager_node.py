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

"""A module that feeds information from two named pipes into shaka-packager."""

from . import metadata
from . import node_base

MP4_AUDIO_INIT_SEGMENT = '{dir}/audio_{channels}_{bitrate}_init.mp4'
WEBM_AUDIO_INIT_SEGMENT = '{dir}/audio_{channels}_{bitrate}_init.webm'
MP4_AUDIO_SEGMENT_TEMPLATE = '{dir}/audio_{channels}_{bitrate}_$Number$.m4s'
WEBM_AUDIO_SEGMENT_TEMPLATE = '{dir}/audio_{channels}_{bitrate}_$Number$.webm'
MP4_AUDIO_OUTPUT = '{dir}/audio_{channels}_{bitrate}_output.mp4'
WEBM_AUDIO_OUTPUT = '{dir}/audio_{channels}_{bitrate}_output.webm'
MP4_VIDEO_INIT_SEGMENT = '{dir}/video_{res}_{bitrate}_init.mp4'
WEBM_VIDEO_INIT_SEGMENT = '{dir}/video_{res}_{bitrate}_init.webm'
MP4_VIDEO_SEGMENT_TEMPLATE = '{dir}/video_{res}_{bitrate}_$Number$.m4s'
WEBM_VIDEO_SEGMENT_TEMPLATE = '{dir}/video_{res}_{bitrate}_$Number$.webm'
MP4_VIDEO_OUTPUT = '{dir}/video_{res}_{bitrate}_output.mp4'
WEBM_VIDEO_OUTPUT = '{dir}/video_{res}_{bitrate}_output.webm'

TEXT_INIT_SEGMENT = '{dir}/text_{lang}_init.mp4'
TEXT_SEGMENT_TEMPLATE = '{dir}/text_{lang}_$Number$.m4s'
TEXT_OUTPUT = '{dir}/text_{lang}_output.mp4'

DASH_OUTPUT = '/output.mpd'
HLS_OUTPUT = '/master_playlist.m3u8'

class SegmentError(Exception):
  """Raise when segment is incompatible with format."""
  pass

class PackagerNode(node_base.NodeBase):

  def __init__(self, audio_inputs, video_inputs, text_inputs, output_dir, config):
    node_base.NodeBase.__init__(self)
    self._audio_inputs = audio_inputs
    self._video_inputs = video_inputs
    self._text_inputs = text_inputs
    self._output_dir = output_dir
    self._config = config

  def start(self):
    args = [
        'packager',
    ]

    for input in self._audio_inputs:
      audio_dict = {'in': input.pipe, 'stream': 'audio'}
      if input.lang != 'und':
        audio_dict['language'] = input.lang
      args += self._create_audio(audio_dict, input)

    for input in self._video_inputs:
      video_dict = {'in': input.pipe, 'stream': 'video'}
      args += self._create_video(video_dict, input)

    for input in self._text_inputs:
      text_dict = {
          'in': input.get_name(),
          'stream': 'text',
          'language': input.get_language(),
      }
      args += self._create_text(text_dict, input.get_language())

    args += [
        # Segment duration given in seconds.
        '--segment_duration', str(self._config.packager['segment_size']),
    ]

    if self._config.mode == 'live':
      args += [
          # Number of seconds the user can rewind through backwards.
          '--time_shift_buffer_depth',
          str(self._config.packager['availability_window']),
          # Number of segments preserved outside the current live window.
          '--preserved_segments_outside_live_window', '1',
          # Number of seconds of content encoded/packaged that is ahead of the
          # live edge.
          '--suggested_presentation_delay',
          str(self._config.packager['presentation_delay']),
      ]

    args += self._setup_manifest_format()

    args += [
        # use an IO block size of ~65K for a threaded IO file.
        '--io_block_size', '65536',
    ]

    if self._config.encryption['enable']:
      args += self._setup_encryption()

    self._process = self._create_process(args)

  def _create_text(self, text_dict, language):
    if self._config.packager['segment_per_file']:
      text_dict['init_segment'] = (TEXT_INIT_SEGMENT.
          format(dir=self._output_dir, lang=language))
      text_dict['segment_template'] = (TEXT_SEGMENT_TEMPLATE.
          format(dir=self._output_dir, lang=language))
    else:
      text_dict['output'] = (TEXT_OUTPUT.
          format(dir=self._output_dir, lang=language))
    return [_packager_stream_arg(text_dict)]

  def _create_audio(self, dict, audio):
    if self._config.packager['segment_per_file']:
      if audio.audio_codec == 'aac':
        self._setup_segmented_output(dict, MP4_AUDIO_INIT_SEGMENT,
            MP4_AUDIO_SEGMENT_TEMPLATE, 'channels', audio.channels,
            metadata.CHANNEL_MAP[audio.channels].aac_bitrate)
      elif audio.audio_codec == 'opus':
        self._setup_segmented_output(dict, WEBM_AUDIO_INIT_SEGMENT,
            WEBM_AUDIO_SEGMENT_TEMPLATE, 'channels', audio.channels,
            metadata.CHANNEL_MAP[audio.channels].opus_bitrate)
    else:
      if self._config.mode == 'vod':
        if audio.audio_codec == 'aac':
          self._setup_single_file_output(dict, MP4_AUDIO_OUTPUT, 'channels',
              audio.channels, metadata.CHANNEL_MAP[audio.channels].aac_bitrate)
        elif audio.audio_codec == 'opus':
          self._setup_single_file_output(dict, MP4_AUDIO_OUTPUT, 'channels',
              audio.channels, metadata.CHANNEL_MAP[audio.channels].opus_bitrate)
      else:
        # Live mode doesn't support a non-segment video.
        raise SegmentError('Non segment does not work with LIVE')
    return [_packager_stream_arg(dict)]

  def _create_video(self, dict, video):
    if self._config.packager['segment_per_file']:
      if video.video_codec == 'h264':
        self._setup_segmented_output(dict, MP4_VIDEO_INIT_SEGMENT,
            MP4_VIDEO_SEGMENT_TEMPLATE, 'res', video.res,
            video.resolution_data.h264_bitrate)
      elif video.video_codec == 'vp9':
        self._setup_segmented_output(dict, WEBM_VIDEO_INIT_SEGMENT,
            WEBM_VIDEO_SEGMENT_TEMPLATE, 'res', video.res,
            video.resolution_data.vp9_bitrate)
    else:
      if self._config.mode == 'vod':
        if video.video_codec == 'h264':
          self._setup_single_file_output(dict, MP4_VIDEO_OUTPUT, 'res',
              video.res, metadata.RESOLUTION_MAP[video.res].h264_bitrate)
        elif video.video_codec == 'vp9':
          self._setup_single_file_output(dict, WEBM_VIDEO_OUTPUT, 'res',
              video.res, metadata.RESOLUTION_MAP[video.res].vp9_bitrate)
      else:
        raise SegmentError("Non segment does not work with LIVE")
    return [_packager_stream_arg(dict)]

  def _setup_segmented_output(self, dict, init_segment_name, segment_name,
                              channels_or_res, channel_or_res_info,
                              bitrate_info):
    if channels_or_res == 'channels':
      # Set the initial segment.
      dict['init_segment'] = (init_segment_name.
          format(dir=self._output_dir, channels=channel_or_res_info,
                bitrate=bitrate_info))
      # Create the individual segments.
      dict['segment_template'] = (segment_name.
          format(dir=self._output_dir, channels=channel_or_res_info,
                bitrate=bitrate_info))
    elif channels_or_res == 'res':
      dict['init_segment'] = (init_segment_name.
          format(dir=self._output_dir, res=channel_or_res_info,
                 bitrate=bitrate_info))
      dict['segment_template'] = (segment_name.
          format(dir=self._output_dir, res=channel_or_res_info,
                 bitrate=bitrate_info))

  def _setup_single_file_output(self, dict, file_name, channels_or_res,
                                channel_or_res_info, bitrate_info):
    if channels_or_res == 'channels':
      dict['output'] = (file_name.format(dir=self._output_dir,
                                         channels=channel_or_res_info,
                                         bitrate=bitrate_info))
    elif channels_or_res == 'res':
      dict['output'] = (file_name.format(dir=self._output_dir,
                                         res=channel_or_res_info,
                                         bitrate=bitrate_info))

  def _setup_manifest_format(self):
    args = []
    if 'dash' in self._config.packager['manifest_format']:
      if self._config.mode == 'vod':
        args += [
            '--generate_static_mpd',
        ]
      args += [
          # Generate DASH manifest file.
          '--mpd_output', self._output_dir + DASH_OUTPUT,
      ]
    if 'hls' in self._config.packager['manifest_format']:
      args += [
          # Generate HLS manifest file.
          '--hls_master_playlist_output',
          self._output_dir + HLS_OUTPUT,
      ]
      if self._config.mode == 'live':
        args += [
            '--hls_playlist_type', 'LIVE',
        ]
      else:
        args += [
            '--hls_playlist_type', 'VOD',
        ]
    return args

  def _setup_encryption(self):
    # Sets up encryption of content.
    args = [
      '--enable_widevine_encryption',
      '--key_server_url', self._config.encryption['key_server_url'],
      '--content_id', self._config.encryption['content_id'],
      '--signer', self._config.encryption['signer'],
      '--aes_signing_key', self._config.encryption['signing_key'],
      '--aes_signing_iv', self._config.encryption['signing_iv'],
      '--protection_scheme', self._config.encryption['protection_scheme'],
      '--clear_lead', str(self._config.encryption['clear_lead']),
    ]
    return args


def _packager_stream_arg(opts):
  ret = ''
  for key, value in opts.items():
    ret += key + '=' + value + ','
  return ret

