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

"""A module that uses ffmpeg to loop a local file into a named pipe."""

from . import node_base

class LoopInputNode(node_base.NodeBase):
  def __init__(self, config, input_path, output_path):
    node_base.NodeBase.__init__(self)
    self._config = config
    self._input_path = input_path
    self._output_path = output_path

  def start(self):
    args = [
        'ffmpeg',
        # Loop the input forever.
        '-stream_loop', '-1',
        # Read input in real time.
        '-re',
    ]

    if self._config.quiet:
      args += [
          # Suppresses all messages except errors.
          '-loglevel', 'error',
      ]
    else:
      args += [
          # Suppresses all messages except warnings and errors.
          # By using this instead of the default, we suppress the status line
          # showing progress and transcoding speed.  The transcoder node will
          # show this instead, which will indicate overall pipeline speed.
          # If we show both at once, it will be unreadable.
          '-loglevel', 'warning',
      ]

    args += [
        # The input itself.
        '-i', self._input_path,
        # Format the output as MPEG2-TS, which works well in a pipe.
        '-f', 'mpegts',
        # Copy the video stream directly.
        '-c:v', 'copy',
        # Copy the audio stream directly.
        '-c:a', 'copy',
        # Do not prompt for output files that already exist.  Since we created
        # the named pipe in advance, it definitely already exists.  A prompt
        # would block ffmpeg to wait for user input.
        '-y',
        # The output itself.
        self._output_path,
    ]

    self._process = self._create_process(args)

