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

"""A module that runs an external command to generate media."""

from . import node_base

class ExternalCommandNode(node_base.NodeBase):

  def __init__(self, command: str, output_path: str):
    super().__init__()
    self._command = command
    self._output_path = output_path

  def start(self):
    # This environment/shell variable must be used by the external command as
    # the place it sends its generated output.  Since the command is executed
    # with shell=True, the command can include
    # $SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT at any point.
    env = {
      'SHAKA_STREAMER_EXTERNAL_COMMAND_OUTPUT': self._output_path,
    }
    # The yaml file may contain a multi-line string, which seems to cause
    # subprocess to execute each line as a command when shell=True.  So convert
    # newlines into spaces.
    command = self._command.replace('\n', ' ')
    self._process = self._create_process(command, shell=True, env=env)
