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

import abc
import threading
import time
import traceback
import urllib.parse

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from io import BufferedIOBase
from typing import Any, BinaryIO, Optional, Union

from streamer.node_base import ProcessStatus, ThreadedNodeBase


# HTTP status codes
HTTP_STATUS_CREATED = 201
HTTP_STATUS_ACCEPTED = 202
HTTP_STATUS_NO_CONTENT = 204
HTTP_STATUS_FAILED = 500

# S3 has a minimum chunk size for multipart uploads.
MIN_S3_CHUNK_SIZE = (5 << 20)  # 5MB


# Supported protocols.  Built based on which optional modules are available for
# cloud storage providers.
SUPPORTED_PROTOCOLS: list[str] = []

# All supported protocols.  Used to provide more useful error messages.
ALL_SUPPORTED_PROTOCOLS: list[str] = ['gs', 's3']


# Don't write the same file more than once per rate limiter period.
# For live streams, this avoids HTTP 429 "Too many request" errors.
RATE_LIMITER_PERIOD_IN_SECONDS = 2


# Optional: To support GCS, import Google Cloud Storage library.
try:
  import google.cloud.storage  # type: ignore
  import google.api_core.exceptions  # type: ignore
  SUPPORTED_PROTOCOLS.append('gs')
except:
  pass

# Optional: To support S3, import AWS's boto3 library.
try:
  import boto3  # type: ignore
  import botocore.config  # type: ignore
  SUPPORTED_PROTOCOLS.append('s3')
except:
  pass


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


class RequestHandlerBase(BaseHTTPRequestHandler):
  """A request handler that processes requests coming from Shaka Packager and
  relays them to the destination.
  """

  def __init__(self, rate_limiter: RateLimiter, *args, **kwargs):
    self._rate_limiter: RateLimiter = rate_limiter

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
    if not suppress:
      self.start_chunked(self.path)

    while True:
      # Parse the chunk size
      chunk_size_line = self.rfile.readline().strip()
      chunk_size = int(chunk_size_line, 16)

      # Read the chunk and process it
      if chunk_size != 0:
        data = self.rfile.read(chunk_size)
        if not suppress:
          self.handle_chunk(data)

      self.rfile.readline()  # Read the trailer

      if chunk_size == 0:
         break  # EOF

    # All done.
    if not suppress:
      self.end_chunked()

  def _parse_non_chunked_transfer(self, suppress: bool) -> None:
    # We have the whole file at once, with a known length.
    content_length = int(self.headers['Content-Length'])

    if suppress:
      # If |suppress|, we read the input but don't do anything with it.
      self.rfile.read(content_length)
    else:
      self.handle_non_chunked(self.path, content_length, self.rfile)

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
      self.handle_delete(self.path)
      self.send_response(HTTP_STATUS_NO_CONTENT)
    except Exception as ex:
      print('Upload failure: ' + str(ex))
      traceback.print_exc()
      self.send_response(HTTP_STATUS_FAILED)

    # If we don't call this at the end of the handler, Packager says we
    # "returned nothing".
    self.end_headers()

  @abc.abstractmethod
  def handle_non_chunked(self, path: str, length: int,
                         file: Union[BinaryIO, BufferedIOBase]) -> None:
    """Write the non-chunked data stream from |file| to the destination."""
    pass

  @abc.abstractmethod
  def start_chunked(self, path: str) -> None:
    """Set up for a chunked transfer to the destination."""
    pass

  @abc.abstractmethod
  def handle_chunk(self, data: bytes) -> None:
    """Handle a single chunk of data."""
    pass

  @abc.abstractmethod
  def end_chunked(self) -> None:
    """End the chunked transfer."""
    pass

  @abc.abstractmethod
  def handle_delete(self, path: str) -> None:
    """Delete the file from cloud storage."""
    pass

