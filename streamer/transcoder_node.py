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

import shlex

from streamer.bitrate_configuration import AudioCodec, VideoCodec
from streamer.input_configuration import Input, InputType, MediaType
from streamer.node_base import PolitelyWaitOnFinish
from streamer.output_stream import AudioOutputStream, OutputStream, TextOutputStream, VideoOutputStream
from streamer.pipeline_configuration import PipelineConfig, StreamingMode
from typing import List, Union, Optional

class TranscoderNode(PolitelyWaitOnFinish):

  def __init__(self,
               inputs: List[Input],
               pipeline_config: PipelineConfig,
               outputs: List[OutputStream],
               index: int,
               hermetic_ffmpeg: Optional[str]) -> None:
    super().__init__()
    self._inputs = inputs
    self._pipeline_config = pipeline_config
    self._outputs = outputs
    self._index = index
    # If a hermetic ffmpeg is passed, use it.
    self._ffmpeg = hermetic_ffmpeg or 'ffmpeg'

  def start(self) -> None:
    args = [
        self._ffmpeg,
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

    if any([output.is_hardware_accelerated() for output in self._outputs]):
      if self._pipeline_config.hwaccel_api == 'vaapi':
        args += [
            # Hardware acceleration args.
            # TODO(#17): Support multiple VAAPI devices.
            '-vaapi_device', '/dev/dri/renderD128',
        ]

    for input in self._inputs:
      # Get any required input arguments for this input.
      # These are like hard-coded extra_input_args for certain input types.
      # This means users don't have to know much about FFmpeg options to handle
      # these common cases.
      args += input.get_input_args()

      # The config file may specify additional args needed for this input.
      # This allows, for example, an external-command-type input to generate
      # almost anything ffmpeg could ingest.  The extra args need to be parsed
      # from a string into an argument array.  Note that shlex.split on an empty
      # string will produce an empty array.
      args += shlex.split(input.extra_input_args)

      if input.input_type == InputType.LOOPED_FILE:
        # These are handled here instead of in get_input_args() because these
        # arguments are specific to ffmpeg and are not understood by ffprobe.
        args += [
            # Loop the input forever.
            '-stream_loop', '-1',
            # Read input in real time; don't go above 1x processing speed.
            '-re',
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
            # Encode from intended starting time of the input.
            '-ss', input.start_time,
        ]
      if input.end_time:
        args += [
            # Encode until intended ending time of the input.
            '-to', input.end_time,
        ]

      # The input name always comes after the applicable input arguments.
      args += [
          # The input itself.
          '-i', input.name,
      ]

    for i, input in enumerate(self._inputs):
      map_args = [
          # Map corresponding input stream to output file.
          # The format is "<INPUT FILE NUMBER>:<STREAM SPECIFIER>", so "i" here
          # is the input file number, and "input.get_stream_specifier()" builds
          # the stream specifier for this input.  The output stream for this
          # input is implied by where we are in the ffmpeg argument list.
          '-map', '{0}:{1}'.format(i, input.get_stream_specifier()),
      ]

      for output_stream in self._outputs:
        if output_stream.input != input:
          # Skip outputs that don't match this exact input object.
          continue
        if output_stream.skip_transcoding:
          # This input won't be transcoded.  This is common for VTT text input.
          continue

        # Map arguments must be repeated for each output file.
        args += map_args

        if input.media_type == MediaType.AUDIO:
          assert(isinstance(output_stream, AudioOutputStream))
          args += self._encode_audio(output_stream, input)
        elif input.media_type == MediaType.VIDEO:
          assert(isinstance(output_stream, VideoOutputStream))
          args += self._encode_video(output_stream, input)
        else:
          assert(isinstance(output_stream, TextOutputStream))
          args += self._encode_text(output_stream, input)

        args += [output_stream.ipc_pipe.write_end()]

    env = {}
    if self._pipeline_config.debug_logs:
      # Use this environment variable to turn on ffmpeg's logging.  This is
      # independent of the -loglevel switch above.
      ffmpeg_log_file = 'TranscoderNode-' + str(self._index) + '.log'
      env['FFREPORT'] = 'file={}:level=32'.format(ffmpeg_log_file)

    self._process = self._create_process(args, env)

  def _encode_audio(self, stream: AudioOutputStream, input: Input) -> List[str]:
    filters: List[str] = []
    args: List[str] = [
        # No video encoding for audio.
        '-vn',
        # TODO: This implied downmixing is not ideal.
        # Set the number of channels to the one specified in the config.
        '-ac', str(stream.layout.max_channels),
    ]

    if stream.layout.max_channels == 6:
      filters += [
        # Work around for https://github.com/google/shaka-packager/issues/598,
        # as seen on https://trac.ffmpeg.org/ticket/6974
        'channelmap=channel_layout=5.1',
      ]

    filters.extend(input.filters)

    hwaccel_api = self._pipeline_config.hwaccel_api
    args += [
        # Set codec and bitrate.
        '-c:a', stream.get_ffmpeg_codec_string(hwaccel_api),
        '-b:a', stream.get_bitrate(),
        # Output MP4 in the pipe, for all codecs.
        '-f', 'mp4',
        # This explicit fragment duration affects both audio and video, and
        # ensures that there are no single large MP4 boxes that Shaka Packager
        # can't consume from a pipe.
        # FFmpeg fragment duration is in microseconds.
        '-frag_duration', str(self._pipeline_config.segment_size * 1e6),
        # Opus in MP4 is considered "experimental".
        '-strict', 'experimental',
      ]

    if len(filters):
      args += [
          # Set audio filters.
          '-af', ','.join(filters),
      ]

    return args

  def _encode_video(self, stream: VideoOutputStream, input: Input) -> List[str]:
    filters: List[str] = []
    args: List[str] = []

    if input.is_interlaced:
      filters.append('pp=fd')
      args.extend(['-r', str(input.frame_rate)])
    
    if stream.resolution.max_frame_rate < input.frame_rate:
       args.extend(['-r', str(stream.resolution.max_frame_rate)])

    filters.extend(input.filters)

    hwaccel_api = self._pipeline_config.hwaccel_api

    # -2 in the scale filters means to choose a value to keep the original
    # aspect ratio.
    if stream.is_hardware_accelerated() and hwaccel_api == 'vaapi':
      # These filters are specific to Linux's vaapi.
      filters.append('format=nv12')
      filters.append('hwupload')
      filters.append('scale_vaapi=-2:{0}'.format(stream.resolution.max_height))
    else:
      filters.append('scale=-2:{0}'.format(stream.resolution.max_height))

    # To avoid weird rounding errors in Sample Aspect Ratio, set it explicitly
    # to 1:1.  Without this, you wind up with SAR set to weird values in DASH
    # that are very close to 1, such as 5120:5123.  In HLS, the behavior is
    # worse.  Some of the width values in the playlist wind up off by one,
    # which causes playback failures in ExoPlayer.
    # https://github.com/google/shaka-streamer/issues/36
    filters.append('setsar=1:1')

    if (stream.codec in {VideoCodec.H264, VideoCodec.HEVC} 
        and not stream.is_hardware_accelerated()):
      # These presets are specifically recognized by the software encoder.
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

    if stream.codec == VideoCodec.H264:  # Software or hardware
      # Use the "high" profile for HD and up, and "main" for everything else.
      # https://en.wikipedia.org/wiki/Advanced_Video_Coding#Profiles
      if stream.resolution.max_height >= 720:
        profile = 'high'
      else:
        profile = 'main'

      args += [
          # Set the H264 profile.  Without this, the default would be "main".
          # Note that this gets overridden to "baseline" in live streams by the
          # "-preset ultrafast" option, presumably because the baseline encoder
          # is faster.
          '-profile:v', profile,
      ]
      
    if stream.codec in {VideoCodec.H264, VideoCodec.HEVC}:
      args += [
          # The only format supported by QT/Apple.
          '-pix_fmt', 'yuv420p',
          # Require a closed GOP.  Some decoders don't support open GOPs.
          '-flags', '+cgop',
         
      ]

    elif stream.codec == VideoCodec.VP9:
      # TODO: Does -preset apply here?
      args += [
          # According to the wiki (https://trac.ffmpeg.org/wiki/Encode/VP9),
          # this allows threaded encoding in VP9, which makes better use of CPU
          # resources and speeds up encoding.  This is still not the default
          # setting as of libvpx v1.7.
          '-row-mt', '1',
          # speeds up encoding, balancing against quality
          '-speed', '2',
      ]
    elif stream.codec == VideoCodec.AV1:
      args += [
          # According to graphs at https://bit.ly/2BmIVt6, this AV1 setting
          # results in almost no reduction in quality (0.8%), but a significant
          # boost in speed (20x).
          '-cpu-used', '8',
          # According to the wiki (https://trac.ffmpeg.org/wiki/Encode/AV1),
          # this allows threaded encoding in AV1, which makes better use of CPU
          # resources and speeds up encoding.  This will be ignored by libaom
          # before version 1.0.0-759-g90a15f4f2, and so there may be no benefit
          # unless libaom and ffmpeg are built from source (as of Oct 2019).
          '-row-mt', '1',
          # According to the wiki (https://trac.ffmpeg.org/wiki/Encode/AV1),
          # this allows for threaded _decoding_ in AV1, which will provide a
          # smoother playback experience for the end user.
          '-tiles', '2x2',
          # AV1 is considered "experimental".
          '-strict', 'experimental',
      ]

    keyframe_interval = int(self._pipeline_config.segment_size *
                            input.frame_rate)

    args += [
        # No audio encoding for video.
        '-an',
        # Set codec and bitrate.
        '-c:v', stream.get_ffmpeg_codec_string(hwaccel_api),
        '-b:v', stream.get_bitrate(),
        # Output MP4 in the pipe, for all codecs.
        '-f', 'mp4',
        # This flag forces a video fragment at each keyframe.
        '-movflags', '+frag_keyframe',
        # This explicit fragment duration affects both audio and video, and
        # ensures that there are no single large MP4 boxes that Shaka Packager
        # can't consume from a pipe.
        # FFmpeg fragment duration is in microseconds.
        '-frag_duration', str(self._pipeline_config.segment_size * 1e6),
        # Set minimum and maximum GOP length.
        '-keyint_min', str(keyframe_interval), '-g', str(keyframe_interval),
        # Set video filters.
        '-vf', ','.join(filters),
    ]
    return args

  def _encode_text(self, stream: TextOutputStream, input: Input) -> List[str]:
    return [
        # Output WebVTT.
        '-f', 'webvtt',
    ]
