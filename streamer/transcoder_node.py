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
from . import node_base
from . import pipeline_configuration

# Alias a few classes to avoid repeating namespaces later.
InputType = input_configuration.InputType
MediaType = input_configuration.MediaType
StreamingMode = pipeline_configuration.StreamingMode


# For H264, there are different profiles with different required command line
# arguments.
PROFILE_ARGS = {
  'baseline': ['-profile:v', 'baseline', '-level:v', '3.0'],
  'main': ['-profile:v', 'main', '-level:v', '3.1'],
  'high': ['-profile:v', 'high', '-level:v', '4.0'],
  'uhd': ['-profile:v', 'high', '-level:v', '5.1'],
}

class TranscoderNode(node_base.NodeBase):

  def __init__(self, output_audios, output_videos, input_config,
               pipeline_config):
    super().__init__()
    self._output_audios = output_audios
    self._output_videos = output_videos
    self._input_config = input_config
    self._pipeline_config = pipeline_config

  def start(self):
    args = [
        'ffmpeg',
        # Do not prompt for output files that already exist. Since we created
        # the named pipe in advance, it definitely already exists. A prompt
        # would block ffmpeg to wait for user input.
        '-y',
    ]

    if self._pipeline_config.quiet:
      args += [
          # Suppresses all messages except errors.
          # Without this, a status line will be printed by default showing
          # progress and transcoding speed.
          '-loglevel', 'error',
      ]

    if any([output.hardware for output in self._output_videos]):
      args += [
          # Hardware acceleration args.
          '-hwaccel', 'vaapi',
          '-vaapi_device', '/dev/dri/renderD128',
      ]

    for input in self._input_config.inputs:
      # The config file may specify additional args needed for this input.
      # This allows, for example, an external-command-type input to generate
      # almost anything ffmpeg could ingest.
      args += input.extra_input_args

      # These are like hard-coded extra_input_args for certain input types.
      # This means users don't have to know much about FFmpeg options to handle
      # these common cases.
      if input.input_type == InputType.LOOPED_FILE:
        args += [
          # Loop the input forever.
          '-stream_loop', '-1',
          # Read input in real time; don't go above 1x processing speed.
          '-re',
        ]
      elif input.input_type == InputType.RAW_IMAGES:
        args += [
            # Parse the input as a stream of images fed into a pipe.
            '-f', 'image2pipe',
            # Set the frame rate to the one specified in the input config.
            # Note that this is the input framerate for the image2 dexuxer, which
            # is not what the similar '-r' option is meant for.
            '-framerate', str(input.frame_rate),
        ]
      elif input.input_type == InputType.WEBCAM:
        args += [
            # Format the input using the webcam format.
            '-f', 'video4linux2',
        ]

      if self._pipeline_config.streaming_mode == StreamingMode.LIVE:
        args += [
            # A larger queue to buffer input from the pipeline (default is 8).
            # This is in packets, but for raw images, that means frames.  A
            # 720p PPM frame is 2.7MB, and a 1080p PPM is 6.2MB.  The entire
            # queue, when full, must fit into memory.
            '-thread_queue_size', '200',
        ]

      if input.start_time:
        args += [
            # Encode from intended starting time of the VOD input.
            '-ss', input.start_time,
        ]
      if input.end_time:
        args += [
            # Encode until intended ending time of the VOD input.
            '-to', input.end_time,
        ]

      # The input name always comes after the applicable input arguments.
      args += [
          # The input itself.
          '-i', input.get_path_for_transcode(),
      ]

    for i, input in enumerate(self._input_config.inputs):
      map_args = [
          # Map corresponding input stream to output file.
          # The format is "<INPUT FILE NUMBER>:<TRACK NUMBER>", so "i" here is
          # the input file number, and "input.get_track()" is the track number
          # from that input file.  The output stream for this input is implied
          # by where we are in the ffmpeg argument list.
          '-map', '{0}:{1}'.format(i, input.track_num),
      ]

      if input.media_type == MediaType.AUDIO:
        for audio in self._output_audios:
          # Map arguments must be repeated for each output file.
          args += map_args
          args += self._encode_audio(audio, input)

      if input.media_type == MediaType.VIDEO:
        for video in self._output_videos:
          # Map arguments must be repeated for each output file.
          args += map_args
          args += self._encode_video(video, input)

    env = {}
    if self._pipeline_config.debug_logs:
      # Use this environment variable to turn on ffmpeg's logging.  This is
      # independent of the -loglevel switch above.
      env['FFREPORT'] = 'file=TranscoderNode.log:level=32'

    self._process = self._create_process(args, env)

  def _encode_audio(self, audio, input):
    filters = []
    args = [
        # No video encoding for audio.
        '-vn',
        # Set the number of channels to the one specified in the VOD config
        # file.
        '-ac', str(audio.channels),
    ]

    if audio.channels == 6:
      filters += [
        # Work around for https://github.com/google/shaka-packager/issues/598,
        # as seen on https://trac.ffmpeg.org/ticket/6974
        'channelmap=channel_layout=5.1',
      ]

    filters.extend(input.filters)

    if audio.codec == 'aac':
      args += [
          # Format with MPEG-TS for a pipe.
          '-f', 'mpegts',
          # AAC audio codec.
          '-c:a', 'aac',
          # Set bitrate to the one specified in the VOD config file.
          '-b:a', '{0}'.format(audio.channel_data.aac_bitrate),
      ]
    elif audio.codec == 'opus':
      args += [
          # Opus encoding has output format webm.
          '-f', 'webm',
          # Opus audio codec.
          '-c:a', 'libopus',
          # Set bitrate to the one specified in the VOD config file.
          '-b:a', '{0}'.format(audio.channel_data.opus_bitrate),
          # DASH-compatible output format.
          '-dash', '1',
      ]

    if len(filters):
      args += [
          # Set audio filters.
          '-af', ','.join(filters),
      ]

    args += [
        # The output.
        audio.pipe,
    ]
    return args

  # TODO(joeyparrish): "video" is a weak variable name
  def _encode_video(self, video, input):
    filters = []
    args = [
        # No audio encoding for video.
        '-an',
        # Full pelME compare function.
        '-cmp', 'chroma',
    ]

    # TODO: auto detection of interlacing
    if input.is_interlaced:
      frame_rate = input.frame_rate
      # Sanity check: since interlaced files are made up of two interlaced
      # frames, the frame rate must be even and not too small.
      assert frame_rate % 2 == 0 and frame_rate >= 48
      filters.append('pp=fd')
      args.extend(['-r', str(frame_rate / 2)])

    filters.extend(input.filters)

    if video.hardware:
      filters.append('format=nv12')
      filters.append('hwupload')
      # -2 here means to choose a width to keep the original aspect ratio.
      filters.append('scale_vaapi=-2:{0}'.format(video.resolution_data.height))
    else:
      # -2 here means to choose a width to keep the original aspect ratio.
      filters.append('scale=-2:{0}'.format(video.resolution_data.height))

    if video.codec == 'h264':
      args += [
          # MPEG-TS format works well in a pipe.
          '-f', 'mpegts',
      ]

      if self._pipeline_config.streaming_mode == StreamingMode.LIVE:
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
          '-b:v', '{0}'.format(video.resolution_data.h264_bitrate),
          # Set maximum number of B frames between non-B frames.
          '-bf', '0',
          # The only format supported by QT/Apple.
          '-pix_fmt', 'yuv420p',
          # Require a closed GOP.  Some decoders don't support open GOPs.
          '-flags', '+cgop',
      ]
      # Use different ffmpeg options depending on the H264 profile.
      args += PROFILE_ARGS[video.resolution_data.h264_profile]

    elif video.codec == 'vp9':
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
          '-b:v', '{0}'.format(video.resolution_data.vp9_bitrate),
          # DASH-compatible output format.
          '-dash', '1',
      ]

    # TODO: auto-detection of framerate?
    keyframe_interval = int(self._pipeline_config.segment_size *
                            input.frame_rate)
    args += [
        # Set minimum and maximum GOP length.
        '-keyint_min', str(keyframe_interval), '-g', str(keyframe_interval),
        # Set video filters.
        '-vf', ','.join(filters),
        # The output.
        video.pipe,
    ]
    return args
