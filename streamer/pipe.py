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

"""A module that encapsulates all the platform-specific logic related to creating
named pipes."""

import os
import uuid
from threading import Thread
from typing import Any

class Pipe(Thread):
  """A class that represents a pipe."""

  def __init__(self):
    """Initializes a non-functioning pipe."""
    
    self._read_pipe_name = ''
    self._write_pipe_name = ''

    # Windows specific declarations.
    self.buf_size = 0
    self._read_side: Any = None
    self._write_side: Any = None

  @staticmethod
  def create_ipc_pipe(temp_dir: str, suffix: str = '') -> 'Pipe':
    """A static method used to create a pipe between two processes. 
    
    On POXIS systems, it creates a named pipe using `os.mkfifo`.
    
    On Windows platforms, it starts a backgroud thread that transfars data from the
    writer to the reader process it is connected to.
    """

    unique_name = str(uuid.uuid4()) + suffix
    pipe = Pipe()

    # New Technology, aka WindowsNT.
    if os.name == 'nt':
      import win32pipe # type: ignore
      # Initialize the pipe object as a thread with `daemon` attribute set
      # to True so that the thread shuts down when the caller thread exits.
      Thread.__init__(pipe, daemon=True)
      pipe_name = '-nt-shaka-' + unique_name
      # The read pipe is connected to a writer process.
      pipe._read_pipe_name = r'\\.\pipe\W' + pipe_name
      # The write pipe is connected to a reader process.
      pipe._write_pipe_name = r'\\.\pipe\R' + pipe_name
      pipe.buf_size = 64 * 1024

      pipe._read_side = win32pipe.CreateNamedPipe(
          pipe._read_pipe_name,
          win32pipe.PIPE_ACCESS_INBOUND,
          win32pipe.PIPE_WAIT | win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
          1,
          pipe.buf_size,
          pipe.buf_size,
          0,
          None)

      pipe._write_side = win32pipe.CreateNamedPipe(
          pipe._write_pipe_name,
          win32pipe.PIPE_ACCESS_OUTBOUND,
          win32pipe.PIPE_WAIT | win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
          1,
          pipe.buf_size,
          pipe.buf_size,
          0,
          None)

      # Start the thread.
      pipe.start()
    elif hasattr(os, 'mkfifo'):
      pipe_name = os.path.join(temp_dir, unique_name)
      pipe._read_pipe_name = pipe_name
      pipe._write_pipe_name = pipe_name
      readable_by_owner_only = 0o600  # Unix permission bits
      os.mkfifo(pipe_name, mode=readable_by_owner_only) # type: ignore
    else:
      raise RuntimeError('Platform not supported.')
    return pipe

  @staticmethod
  def create_file_pipe(path: str, mode: str) -> 'Pipe':
    """Returns a Pipe object whose read or write end is a path to a file."""

    pipe = Pipe()
    # A process will write on the read pipe(file).
    if mode == 'w':
      pipe._read_pipe_name = path
    # A process will read from the write pipe(file).
    elif mode == 'r':
      pipe._write_pipe_name = path
    else:
      raise RuntimeError('{} is not a valid file mode'.format(mode))
    return pipe

  def run(self):
    """This method serves as a server that connects a writer client
    to a reader client.
    
    This methods will run as a thread, and will only be called on Windows platforms.
    """

    import win32pipe, win32file, pywintypes # type: ignore
    try:
      # Connect to both ends of the pipe before starting the transfer.
      # This funciton is blocking. If no process is connected yet, it will wait
      # indefinitely.
      win32pipe.ConnectNamedPipe(self._read_side)
      win32pipe.ConnectNamedPipe(self._write_side)
      while True:
        # Writer -> _read_side -> _write_side -> Reader
        _, data = win32file.ReadFile(self._read_side, self.buf_size)
        win32file.WriteFile(self._write_side, data)
    except Exception as ex:
      # Remove the pipes from the system.
      win32file.CloseHandle(self._read_side)
      win32file.CloseHandle(self._write_side)
      # If the error was due to one of the processes shutting down, just exit normally.
      if isinstance(ex, pywintypes.error) and ex.args[0] in [109, 232]:
        return 0
      # Otherwise, raise that error.
      raise ex

  def read_end(self) -> str:
    """Returns a pipe/file path that a reader process can read from."""
    assert self._write_pipe_name
    return self._write_pipe_name

  def write_end(self) -> str:
    """Returns a pipe/file path that a writer process can write to."""
    assert self._read_pipe_name
    return self._read_pipe_name
