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

"""A module that pushes input to ffmpeg to transcode into various formats."""

from . import input_configuration
from . import metadata
from . import node_base

# For H264, there are different profiles with different required command line
# arguments.
profile_args = {
  'baseline': ['-profile:v', 'baseline', '-level:v', '3.0'],
  'main': ['-profile:v', 'main', '-level:v', '3.1'],
  'high': ['-profile:v', 'high', '-level:v', '4.0'],
  'uhd': ['-profile:v', 'high', '-level:v', '5.1'],
}

class TranscoderNode(node_base.NodeBase):

  def __init__(self, inputs, output_audios, output_videos, input_config, config):
    node_base.NodeBase.__init__(self)
    self._inputs = inputs
    self._output_audios = output_audios
    self._output_videos = output_videos
    self._input_config = input_config
    self._config = config

  def start(self):
    args = [
        'ffmpeg',
        # Do not prompt for output files that already exist. Since we created
        # the named pipe in advance, it definitely already exists. A prompt
        # would block ffmpeg to wait for user input.
        '-y',
    ]

    if any([output.hardware for output in self._output_videos]):
      args += [
          # Hardware acceleration args.
          '-hwaccel', 'vaapi',
          '-vaapi_device', '/dev/dri/renderD128',
      ]

    for i in range(len(self._inputs)):
      input = self._input_config.inputs[i]

      if self._config.mode == 'live':
        args += self._live_input(input)

      if input.get_start_time():
        args += [
            # Encode from intended starting time of the VOD input.
            '-ss', input.get_start_time(),
        ]
      if input.get_end_time():
        args += [
            # Encode until intended ending time of the VOD input.
            '-to', input.get_end_time(),
        ]

      # The input name always comes after the applicable input arguments.
      args += [
          # The input itself.
          '-i', self._inputs[i],
      ]

      # Check if the media type of the input is audio and if there are expected
      # outputs for the audio input.
      if input.get_media_type() == 'audio' and self._output_audios:
        for audio in self._output_audios:
          if self._config.mode == 'vod':
            args += [
                # Map corresponding stream to output file.
                '-map', '0:{0}'.format(input.get_track()),
            ]
          args += self._encode_audio(audio, audio.audio_codec, audio.channels,
                                     metadata.CHANNEL_MAP[audio.channels])

      # Check if the media type of the input is video and if there are expected
      # outputs for the video input.
      if input.get_media_type() == 'video' and self._output_videos:
        for video in self._output_videos:
          if self._config.mode == 'vod':
            args += [
                # Map corresponding stream to output file.
                '-map', '0:{0}'.format(input.get_track()),
            ]
          group_of_pictures = int(self._config.packager['segment_size'] *
                                  input.get_frame_rate())
          args += self._encode_video(video, video.video_codec,
                                     group_of_pictures,
                                     metadata.RESOLUTION_MAP[video.res],
                                     input.get_frame_rate(),
                                     input.get_interlaced())

    self._process = self._create_process(args)

  def _live_input(self, input_object):
    args = []
    if input_object.get_input_type() == 'looped_file':
      pass
    elif input_object.get_input_type() == 'raw_images':
      args += [
          # Format the input as a stream of images fed into a pipe.
          '-f', 'image2pipe',
          # Assumes the images are in ppm raw format.
          '-vcodec', 'ppm',
          # Set the frame rate to the one specified in the input config.
          '-r', str(input_object.get_frame_rate()),
      ]
    elif input_object.get_input_type() == 'webcam':
      args += [
          # Format the input using the webcam format.
          '-f', 'video4linux2',
      ]
    args += [
        # A larger queue to buffer input from the pipeline (default is 8).
        '-thread_queue_size', '16000',
    ]
    return args

  def _encode_audio(self, audio, codec, channels, channel_map):
    args = [
        # No video encoding for audio.
        '-vn',
        # Set the number of channels to the one specified in the VOD config
        # file.
        '-ac', str(channels),
    ]

    if channels == 6:
      args += [
        # Work around for https://github.com/google/shaka-packager/issues/598,
        # as seen on https://trac.ffmpeg.org/ticket/6974
        '-af', 'channelmap=channel_layout=5.1',
      ]

    if codec == 'aac':
      args += [
          # Format with MPEG-TS for a pipe.
          '-f', 'mpegts',
          # AAC audio codec.
          '-c:a', 'aac',
          # Set bitrate to the one specified in the VOD config file.
          '-b:a', '{0}k'.format(channel_map.aac_bitrate),
          # Reorder mp4 segments so that the moov segment is at the front.
          # Needed for output to a pipe.
          '-movflags', '+faststart',
      ]
    elif codec == 'opus':
      args += [
          # Opus encoding has output format webm.
          '-f', 'webm',
          # Opus audio codec.
          '-c:a', 'libopus',
          # Set bitrate to the one specified in the VOD config file.
          '-b:a', '{0}k'.format(channel_map.opus_bitrate),
          # DASH-compatible output format.
          '-dash', '1',
      ]
    args += [
        # The output.
        audio.pipe,
    ]
    return args

  def _encode_video(self, video, codec, gop_size, res_map, frame_rate,
                    is_interlaced):
    filters = []
    args = [
        # No audio encoding for video.
        '-an',
        # Full pelME compare function.
        '-cmp', 'chroma',
    ]
    #TODO: auto detection of interlacing
    if is_interlaced:
      # Sanity check: since interlaced files are made up of two interlaced
      # frames, the frame rate must be even and not too small.
      assert frame_rate % 2 == 0 and frame_rate >= 48
      filters.append('pp=fd')
      args.extend(['-r', str(frame_rate / 2)])

    if video.hardware:
      filters.append('format=nv12')
      filters.append('hwupload')
      filters.append('scale_vaapi={0}:{1}'.format(-2, res_map.height))
    else:
      filters.append('scale={0}:{1}'.format(-2, res_map.height))

    if codec == 'h264':
      args += [
          # MPEG-TS format works well in a pipe.
          '-f', 'mpegts',
      ]

      if self._config.mode == 'live':
        args += [
            # Encodes with highest-speed presets for real-time live streaming.
            '-preset', 'ultrafast',
        ]
      else:
        args += [
            # Take your time for VOD streams.
            '-preset', 'slow',
            # Apply the loop filter for higher quality output.
            '-flags', '+loop',
        ]

      if video.hardware:
        args += [
            # H264 VAAPI video codec.
            '-c:v', 'h264_vaapi',
        ]
      else:
        args += [
            # H264 video codec.
            '-c:v', 'h264',
        ]

      args += [
          # Set bitrate to the one specified in the VOD config file.
          '-b:v', '{0}'.format(res_map.h264_bitrate),
          # Set maximum number of B frames between non-B frames.
          '-bf', '0',
          # Reorder mp4 segments so that the moov segment is at the front.
          # Needed for output to a pipe.
          '-movflags', '+faststart',
          # The only format supported by QT/Apple.
          '-pix_fmt', 'yuv420p',
          # Require a closed GOP.  Some decoders don't support open GOPs.
          '-flags', '+cgop',
      ]
      # Use different ffmpeg options depending on the H264 profile.
      args += profile_args[res_map.h264_profile]

    elif codec == 'vp9':
      args += [
          # Format using webm.
          '-f', 'webm',
      ]

      if video.hardware:
        args += [
            # VP9 VAAPI video codec.
            '-c:v', 'vp9_vaapi',
        ]
      else:
        args += [
          # VP9 video codec.
          '-c:v', 'vp9',
        ]

      args += [
          # Set bitrate to the one specified in the VOD config file.
          '-b:v', '{0}'.format(res_map.vp9_bitrate),
          # DASH-compatible output format.
          '-dash', '1',
      ]

    args += [
        # Set minimum and maximum GOP length.
        '-keyint_min', str(gop_size), '-g', str(gop_size),
        # Set video filters.
        '-vf', ','.join(filters),
        # The output.
        video.pipe,
    ]
    return args
