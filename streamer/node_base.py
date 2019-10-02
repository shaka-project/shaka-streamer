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

"""A base class for nodes that run a single subprocess."""

import abc
import enum
import shlex
import subprocess
import time

class ProcessStatus(enum.Enum):
  # Use number values so we can sort based on value.
  Running = 0
  Finished = 1
  Errored = 2


class NodeBase(object):

  @abc.abstractmethod
  def __init__(self):
    self._process = None

  def __del__(self):
    # If the process isn't stopped by now, stop it here.  It is preferable to
    # explicitly call stop().
    self.stop()

  @abc.abstractmethod
  def start(self):
    """Start the subprocess.

    Should be overridden by the subclass to construct a command line, call
    self._create_process, and assign the result to self._process.
    """
    pass

  def _create_process(self, args):
    """A central point to create subprocesses, so that we can debug the
    command-line arguments.

    Args:
      args: An array of strings, the command line of the subprocess.
    Returns:
      The Popen object of the subprocess.
    """
    # Print arguments formatted as output from bash -x would be.
    # This makes it easy to see the arguments and easy to copy/paste them for
    # debugging in a shell.
    print('+ ' + ' '.join([shlex.quote(arg) for arg in args]))
    return subprocess.Popen(args, stdin = subprocess.DEVNULL)

  def check_status(self):
    """Returns the current ProcessStatus of the node."""
    if not self._process:
      raise ValueError('Must have a process to check')

    self._process.poll()
    if self._process.returncode is None:
      return ProcessStatus.Running

    if self._process.returncode == 0:
      return ProcessStatus.Finished
    else:
      return ProcessStatus.Errored

  def stop(self):
    """Stop the subprocess if it's still running."""
    if self._process:
      # Slightly more polite than kill.  Try this first.
      self._process.terminate()

      if self.check_status() == ProcessStatus.Running:
        # If it's not dead yet, wait 1 second.
        time.sleep(1)

      if self.check_status() == ProcessStatus.Running:
        # If it's still not dead, use kill.
        self._process.kill()
        # Wait for the process to die and read its exit code.  There is no way
        # to ignore a kill signal, so this will happen quickly.  If we don't do
        # this, it can create a zombie process.
        self._process.wait()
