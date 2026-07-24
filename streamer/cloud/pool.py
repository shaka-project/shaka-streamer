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
import threading
import traceback
from setproctitle import setproctitle  # type: ignore
from queue import Queue

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
  def __init__(self, worker_type: MessageType, path: str = '',
               data: bytes = b'') -> None:
    self.type: MessageType = worker_type
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
    except Exception:  # pylint: disable=broad-exception-caught
      # Anything else is almost always a transient failure from the cloud
      # storage provider: a timeout, a dropped connection, a DNS failure, or a
      # 5xx response.  These must not kill the worker.  A live stream runs for
      # weeks or months, so a worker that dies on the first network hiccup
      # takes capacity out of the pool for the entire life of the stream.
      #
      # Log it and carry on.  The main process sees the failed upload as an
      # HTTP 500 from the proxy, which Packager can be told to tolerate with
      # --ignore_http_output_failures.
      traceback.print_exc()

      # Whatever we were in the middle of is no longer valid, so drop any
      # partial chunked-transfer state before handling the next message.
      try:
        uploader.reset()
      except Exception:  # pylint: disable=broad-exception-caught
        traceback.print_exc()


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

    try:
      self._process.writer.send(Message.reset())
    except OSError:
      # The worker process has died, so the pipe to it is broken.  The pool
      # will replace it when this worker is next taken from the queue.  Don't
      # let this mask an exception from the body of the "with" statement, which
      # is what actually explains the failure.
      pass
    finally:
      # This must happen no matter what.  If we fail to release the worker, it
      # is gone from the pool forever, and the pool will eventually be empty
      # and deadlock in get_worker().
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
    self._upload_location: str = upload_location
    self._all_processes: list[WorkerProcess] = []
    self._available_processes: Queue[WorkerProcess] = Queue()
    # Guards _all_processes, which is touched by every thread of the proxy's
    # ThreadingHTTPServer.  The Queue has its own locking and needs none.
    self._lock = threading.Lock()

    for _ in range(size):
      worker_process = self._spawn()
      self._all_processes.append(worker_process)
      self._available_processes.put(worker_process)

  def _spawn(self) -> WorkerProcess:
    """Start a new worker subprocess and return a handle to it."""

    reader, writer = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.Process(target=worker_target,
                                      args=(self._upload_location, reader))
    process.start()
    return WorkerProcess(process, writer)

  def _replace(self, dead: WorkerProcess) -> WorkerProcess:
    """Replace a dead worker with a fresh one, keeping the pool size fixed."""

    # Reap the dead process, so that it doesn't linger as a zombie.
    dead.writer.close()
    dead.process.join()

    replacement = self._spawn()

    with self._lock:
      # Swap in place, so that close() still sees exactly one entry per slot.
      self._all_processes[self._all_processes.index(dead)] = replacement

    return replacement

  def _release(self, process: WorkerProcess) -> None:
    """Called by worker handles to release the worker back to the pool."""

    self._available_processes.put(process)

  def get_worker(self) -> WorkerHandle:
    """Get an available worker.  Blocks until one is available.

    Returns a WorkerHandle meant to be used as a context manager (with "with"
    statements) so that it will be automatically released."""

    worker_process = self._available_processes.get(block=True)

    # A worker can still die on us: killed by the OOM killer, or crashed in a
    # native extension of a cloud storage library.  Replace it here rather than
    # handing out a worker whose pipe is already broken.  Without this, the
    # pool would shrink over the life of a long-running live stream until it
    # was empty, at which point get_worker() would block forever and wedge the
    # whole pipeline.
    if not worker_process.process.is_alive():
      worker_process = self._replace(worker_process)

    return WorkerHandle(self, worker_process)

  def close(self) -> None:
    """Close all worker processes."""

    with self._lock:
      all_processes = list(self._all_processes)

    # Signal shutdown with an explicit SIGTERM rather than by closing the write
    # end of each pipe.  Because the workers are forked, every worker inherits a
    # copy of every other worker's pipe write fd, so closing our own copy does
    # not deliver EOF to the reader and the worker would block in recv()
    # forever.  A worker has no shutdown work that must complete, so SIGTERM is
    # safe.
    for process in all_processes:
      process.process.terminate()

    for process in all_processes:
      process.process.join()
      process.writer.close()
