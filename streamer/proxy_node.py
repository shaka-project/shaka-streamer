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

"""A module that implements a simple proxy server for uploading packaged
content to cloud storage providers (GCS and S3) and also any server that
accepts PUT requests.
"""

import io
import os
import abc
import time
import posixpath
from urllib.parse import urlparse, ParseResult
from threading import Thread, Lock
from typing import Optional, Union, Type, Dict, List
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection, HTTPResponse, HTTPSConnection, CREATED
from streamer.node_base import ProcessStatus, ThreadedNodeBase


class BodyAsFileIO(io.BufferedIOBase):
  """A class that provides a layer of access to the `rfile` property of the
  request handler.  This is done because the `rfile` can't be read on its own
  as a file since it does not have an `EOF`.  This class will encapsulate the
  logic of using Content-Length or chunk size to decide whether the read is over
  or not.  Another solution would be to read the whole request body and then
  send it, but this will be very slow for big request bodies, so this class
  is built to read the request body incrementally only when `read()` is requested.
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
    """This method is used to read `self.body` incrementally with each call.
    This is done because if we try to use `read()` on `self.body` it will wait
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
      self._buffer, bytes_read = self._buffer[blocksize:], self._buffer[:blocksize]
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


class Connection:
  """A class that encapsulates an HTTP(S)Connection with its status."""

  def __init__(self,
               ConnectionFactory: Union[Type[HTTPConnection],
                                        Type[HTTPSConnection]], host: str):
    self.connection = ConnectionFactory(host)
    self.is_used = True
    self.res_error: Optional[HTTPResponse] = None


class RequestHandler(BaseHTTPRequestHandler):
  """A request handler that processes the PUT requests coming from
  shaka packager and redirects them to the destination.
  """

  def __init__(self, conn: Connection, extra_headers: Dict[str, str],
               param_query: str, temp_dir: Optional[str], *args, **kwargs):
    self._conn = conn
    self._extra_headers = extra_headers
    self._params_and_queries = param_query
    self._temp_dir = temp_dir
    # Call `super().__init__()` last because this call is what handles the
    # actual request and we need the variables defined above to handle
    # this request.
    super().__init__(*args, **kwargs)

  def do_PUT(self):
    """do_PUT will handle the PUT requests coming from shaka packager."""

    # Don't chunk by default, as the request body is already chunked
    # or we have a content-length header which means we are not using
    # chunked transfer-encoding.
    encode_chunked = False
    content_length = self.headers['Content-Length']
    # Store the manifest files locally in `self._temp_dir`.
    if self._temp_dir is not None and self.path.endswith(('.mpd', '.m3u8')):
      body = self._write_body_and_get_file_io()
      if content_length == None:
        # We need to re-chunk it again as we wrote it as a whole
        # to the filesystem.
        encode_chunked = True
    else:
      content_length = content_length and int(content_length)
      body = BodyAsFileIO(self.rfile, content_length)
    # Add the extra headers to `self.headers`, this might contain an
    # access token for instance.
    for key, value in self._extra_headers:
      self.headers.add_header(key, value)
    # Forward the request to the connection we have with the same path as
    # how we received it.  Also include any parameters and the query string.
    self._conn.connection.request('PUT', self.path + self._params_and_queries,
                                  body, self.headers, encode_chunked=encode_chunked)
    res = self._conn.connection.getresponse()
    if res.status == CREATED:
      # Mark the connection as unused and respond to shaka packager with success.
      self._conn.is_used = False
      self.send_response(CREATED, 'Created')
      self.end_headers()
      # self.wfile.write(res.read1())
    else:
      # Set the error log to the response to log it later.
      self._conn.res_error = res
  
  def _write_body_and_get_file_io(self):
    """A method that writes a request body to the filesystem
    and returns a file io object opened for reading.
    """

    # Store the request body in `self._temp_dir`.
    # Ignore the first '/' `self.path` as posixpath will think
    # it points to the root direcotry.
    path = posixpath.join(self._temp_dir, self.path[1:])
    # With `exist_ok=True`, any intermidiate direcotries are created if needed.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as request_body_file:
      if self.headers['Content-Length'] is not None:
        content_length = int(self.headers['Content-Length'])
        request_body_file.write(self.rfile.read(content_length))
      else:
        while True:
          bytes_chunk_size = self.rfile.readline()
          int_chunk_size = int(bytes_chunk_size.strip(), base=16)
          request_body_file.write(self.rfile.read(int_chunk_size))
          # An empty newline that we have to consume.
          self.rfile.readline()
          # Chunk of size zero indicates that we have reached the end.
          if int_chunk_size == 0:
            break
    return open(path, 'rb')