class GCSHandler(RequestHandlerBase):
  # Can't annotate the bucket here as a parameter if we don't have the library.
  def __init__(self, bucket: Any, base_path: str,
               rate_limiter: RateLimiter, *args, **kwargs) -> None:
    self._bucket: google.cloud.storage.Bucket = bucket
    self._base_path: str = base_path
    self._chunked_output: Optional[BinaryIO] = None

    # The HTTP server passes *args and *kwargs that we need to pass along, but
    # don't otherwise care about.  This must happen last, or somehow our
    # members never get set.
    super().__init__(rate_limiter, *args, **kwargs)

  def handle_non_chunked(self, path: str, length: int,
                         file: Union[BinaryIO, BufferedIOBase]) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')
    blob = self._bucket.blob(full_path)
    blob.cache_control = 'no-cache'

    # If you don't pass size=length, it tries to seek in the file, which fails.
    blob.upload_from_file(file, size=length,
                          retry=google.cloud.storage.retry.DEFAULT_RETRY)

  def start_chunked(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')
    blob = self._bucket.blob(full_path)
    blob.cache_control = 'no-cache'

    self._chunked_output = blob.open(
        'wb', retry=google.cloud.storage.retry.DEFAULT_RETRY)

  def handle_chunk(self, data: bytes) -> None:
    assert self._chunked_output is not None
    self._chunked_output.write(data)

  def end_chunked(self) -> None:
    assert self._chunked_output is not None
    self._chunked_output.close()
    self._chunked_output = None

  def handle_delete(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')
    blob = self._bucket.blob(full_path)
    try:
      blob.delete(retry=google.cloud.storage.retry.DEFAULT_RETRY)
    except google.api_core.exceptions.NotFound:
      # Some delete calls seem to throw "not found", but the files still get
      # deleted.  So ignore these and don't fail the request.
      pass


class S3Handler(RequestHandlerBase):
  # Can't annotate the client here as a parameter if we don't have the library.
  def __init__(self, client: Any, bucket_name: str, base_path: str,
               rate_limiter: RateLimiter, *args, **kwargs) -> None:
    self._client: boto3.client = client
    self._bucket_name: str = bucket_name
    self._base_path: str = base_path

    # Used for chunked uploads:
    self._upload_id: Optional[str] = None
    self._upload_path: Optional[str] = None
    self._next_part_number: int = 0
    self._part_info: list[dict[str,Any]] = []
    self._data: bytes = b''

    # The HTTP server passes *args and *kwargs that we need to pass along, but
    # don't otherwise care about.  This must happen last, or somehow our
    # members never get set.
    super().__init__(rate_limiter, *args, **kwargs)

  def handle_non_chunked(self, path: str, length: int,
                         file: Union[BinaryIO, BufferedIOBase]) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')
    # length is unused here.
    self._client.upload_fileobj(file, self._bucket_name, full_path,
                                ExtraArgs={'CacheControl': 'no-cache'})

  def start_chunked(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    self._upload_path = (self._base_path + path).strip('/')
    response = self._client.create_multipart_upload(
        Bucket=self._bucket_name, Key=self._upload_path,
        CacheControl='no-cache')

    # This ID is sent to subsequent calls into the S3 client.
    self._upload_id = response['UploadId']
    self._part_info = []
    self._next_part_number = 1

    # Multi-part uploads for S3 can't have chunks smaller than 5MB.
    # We accumulate data for chunks here.
    self._data = b''

  def handle_chunk(self, data: bytes, force: bool = False) -> None:
    # Collect data until we hit the minimum chunk size.
    self._data += data

    data_len = len(self._data)
    if data_len >= MIN_S3_CHUNK_SIZE or (data_len and force):
      response = self._client.upload_part(
          Bucket=self._bucket_name, Key=self._upload_path,
          PartNumber=self._next_part_number, UploadId=self._upload_id,
          Body=self._data)

      # We have to collect this data, in this format, to finish the multipart
      # upload later.
      self._part_info.append({
        'PartNumber': self._next_part_number,
        'ETag': response['ETag'],
      })
      self._next_part_number += 1
      self._data = b''

  def end_chunked(self) -> None:
    # Flush the buffer.
    self.handle_chunk(b'', force=True)

    # Complete the multipart upload.
    upload_info = { 'Parts': self._part_info }
    self._client.complete_multipart_upload(
        Bucket=self._bucket_name, Key=self._upload_path,
        UploadId=self._upload_id, MultipartUpload=upload_info)
    self._upload_id = None
    self._upload_path = None
    self._next_part_number = 0
    self._part_info = []

  def handle_delete(self, path: str) -> None:
    self._client.delete_object(
        Bucket=self._bucket_name, Key=self._upload_path)


class HTTPUploadBase(ThreadedNodeBase):
  """Runs an HTTP server at `self.server_location` to upload to cloud.

  Subclasses handle upload to specific cloud storage providers.

  The local HTTP server at `self.server_location` can only ingest PUT requests.
  """
  server: Optional[ThreadingHTTPServer] = None
  server_location: str = ''
  server_thread: Optional[threading.Thread] = None

  def __init__(self) -> None:
    super().__init__(thread_name=self.__class__.__name__,
                     continue_on_exception=True,
                     sleep_time=3)
    self._rate_limiter = RateLimiter()

  @abc.abstractmethod
  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    pass

  def start(self) -> None:
    # Will be started early to get server location.
    if self.server is not None:
      return

    handler_factory = (
        lambda *args, **kwargs: self.create_handler(*args, **kwargs))

    # By specifying port 0, a random unused port will be chosen for the server.
    self.server = ThreadingHTTPServer(
        ('localhost', 0), handler_factory)
    self.server_location = (
        'http://' + self.server.server_name +
        ':' + str(self.server.server_port))

    self.server_thread = threading.Thread(
        name=self.server_location, target=self.server.serve_forever)
    self.server_thread.start()

    return super().start()

  def stop(self, status: Optional[ProcessStatus]) -> None:
    if self.server:
      self.server.shutdown()
      self.server = None
    if self.server_thread:
      self.server_thread.join()
      self.server_thread = None
    return super().stop(status)

  def check_status(self) -> ProcessStatus:
    # This makes sure this node will never prevent the shutdown of the whole
    # system.  It will be stopped explicitly when ControllerNode tears down.
    return ProcessStatus.Finished

  def _thread_single_pass(self) -> None:
    # Nothing to do here.
    return


class GCSUpload(HTTPUploadBase):
  """Upload to Google Cloud Storage."""

  def __init__(self, upload_location: str) -> None:
    super().__init__()

    url = urllib.parse.urlparse(upload_location)
    self._client = google.cloud.storage.Client()
    self._bucket = self._client.bucket(url.netloc)
    # Strip both left and right slashes.  Otherwise, we get a blank folder name.
    self._base_path = url.path.strip('/')

  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    return GCSHandler(self._bucket, self._base_path,
                      self._rate_limiter, *args, **kwargs)


class S3Upload(HTTPUploadBase):
  """Upload to Amazon S3."""

  def __init__(self, upload_location: str) -> None:
    super().__init__()

    url = urllib.parse.urlparse(upload_location)
    config = botocore.config.Config(retries = {'mode': 'standard'})
    self._client = boto3.client('s3', config=config)
    self._bucket_name = url.netloc
    # Strip both left and right slashes.  Otherwise, we get a blank folder name.
    self._base_path = url.path.strip('/')

  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    return S3Handler(self._client, self._bucket_name, self._base_path,
                     self._rate_limiter, *args, **kwargs)


class ProxyNode(object):
  SUPPORTED_PROTOCOLS = SUPPORTED_PROTOCOLS
  ALL_SUPPORTED_PROTOCOLS = ALL_SUPPORTED_PROTOCOLS

  @staticmethod
  def create(upload_location: str) -> HTTPUploadBase:
    """Creates an upload node based on the protocol used in |upload_location|."""
    if upload_location.startswith("gs://"):
      return GCSUpload(upload_location)
    elif upload_location.startswith("s3://"):
      return S3Upload(upload_location)
    else:
      raise RuntimeError("Protocol of {} isn't supported".format(upload_location))

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
