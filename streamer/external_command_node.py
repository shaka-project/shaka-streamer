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

import os
import signal
import subprocess
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
    # Create a new group for the spawned shell to easily shut it down.
    if os.name == 'posix':
      # A POSIX only argument.
      new_group_flag = {'start_new_session': True}
    elif os.name == 'nt':
      # A Windows only argument.
      new_group_flag = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    self._process = self._create_process(command, shell=True,
                                         env=env, **new_group_flag)

  def stop(self, status):
    # Since we created the external shell process in a new group, sending
    # a SIGTERM to the group will terminate the shell and its children.
    if self.check_status() == node_base.ProcessStatus.Running:
      if os.name == 'posix':
        os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
      elif os.name == 'nt':
        os.kill(self._process.pid, signal.CTRL_BREAK_EVENT)
