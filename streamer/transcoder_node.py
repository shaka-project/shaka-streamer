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

from . import bitrate_configuration
from . import input_configuration
from . import node_base
from . import pipeline_configuration

# Alias a few classes to avoid repeating namespaces later.
AudioCodec = bitrate_configuration.AudioCodec
VideoCodec = bitrate_configuration.VideoCodec

InputType = input_configuration.InputType
MediaType = input_configuration.MediaType

StreamingMode = pipeline_configuration.StreamingMode


class TranscoderNode(node_base.PolitelyWaitOnFinishMixin, node_base.NodeBase):

  def __init__(self, input_config, pipeline_config, outputs):
    super().__init__()
    self._input_config = input_config
    self._pipeline_config = pipeline_config
    self._outputs = outputs

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

    if any([output.is_hardware_accelerated() for output in self._outputs]):
      if self._pipeline_config.hwaccel_api == 'vaapi':
        args += [
            # Hardware acceleration args.
            # TODO(#17): Support multiple VAAPI devices.
            '-vaapi_device', '/dev/dri/renderD128',
        ]

    for input in self._input_config.inputs:
      # Get any required input arguments for this input.
      # These are like hard-coded extra_input_args for certain input types.
      # This means users don't have to know much about FFmpeg options to handle
      # these common cases.
      args += input.get_input_args()

      # The config file may specify additional args needed for this input.
      # This allows, for example, an external-command-type input to generate
      # almost anything ffmpeg could ingest.
      args += input.extra_input_args

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
          '-i', input.get_path_for_transcode(),
      ]

    for i, input in enumerate(self._input_config.inputs):
      if input.media_type == MediaType.TEXT:
        # We don't yet have the ability to transcode or process text inputs.
        continue

      map_args = [
          # Map corresponding input stream to output file.
          # The format is "<INPUT FILE NUMBER>:<STREAM SPECIFIER>", so "i" here
          # is the input file number, and "input.get_stream_specifier()" builds
          # the stream specifier for this input.  The output stream for this
          # input is implied by where we are in the ffmpeg argument list.
          '-map', '{0}:{1}'.format(i, input.get_stream_specifier()),
      ]

      for output_stream in self._outputs:
        if output_stream.type != input.media_type:
          # Skip outputs that don't match this input.
          continue

        # Map arguments must be repeated for each output file.
        args += map_args

        if input.media_type == MediaType.AUDIO:
          args += self._encode_audio(output_stream, input)
        else:
          args += self._encode_video(output_stream, input)

        # The output pipe.
        args += [output_stream.pipe]

    env = {}
    if self._pipeline_config.debug_logs:
      # Use this environment variable to turn on ffmpeg's logging.  This is
      # independent of the -loglevel switch above.
      env['FFREPORT'] = 'file=TranscoderNode.log:level=32'

    self._process = self._create_process(args, env)

  def _encode_audio(self, stream, input):
    filters = []
    args = [
        # No video encoding for audio.
        '-vn',
        # TODO: This implied downmixing is not ideal.
        # Set the number of channels to the one specified in the config.
        '-ac', str(stream.channels),
    ]

    if stream.channels == 6:
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
    ]

    # TODO: Use the same intermediate format as output format?
    if stream.codec == AudioCodec.AAC:
      args += [
          # MPEG-TS format works well in a pipe.
          '-f', 'mpegts',
      ]
    elif stream.codec == AudioCodec.OPUS:
      args += [
          # Format using WebM.
          '-f', 'webm',
          # DASH-compatible output format.
          # TODO: Is this argument necessary?
          '-dash', '1',
      ]

    if len(filters):
      args += [
          # Set audio filters.
          '-af', ','.join(filters),
      ]

    return args

  def _encode_video(self, stream, input):
    filters = []
    args = []

    if input.is_interlaced:
      filters.append('pp=fd')
      args.extend(['-r', str(input.frame_rate)])

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

    # TODO: Use the same intermediate format as output format?

    if stream.codec == VideoCodec.H264:
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

    if stream.codec.get_base_codec() == VideoCodec.H264:  # Software or hardware
      # Use the "high" profile for HD and up, and "main" for everything else.
      # https://en.wikipedia.org/wiki/Advanced_Video_Coding#Profiles
      if stream.resolution.max_height >= 720:
        profile = 'high'
      else:
        profile = 'main'

      args += [
          # MPEG-TS format works well in a pipe.
          '-f', 'mpegts',
          # The only format supported by QT/Apple.
          '-pix_fmt', 'yuv420p',
          # Require a closed GOP.  Some decoders don't support open GOPs.
          '-flags', '+cgop',
          # Set the H264 profile.  Without this, the default would be "main".
          # Note that this gets overridden to "baseline" in live streams by the
          # "-preset ultrafast" option, presumably because the baseline encoder
          # is faster.
          '-profile:v', profile,
      ]

    elif stream.codec.get_base_codec() == VideoCodec.VP9:
      # TODO: Does -preset apply here?
      args += [
          # Format using WebM.
          '-f', 'webm',
          # DASH-compatible output format.
          # TODO: Is this argument necessary?
          '-dash', '1',
          # According to the wiki (https://trac.ffmpeg.org/wiki/Encode/VP9),
          # this allows threaded encoding in VP9, which makes better use of CPU
          # resources and speeds up encoding.  This is still not the default
          # setting as of libvpx v1.7.
          '-row-mt', '1',
      ]

    keyframe_interval = int(self._pipeline_config.segment_size *
                            input.frame_rate)

    args += [
        # No audio encoding for video.
        '-an',
        # Set codec and bitrate.
        '-c:v', stream.get_ffmpeg_codec_string(hwaccel_api),
        '-b:v', stream.get_bitrate(),
        # Set minimum and maximum GOP length.
        '-keyint_min', str(keyframe_interval), '-g', str(keyframe_interval),
        # Set video filters.
        '-vf', ','.join(filters),
    ]
    return args
