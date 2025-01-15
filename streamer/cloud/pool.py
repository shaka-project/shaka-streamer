# Copyright 2025 Google LLC
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

"""A pool of worker processes to upload to cloud storage."""

import abc
import enum
from setproctitle import setproctitle  # type: ignore
from queue import Queue

from typing import Optional
from typing_extensions import Self

import multiprocessing
# On Windows, we get multiprocessing.connection.PipeConnection.
# On Linux/macOS, we get multiprocessing.connection.Connection.
# Both inherit from multiprocessing.connection._ConnectionBase.
from multiprocessing.connection import _ConnectionBase

from streamer.cloud.base import CloudUploaderBase
import streamer.cloud.uploader as Uploader


class MessageType(enum.Enum):
  """Message type constants used for IPC from the main process to the pool."""

  WRITE_NON_CHUNKED = 'write_non_chunked'
  START_CHUNKED = 'start_chunked'
  WRITE_CHUNK = 'write_chunk'
  END_CHUNKED = 'end_chunked'
  DELETE = 'delete'
  RESET = 'reset'


class Message(object):
  """Message objects used for IPC from the main process to the pool."""
  def __init__(self, type: MessageType, path: str = "",
               data: bytes = b'') -> None:
    self.type: MessageType = type
    self.path: str = path
    self.data: bytes = data

  @staticmethod
  def write_non_chunked(path: str, data: bytes) -> 'Message':
    """A request to write non-chunked data (all at once)."""
    return Message(MessageType.WRITE_NON_CHUNKED, path, data)

  @staticmethod
  def start_chunked(path: str) -> 'Message':
    """A request to start a chunked data transfer."""
    return Message(MessageType.START_CHUNKED, path)

  @staticmethod
  def write_chunk(data: bytes) -> 'Message':
    """A request to write a single chunk of data."""
    return Message(MessageType.WRITE_CHUNK, data = data)

  @staticmethod
  def end_chunked() -> 'Message':
    """A request to end a chunked data transfer."""
    return Message(MessageType.END_CHUNKED)

  @staticmethod
  def delete(path: str) -> 'Message':
    """A request to delete a file."""
    return Message(MessageType.DELETE, path)

  @staticmethod
  def reset() -> 'Message':
    """A request to reset state when releasing a worker."""
    return Message(MessageType.RESET)


def worker_target(upload_location: str, reader: _ConnectionBase):
  """Target for multiprocessing.Process.

  This is the entry point for every worker subprocess.

  Reads messages from IPC and talks to cloud storage."""

  # Set the title of the process as it appears in "ps" under Linux.
  setproctitle('shaka-streamer cloud upload worker')

  # Create an uploader using whatever vendor-specific module is necessary for
  # this upload location URL.  (Google Cloud Storage, Amazon S3, etc.)
  uploader = Uploader.create(upload_location)

  # Wait for command messages from the main process, proxying each command to
  # the uploader.
  while True:
    try:
      message: Message = reader.recv()

      if message.type == MessageType.WRITE_NON_CHUNKED:
        uploader.write_non_chunked(message.path, message.data)
      elif message.type == MessageType.START_CHUNKED:
        uploader.start_chunked(message.path)
      elif message.type == MessageType.WRITE_CHUNK:
        uploader.write_chunk(message.data)
      elif message.type == MessageType.END_CHUNKED:
        uploader.end_chunked()
      elif message.type == MessageType.DELETE:
        uploader.delete(message.path)
      elif message.type == MessageType.RESET:
        uploader.reset()
    except EOFError:
      # Quit the process when the other end of the pipe is closed.
      return


class WorkerProcess(object):
  """A worker process and the write end of its pipe."""

  def __init__(self, process: multiprocessing.Process,
               writer: _ConnectionBase) -> None:
    self.process = process
    self.writer = writer


class AbstractPool(object):
  """An interface for a WorkerHandle (below) to talk to Pool (which references
  WorkerHandle).  Created to break a circular dependency for static typing."""

  @abc.abstractmethod
  def _release(self, process: WorkerProcess) -> None:
    """Add a process back into the pool."""
    pass


class WorkerHandle(CloudUploaderBase):
  """A proxy for a cloud uploader interface that sends commands to a worker
  process.  It is also a context manager for use with "with" statements."""

  def __init__(self, pool: AbstractPool, process: WorkerProcess) -> None:
    self._pool = pool
    self._process = process

  def __enter__(self) -> Self:
    # Part of the interface for context managers, but there's nothing to do
    # here.
    return self

  def __exit__(self, *args, **kwargs) -> None:
    """Reset the subprocess's uploader and release the subprocess back to the
    pool."""

    self._process.writer.send(Message.reset())
    self._pool._release(self._process)

  def write_non_chunked(self, path: str, data: bytes) -> None:
    self._process.writer.send(Message.write_non_chunked(path, data))

  def start_chunked(self, path: str) -> None:
    self._process.writer.send(Message.start_chunked(path))

  def write_chunk(self, data: bytes) -> None:
    self._process.writer.send(Message.write_chunk(data))

  def end_chunked(self) -> None:
    self._process.writer.send(Message.end_chunked())

  def delete(self, path: str) -> None:
    self._process.writer.send(Message.delete(path))

  def reset(self) -> None:
    # Part of the interface for uploaders, but this should not be called
    # explicitly.
    pass


class Pool(AbstractPool):
  """A pool of worker subprocesses that handle cloud upload actions."""

  def __init__(self, upload_location: str, size: int) -> None:
    self._all_processes: list[WorkerProcess] = []
    self._available_processes: Queue[WorkerProcess] = Queue()

    for i in range(size):
      reader, writer = multiprocessing.Pipe(duplex=False)
      process = multiprocessing.Process(target=worker_target,
                                        args=(upload_location, reader))
      process.start()
      worker_process = WorkerProcess(process, writer)
      self._available_processes.put(worker_process)
      self._all_processes.append(worker_process)

  def _release(self, worker_process: WorkerProcess) -> None:
    """Called by worker handles to release the worker back to the pool."""

    self._available_processes.put(worker_process)

  def get_worker(self) -> WorkerHandle:
    """Get an available worker.  Blocks until one is available.

    Returns a WorkerHandle meant to be used as a context manager (with "with"
    statements) so that it will be automatically released."""

    worker_process = self._available_processes.get(block=True)
    return WorkerHandle(self, worker_process)

  def close(self) -> None:
    """Close all worker processes."""

    for process in self._all_processes:
      process.writer.close()
      process.process.join()
