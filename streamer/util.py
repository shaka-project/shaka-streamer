# Copyright 2021 Google LLC
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

"""Utility functions used by multiple modules."""

import io
from typing import Optional


def is_url(output_location: str) -> bool:
  """Returns True if the output location is a URL."""
  return output_location.startswith(('http://',
                                     'https://'))


class RequestBodyAsFileIO(io.BufferedIOBase):
  """A class that provides a layer of access to an HTTP request body.  It provides
  an interface to treat a request body (of type `io.BufferedIOBase`) as a file.
  Since a request body does not have an `EOF`, this class will encapsulate the
  logic of using Content-Length or chunk size to provide an emulated `EOF`.

  This implementation is much faster than storing the request body
  in the filesystem then reading it with an `EOF` included.
  """

  def __init__(self, rfile: io.BufferedIOBase, content_length: Optional[int]):
    super().__init__()
    self._body = rfile
    # Decide whether this is a chunked request or not based on content length.
    if content_length is not None:
      self._is_chunked = False
      self._left_to_read = content_length
    else:
      self._is_chunked = True
      self._last_chunk_read = False
      self._buffer = b''

  def read(self, blocksize: Optional[int] = None) -> bytes:
    """This method reads `self.body` incrementally with each call.
    This is done because if we try to use `read()` on `self._body` it will wait
    forever for an `EOF` which is not present and will never be.

    This method -like the original `read()`- will read up to (but not more than)
    `blocksize` if it is a non-negative integer, and will read till `EOF` if
    blocksize is None, a negative integer, or not passed.
    """

    if self._is_chunked:
      return self._read_chunked(blocksize)
    else:
      return self._read_not_chunked(blocksize)

  def _read_chunked(self, blocksize: Optional[int] = None) -> bytes:
    """This method provides the read functionality from a request
    body with chunked Transfer-Encoding.
    """

    # For non-negative blocksize values.
    if blocksize and blocksize >= 0:
      # Keep buffering until we can fulfil the blocksize or there
      # are no chunks left to buffer.
      while blocksize > len(self._buffer) and not self._last_chunk_read:
        byte_chunk_size = self._body.readline()
        self._buffer += byte_chunk_size
        int_chunk_size = int(byte_chunk_size.strip(), base=16)
        self._buffer += self._body.read(int_chunk_size)
        # Consume the CLRF after each chunk.
        self._buffer += self._body.readline()
        if int_chunk_size == 0:
          # A zero sized chunk indicates that no more chunks left.
          self._last_chunk_read = True
      bytes_read, self._buffer = self._buffer[:blocksize], self._buffer[blocksize:]
      return bytes_read
    # When blocksize is a negative integer or None.
    else:
      bytes_read = b''
      while True:
        chunk = self._read_chunked(64 * 1024)
        bytes_read += chunk
        if chunk == b'':
          return bytes_read

  def _read_not_chunked(self, blocksize: Optional[int] = None) -> bytes:
    """This method provides the read functionality from a request
    body of a known Content-Length.
    """

    # Don't try to read if there is nothing to read.
    if self._left_to_read == 0:
      # This indicates `EOF` for the caller.
      return b''
    # For non-negative blocksize values.
    if blocksize and blocksize >= 0:
      size_to_read = min(blocksize, self._left_to_read)
      self._left_to_read -= size_to_read
      return self._body.read(size_to_read)
    # When blocksize is a negative integer or None.
    else:
      size_to_read, self._left_to_read = self._left_to_read, 0
      return self._body.read(size_to_read)

