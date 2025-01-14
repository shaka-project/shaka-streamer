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

"""A simple proxy server to upload to cloud stroage providers."""

import time
import traceback
import urllib.parse

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Union

from streamer.node_base import ProcessStatus, ThreadedNodeBase

from streamer.cloud.pool import Pool
from streamer.cloud.uploader import ALL_SUPPORTED_PROTOCOLS, SUPPORTED_PROTOCOLS


# HTTP status codes
HTTP_STATUS_CREATED = 201
HTTP_STATUS_ACCEPTED = 202
HTTP_STATUS_NO_CONTENT = 204
HTTP_STATUS_FAILED = 500


# Don't write the same file more than once per rate limiter period.
# For live streams, this avoids HTTP 429 "Too many request" errors.
RATE_LIMITER_PERIOD_IN_SECONDS = 2


class RateLimiter(object):
  """A rate limiter that tracks which files we have written to recently."""

  def __init__(self) -> None:
    self._reset(time.time())

  def suppress(self, path) -> bool:
    """Returns true if you should skip this upload."""

    now = time.time()
    if now > self._last_check + RATE_LIMITER_PERIOD_IN_SECONDS:
      self._reset(now)

    if path in self._recent_files:
      return True  # skip

    self._recent_files.add(path)
    return False  # upload

  def _reset(self, now: float) -> None:
    # These files are only valid for RATE_LIMITER_PERIOD_IN_SECONDS.
    # After that, they get cleared.
    self._recent_files: set[str] = set()

    # The timestamp of the last check; the start of the rate limiter period.
    self._last_check: float = now


class RequestHandler(BaseHTTPRequestHandler):
  """A request handler that processes requests coming from Shaka Packager and
  relays them to the destination.
  """

  def __init__(self, rate_limiter: RateLimiter, pool: Pool,
               *args, **kwargs) -> None:
    self._rate_limiter: RateLimiter = rate_limiter
    self._pool: Pool = pool

    # The HTTP server passes *args and *kwargs that we need to pass along, but
    # don't otherwise care about.  This must happen last, or somehow our
    # members never get set.
    super().__init__(*args, **kwargs)

  # NOTE: The default values here for log_request are taken from the base
  # class, and not a design decision of ours.
  def log_request(self, code: Union[int, str] = '-', size: Union[int, str] = '-') -> None:
    """Override the request logging feature of the Python HTTP server."""
    try:
      code_int = int(code)
    except:
      code_int = 0

    if code_int >= 200 and code_int <= 299:
      # Stub out log_request to avoid creating noise from the HTTP server when
      # requests are successful.
      return

    return super().log_request(code, size)

  def _parse_chunked_transfer(self, suppress: bool) -> None:
    # Here we parse the chunked transfer encoding and delegate to the
    # subclass's start/chunk/end methods.  If |suppress|, we parse the input
    # but don't do anything with it.
    with self._pool.get_worker() as worker:
      if not suppress:
        worker.start_chunked(self.path)

      while True:
        # Parse the chunk size
        chunk_size_line = self.rfile.readline().strip()
        chunk_size = int(chunk_size_line, 16)

        # Read the chunk and process it
        if chunk_size != 0:
          data = self.rfile.read(chunk_size)
          if not suppress:
            worker.write_chunk(data)

        self.rfile.readline()  # Read the trailer

        if chunk_size == 0:
           break  # EOF

      # All done.
      if not suppress:
        worker.end_chunked()

  def _parse_non_chunked_transfer(self, suppress: bool) -> None:
    # We have the whole file at once, with a known length.
    content_length = int(self.headers['Content-Length'])

    if suppress:
      # If |suppress|, we read the input but don't do anything with it.
      self.rfile.read(content_length)
    else:
      with self._pool.get_worker() as worker:
        worker.write_non_chunked(self.path, self.rfile.read(content_length))

  def do_PUT(self) -> None:
    """Handle PUT requests coming from Shaka Packager."""
    suppress = self._rate_limiter.suppress(self.path)

    try:
      if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
        self._parse_chunked_transfer(suppress)
      else:
        self._parse_non_chunked_transfer(suppress)

      # Close the input and respond.
      self.rfile.close()
      self.send_response(HTTP_STATUS_ACCEPTED if suppress else HTTP_STATUS_CREATED)
    except Exception as ex:
      print('Upload failure: ' + str(ex))
      traceback.print_exc()
      self.send_response(HTTP_STATUS_FAILED)

    # If we don't call this at the end of the handler, Packager says we
    # "returned nothing".
    self.end_headers()

  def do_DELETE(self) -> None:
    """Handle DELETE requests coming from Shaka Packager."""
    try:
      with self._pool.get_worker() as worker:
        worker.delete(self.path)
      self.send_response(HTTP_STATUS_NO_CONTENT)
    except Exception as ex:
      print('Upload failure: ' + str(ex))
      traceback.print_exc()
      self.send_response(HTTP_STATUS_FAILED)

    # If we don't call this at the end of the handler, Packager says we
    # "returned nothing".
    self.end_headers()


