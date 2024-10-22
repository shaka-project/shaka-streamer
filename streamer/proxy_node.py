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
import traceback
import urllib.parse
from typing import IO, Optional
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from streamer.node_base import ProcessStatus, ThreadedNodeBase


HTTP_STATUS_CREATED = 201
HTTP_STATUS_FAILED = 500
MAX_CHUNK_SIZE = (1 << 20)  # 1 MB


# Supported protocols.  Built based on which optional modules are available for
# cloud storage providers.
SUPPORTED_PROTOCOLS: list[str] = []

# All supported protocols.  Used to provide more useful error messages.
ALL_SUPPORTED_PROTOCOLS: list[str] = ['gs', 's3']


try:
  import google.cloud.storage as gcs  # type: ignore
  SUPPORTED_PROTOCOLS.append('gs')
except:
  pass

try:
  import boto3 as aws  # type: ignore
  SUPPORTED_PROTOCOLS.append('s3')
except:
  pass


class RequestHandlerBase(BaseHTTPRequestHandler):
  """A request handler that processes the PUT requests coming from
  Shaka Packager and pushes them to the destination.
  """
  def do_PUT(self) -> None:
    """Handle the PUT requests coming from Shaka Packager."""
    try:
      if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
        self.start_chunked(self.path)

        while True:
          # Parse the chunk size
          chunk_size_line = self.rfile.readline().strip()
          chunk_size = int(chunk_size_line, 16)

          # Read the chunk and process it
          if chunk_size != 0:
            self.handle_chunk(self.rfile.read(chunk_size))
          self.rfile.readline()  # Read the trailer

          if chunk_size == 0:
             break  # EOF

        self.end_chunked()
      else:
        content_length = int(self.headers['Content-Length'])
        if content_length != 0:
          self.handle_non_chunked(self.path, content_length, self.rfile)

      self.rfile.close()
      self.send_response(HTTP_STATUS_CREATED)
    except Exception as ex:
      print('Upload failure: ' + str(ex))
      traceback.print_exc()
      self.send_response(HTTP_STATUS_FAILED)
    self.end_headers()

  @abc.abstractmethod
  def handle_non_chunked(self, path: str, length: int, file: IO) -> None:
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


class GCSHandler(RequestHandlerBase):
  def __init__(self, bucket: gcs.Bucket, base_path: str,
               *args, **kwargs) -> None:
    self._bucket = bucket
    self._base_path = base_path

    # The HTTP server passes *args and *kwargs that we need to pass along, but
    # don't otherwise care about.
    super().__init__(*args, **kwargs)

  def handle_non_chunked(self, path: str, length: int, file: IO) -> None:
    full_path = self._base_path + path
    blob = self._bucket.blob(full_path)
    blob.upload_from_file(file, size=length, retries=3)

  def start_chunked(self, path: str) -> None:
    full_path = self._base_path + path
    blob = self._bucket.blob(full_path)
    self._chunk_file = blob.open('wb')

  def handle_chunk(self, data: bytes) -> None:
    self._chunk_file.write(data)

  def end_chunked(self) -> None:
    self._chunk_file.close()


class S3Handler(RequestHandlerBase):
  def __init__(self, upload_location: str, *args, **kwargs) -> None:
    self._upload_location = upload_location

    # The HTTP server passes *args and *kwargs that we need to pass along, but
    # don't otherwise care about.
    super().__init__(*args, **kwargs)

  def handle_non_chunked(self, path: str, length: int, file: IO) -> None:
    # FIXME: S3 upload
    pass

  def start_chunked(self, path: str) -> None:
    # FIXME: S3 upload
    pass

  def handle_chunk(self, data: bytes) -> None:
    # FIXME: S3 upload
    pass

  def end_chunked(self) -> None:
    # FIXME: S3 upload
    pass


class HTTPUploadBase(ThreadedNodeBase):
  """Runs an HTTP server at `self.server_location` to upload to cloud.

  Subclasses handle upload to specific cloud storage providers.

  The local HTTP server at `self.server_location` can only ingest PUT requests.
  """

  def __init__(self) -> None:
    super().__init__(thread_name=self.__class__.__name__,
                     continue_on_exception=True,
                     sleep_time=3)

    handler_factory = (
        lambda *args, **kwargs: self.create_handler(*args, **kwargs))

    # By specifying port 0, a random unused port will be chosen for the server.
    self.server = ThreadingHTTPServer(('localhost', 0), handler_factory)

    self.server_location = 'http://' + self.server.server_name + \
                           ':' + str(self.server.server_port)

    self.server_thread = threading.Thread(name=self.server_location,
                                          target=self.server.serve_forever)

  @abc.abstractmethod
  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    pass

  def stop(self, status: Optional[ProcessStatus]) -> None:
    self.server.shutdown()
    self.server_thread.join()
    return super().stop(status)

  def start(self) -> None:
    self.server_thread.start()
    return super().start()

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
    url = urllib.parse.urlparse(upload_location)
    self._client = gcs.Client()
    self._bucket = self._client.bucket(url.netloc)
    # Strip both left and right slashes.  Otherwise, we get a blank folder name.
    self._base_path = url.path.strip('/')
    super().__init__()

  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    return GCSHandler(self._bucket, self._base_path, *args, **kwargs)


class S3Upload(HTTPUploadBase):
  """Upload to Amazon S3."""

  def __init__(self, upload_location: str) -> None:
    self._upload_location = upload_location
    super().__init__()

  def create_handler(self, *args, **kwargs) -> BaseHTTPRequestHandler:
    """Returns a cloud-provider-specific request handler to upload to cloud."""
    return S3Handler(self._upload_location, *args, **kwargs)


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