class RequestHandlersManager():
  """A request handlers' manager that produces a RequestHandler whenever its
  __call__ method is called. It is used to keep a pool of connections that it
  passes to the request handler so that these connections can be reused."""

  def __init__(self, url: ParseResult, initial_headers: Dict[str, str],
               temp_dir: Optional[str], max_conns: int = 50):

    if url.scheme not in ['http', 'https']:
      # We can only instantiate HTTP/HTTPS connections.
      raise RuntimeError("Unsupported scheme: {}", url.scheme)
    self._ConnectionFactory = HTTPConnection if url.scheme == 'http' else HTTPSConnection
    self._destination_host = url.netloc
    # Store the parameters and queries to send them when requesting
    # from `self._destination_host`.
    self._params_query = ';' + url.params if url.params else ''
    self._params_query += '?' + url.query if url.query else ''
    # These headers are going to be sent to `self._destination_host`
    # with each request along with the headers that the request handler
    # receives. Note that these extra headers can possibely overwrite
    # the original request headers that the request handler received.
    self._extra_headers = initial_headers
    self._temp_dir = temp_dir
    self._max_conns = max_conns

    self._connection_pool: List[Connection] = []
    self._connection_pooling_lock = Lock()

  def __call__(self, *args, **kwargs) -> RequestHandler:
    """This magical method makes a RequestHandlersManager instance
    callable and returns a RequestHandler when called.  This means
    that a RequestHandlersManager instance is a RequestHandler factory.
    """

    return RequestHandler(self._get_a_connection(), self._extra_headers,
                          self._params_query, self._temp_dir, *args, **kwargs)

  def _get_a_connection(self) -> Connection:
    """This method looks for an unused connection in the pool and returns it
    to be used. Access to the connection pool is locked so that race conditions
    doesn't occur if the server running this request handler manager is threaded.
    """

    # Acquire the lock to make this method thread safe over
    # the shared connection pool.
    self._connection_pooling_lock.acquire()
    def _find_conn() -> Optional[Connection]:
      for conn in self._connection_pool:
        if not conn.is_used:
          conn.is_used = True
          # Release the lock before returning a valid connection.
          self._connection_pooling_lock.release()
          return conn
      return None

    # First look for an unused connection.
    conn = _find_conn()
    if conn is not None:
      return conn

    # Make another connection if we didn't yet hit the cap.
    if len(self._connection_pool) < self._max_conns:
      self._connection_pool.append(Connection(self._ConnectionFactory,
                                              self._destination_host))
      # Release the lock before returning a valid connection.
      self._connection_pooling_lock.release()
      return self._connection_pool[-1]

    # Wait until a connection is unused.
    while True:
      conn = _find_conn()
      if conn is not None:
        return conn
      time.sleep(0.1)

  def update_headers(self, **kwargs):
    self._extra_headers.update(**kwargs)


class ProxyUploadNode(ThreadedNodeBase):
  """A base class for the different uploading nodes."""

  @abc.abstractmethod
  def __init__(self, upload_location: ParseResult,
               extra_headers: Dict[str, str], temp_dir: Optional[str]):

    super().__init__(thread_name=self.__class__.__name__,
                     continue_on_exception=True,
                     sleep_time=self.get_refresh_period())

    self.req_handlers_manager = RequestHandlersManager(upload_location, 
                                                       extra_headers, temp_dir)

    self.server = ThreadingHTTPServer(('localhost', 0), self.req_handlers_manager)

    self.server_location = 'http://' + self.server.server_name + \
                           ':' + str(self.server.server_port) + \
                            upload_location.path

    self.server_thread = Thread(name=self.server_location,
                                target=self.server.serve_forever,
                                daemon=True)

  def stop(self, status: Optional[ProcessStatus]):
    self.server.shutdown()
    self.server_thread.join()
    return super().stop(status)

  def start(self):
    self.server_thread.start()
    return super().start()

  def _thread_single_pass(self):
    return self.refresh_period_passed()

  def get_refresh_period(self) -> float:
    """This method is used to set the `self._sleep_time` for a ProxyUploadNode.
    It defaults to a very long time that might be changed by subclasses
    overriding this method.
    """
    # Never thought my life is that short.
    return 60 * 60 * 24 * 365 * 100

  def refresh_period_passed(self) -> None:
    # Ideally, we will have nothing to do after each refresh period
    # which is a very long time by default.
    return


class HTTPUpload(ProxyUploadNode):
  """The ProxyUploadNode used when PUT requesting to a url using HTTP/HTTPS."""

  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str]):

    # No preprocessing needed for the upload location url or the headers.
    super().__init__(urlparse(upload_location), extra_headers, temp_dir)


class GCSUpload(ProxyUploadNode):
  """The ProxyUploadNode used when PUT requesting to a GCS bucket."""
  # https://cloud.google.com/storage/docs/uploading-objects#upload-object-xml
  # curl -X PUT --data-binary @OBJECT_LOCATION \
  # -H "Authorization: Bearer OAUTH2_TOKEN" \
  # "https://storage.googleapis.com/BUCKET_NAME/OBJECT_NAME"
  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str]):

    self.extra_headers: Dict[str, str] = {}
    super().__init__(self.extra_headers, temp_dir)

  def refresh_period_passed(self) -> None:
    pass


class S3Upload(ProxyUploadNode):
  """The ProxyUploadNode used when PUT requesting to a S3 bucket."""
  # https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html#API_PutObject_RequestSyntax
  # curl -X PUT --data-binary @OBJECT_LOCATION \
  # -H "Authorization: idk yet but it's some sort of aws specific auth" \
  # "BUCKET_NAME.s3.amazonaws.com/OBJECT_NAME"
  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str]):

    self.extra_headers: Dict[str, str] = {}
    super().__init__(self.extra_headers, temp_dir)

  def refresh_period_passed(self) -> None:
    pass


def get_upload_node(upload_location: str, extra_headers: Dict[str, str],
                    temp_dir: Optional[str] = None) -> ProxyUploadNode:
  """Instantiates an appropriate ProxyUploadNode subclass based
  on the protocol used in `upload_location` url.
  """

  if upload_location.startswith(("http://", "https://")):
    return HTTPUpload(upload_location, extra_headers, temp_dir)
  elif upload_location.startswith("gs://"):
    return GCSUpload(upload_location, extra_headers, temp_dir)
  elif upload_location.startswith("s3://"):
    return S3Upload(upload_location, extra_headers, temp_dir)
  else:
    raise RuntimeError("Protocol of [{}] isn't supported".format(upload_location))