class ProxyNode(ThreadedNodeBase):
  """Runs an HTTP server at `self.server_location` to upload to cloud.

  Subclasses handle upload to specific cloud storage providers.

  The local HTTP server at `self.server_location` can only ingest PUT requests.
  """
  SUPPORTED_PROTOCOLS = SUPPORTED_PROTOCOLS
  ALL_SUPPORTED_PROTOCOLS = ALL_SUPPORTED_PROTOCOLS

  server_location: str = ''

  def __init__(self, upload_location: str, pool_size: int) -> None:
    super().__init__(thread_name=self.__class__.__name__,
                     continue_on_exception=True,
                     sleep_time=3)
    if not ProxyNode.is_supported(upload_location):
      raise RuntimeError("Protocol of {} isn't supported".format(upload_location))

    self._upload_location = upload_location
    self._rate_limiter = RateLimiter()
    self._server: Optional[ThreadingHTTPServer] = None
    self._pool: Optional[Pool] = None
    self._pool_size: int = pool_size

  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    assert self._pool is not None
    return RequestHandler(self._rate_limiter, self._pool, *args, **kwargs)

  def start(self) -> None:
    # Will be started early to get server location.
    if self._server is not None:
      return

    self._pool = Pool(self._upload_location, self._pool_size)

    handler_factory = (
        lambda *args, **kwargs: self.create_handler(*args, **kwargs))

    # By specifying port 0, a random unused port will be chosen for the server.
    self._server = ThreadingHTTPServer(
        ('localhost', 0), handler_factory)
    self.server_location = (
        'http://' + self._server.server_name +
        ':' + str(self._server.server_port))

    return super().start()

  def stop(self, status: Optional[ProcessStatus]) -> None:
    if self._server:
      self._server.shutdown()
      self._server = None
    if self._pool:
      self._pool.close()
      self._pool = None
    return super().stop(status)

  def check_status(self) -> ProcessStatus:
    # This makes sure this node will never prevent the shutdown of the whole
    # system.  It will be stopped explicitly when ControllerNode tears down.
    return ProcessStatus.Finished

  def _thread_single_pass(self) -> None:
    assert self._server is not None
    # Will terminate on server.shutdown().
    self._server.serve_forever()

  @staticmethod
  def is_understood(upload_location: str) -> bool:
    """Is the URL understood, independent of libraries available?"""
    url = urllib.parse.urlparse(upload_location)
    return url.scheme in ALL_SUPPORTED_PROTOCOLS

  @staticmethod
  def is_supported(upload_location: str) -> bool:
    """Is the URL supported with the libraries available?"""
    url = urllib.parse.urlparse(upload_location)
    return url.scheme in SUPPORTED_PROTOCOLS
