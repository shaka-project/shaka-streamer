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

import os
import json
import threading
import urllib.parse
from typing import Optional, Union, Dict
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection, HTTPSConnection, CREATED, OK

from streamer.node_base import ProcessStatus, ThreadedNodeBase
from streamer.util import RequestBodyAsFileIO


# Protocols we have classes for to handle them.
SUPPORTED_PROTOCOLS = ['http', 'https', 'gs', 's3']


class RequestHandler(BaseHTTPRequestHandler):
  """A request handler that processes the PUT requests coming from
  shaka packager and pushes them to the destination.
  """

  def __init__(self, conn: Union[HTTPConnection, HTTPSConnection],
               extra_headers: Dict[str, str], base_path: str, param_query: str,
               temp_dir: Optional[str], *args, **kwargs):

    self._conn = conn
    # Extra headers to add when sending the request to the host
    # using `self._conn`.
    self._extra_headers = extra_headers
    # The base path that will be prepended to the path of the handled request
    # before forwarding the request to the host using `self._conn`.
    self._base_path = base_path
    # Parameters and query string to send in the url with each forwarded request.
    self._params_and_querystring = param_query
    self._temp_dir = temp_dir
    # Call `super().__init__()` last because this call is what handles the
    # actual request and we need the variables defined above to handle
    # this request.
    super().__init__(*args, **kwargs)

  def do_PUT(self):
    """do_PUT will handle the PUT requests coming from shaka packager."""

    headers = {}
    # Use the same headers for requesting.
    for k, v in self.headers.items():
      if k.lower() != 'host':
        headers[k] = v
    # Add the extra headers, this might contain an access token for instance.
    for k, v in self._extra_headers.items():
      headers[k] = v

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
      body = RequestBodyAsFileIO(self.rfile, content_length)

    # The url will be the result of joining the base path we should
    # send the request to with the path this request came to.
    url = self._base_path + self.path
    # Also include any parameters and the query string.
    url += self._params_and_querystring

    self._conn.request('PUT', url, body, headers, encode_chunked=encode_chunked)
    res = self._conn.getresponse()
    # Disable response logging.
    self.log_request = lambda _: None
    # Respond to Shaka Packager with the response we got.
    self.send_response(res.status)
    self.end_headers()
    # self.wfile.write(res.read())
    # The destination should send (201/CREATED), but some do also send (200/OK).
    if res.status != CREATED and res.status != OK:
      print('Unexpected status for the PUT request:'
             ' {}, ErrMsg: {!r}'.format(res.status, res.read()))

  def _write_body_and_get_file_io(self):
    """A method that writes a request body to the filesystem
    and returns a file io object opened for reading.
    """

    # Store the request body in `self._temp_dir`.
    # Ignore the first '/' `self.path` as posixpath will think
    # it points to the root direcotry.
    path = os.path.join(self._temp_dir, self.path[1:])
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


class RequestHandlersFactory():
  """A request handlers' factory that produces a RequestHandler whenever
  its __call__ method is called.  It stores all the relevant data that the
  instantiated request handler will need when sending a request to the host.
  """

  def __init__(self, upload_location: str, initial_headers: Dict[str, str] = {},
               temp_dir: Optional[str] = None, max_conns: int = 50):

    url = urllib.parse.urlparse(upload_location)
    if url.scheme not in ['http', 'https']:
      # We can only instantiate HTTP/HTTPS connections.
      raise RuntimeError("Unsupported scheme: {}", url.scheme)
    self._ConnectionFactory = HTTPConnection if url.scheme == 'http' \
                              else HTTPSConnection
    self._destination_host = url.netloc
    # Store the url path to prepend it to the path of each handled
    # request before forwarding the request to `self._destination_host`.
    self._base_path = url.path
    # Store the parameters and the query string to send them in
    # any request going to `self._destination_host`.
    self._params_query = ';' + url.params if url.params else ''
    self._params_query += '?' + url.query if url.query else ''
    # These headers are going to be sent to `self._destination_host`
    # with each request along with the headers that the request handler
    # receives.  Note that these extra headers can possibely overwrite
    # the original request headers that the request handler received.
    self._extra_headers = initial_headers
    self._temp_dir = temp_dir
    self._max_conns = max_conns

  def __call__(self, *args, **kwargs) -> RequestHandler:
    """This magical method makes a RequestHandlersFactory instance
    callable and returns a RequestHandler when called.
    """

    connection = self._ConnectionFactory(self._destination_host)
    return RequestHandler(connection, self._extra_headers,
                          self._base_path, self._params_query, self._temp_dir,
                          *args, **kwargs)

  def update_headers(self, **kwargs):
    self._extra_headers.update(**kwargs)


class HTTPUpload(ThreadedNodeBase):
  """A ThreadedNodeBase subclass that launches a local threaded
  HTTP server running at `self.server_location` and connected to
  the host of `upload_location`.  The requests sent to this server
  will be sent to the `upload_location` after adding `extra_headers`
  to its headers.  if `temp_dir` argument was not None, DASH and HLS
  manifests will be stored in it before sending them to `upload_location`.

  The local HTTP server at `self.server_location` can only ingest PUT requests.
  """

  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str],
               periodic_job_wait_time: float = 3600 * 24 * 365.25):

    super().__init__(thread_name=self.__class__.__name__,
                     continue_on_exception=True,
                     sleep_time=periodic_job_wait_time)

    self.temp_dir = temp_dir
    self.RequestHandlersFactory = RequestHandlersFactory(upload_location,
                                                         extra_headers,
                                                         self.temp_dir)

    # By specifying port 0, a random unused port will be chosen for the server.
    self.server = ThreadingHTTPServer(('localhost', 0),
                                      self.RequestHandlersFactory)

    self.server_location = 'http://' + self.server.server_name + \
                           ':' + str(self.server.server_port)

    self.server_thread = threading.Thread(name=self.server_location,
                                          target=self.server.serve_forever)

  def stop(self, status: Optional[ProcessStatus]):
    self.server.shutdown()
    self.server_thread.join()
    return super().stop(status)

  def start(self):
    self.server_thread.start()
    return super().start()

  def _thread_single_pass(self):
    return self.periodic_job()

  def periodic_job(self) -> None:
    # Ideally, we will have nothing to do periodically after the wait time
    # which is a very long time by default.  However, this can be overridden
    # by subclasses and populated with calls to all the functions that need
    # to be executed periodically.
    return


class GCSUpload(HTTPUpload):
  """The upload node used when PUT requesting to a GCS bucket.

  It will parse the `upload_location` argument with `gs://` protocol
  and use the GCP REST API that uses HTTPS protocol instead.
  """

  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str]):
    upload_location = 'https://storage.googleapis.com/' + upload_location[5:]

    # Normalize the extra headers dictionary.
    for key in list(extra_headers.copy()):
      extra_headers[key.lower()] = extra_headers.pop(key)

    # We don't have to get a refresh token.  Maybe there is an access token
    # provided and we won't outlive it anyway, but that's the user's responsibility.
    self.refresh_token = extra_headers.pop('refresh-token', None)
    self.client_id = extra_headers.pop('client-id', None)
    self.client_secret = extra_headers.pop('client-secret', None)
    # The access token expires after 3600s in GCS.
    refresh_period = int(extra_headers.pop('refresh-every', None) or 3300)

    super().__init__(upload_location, extra_headers, temp_dir, refresh_period)

    # We yet don't have an access token, so we need to get a one.
    self._refresh_access_token()

  def _refresh_access_token(self):
    if (self.refresh_token is not None
        and self.client_id is not None
        and self.client_secret is not None):
      conn = HTTPSConnection('oauth2.googleapis.com')
      req_body = {
        'grant_type': 'refresh_token',
        'refresh_token': self.refresh_token,
        'client_id': self.client_id,
        'client_secret': self.client_secret,
      }
      conn.request('POST', '/token', json.dumps(req_body))
      res = conn.getresponse()
      if res.status == OK:
        res_body = json.loads(res.read())
        # Update the Authorization header that the request factory has.
        auth = res_body['token_type'] + ' ' + res_body['access_token']
        self.RequestHandlersFactory.update_headers(Authorization=auth)
      else:
        print("Couldn't refresh access token. ErrCode: {}, ErrMst: {!r}".format(
            res.status, res.read()))
    else:
      print("Non sufficient info provided to refresh the access token.")
      print("To refresh access token periodically, 'refresh-token', 'client-id'"
            " and 'client-secret' headers must be provided.")
      print("After the current access token expires, the upload will fail.")

  def periodic_job(self) -> None:
    self._refresh_access_token()


class S3Upload(HTTPUpload):
  """The upload node used when PUT requesting to a S3 bucket.

  It will parse the `upload_location` argument with `s3://` protocol
  and use the AWS REST API that uses HTTPS protocol instead.
  """

  def __init__(self, upload_location: str, extra_headers: Dict[str, str],
               temp_dir: Optional[str]):
    raise NotImplementedError("S3 uploads aren't working yet.")
    url_parts = upload_location[5:].split('/', 1)
    bucket = url_parts[0]
    path = '/' + url_parts[1] if len(url_parts) > 1 else ''
    upload_location = 'https://' + bucket + '.s3.amazonaws.com' + path

    # We don't have to get a refresh token.  Maybe there is an access token
    # provided and we won't outlive it anyway, but that's the user's responsibility.
    self.refresh_token = extra_headers.pop('refresh-token', None)
    self.client_id = extra_headers.pop('client-id', None)
    # The access token expires after 3600s in S3.
    refresh_period = int(extra_headers.pop('refresh-every', None) or 3300)

    super().__init__(upload_location, extra_headers, temp_dir, refresh_period)

    # We yet don't have an access token, so we need to get a one.
    self._refresh_access_token()

  def _refresh_access_token(self):
    if (self.refresh_token is not None and self.client_id is not None):
      conn = HTTPSConnection('api.amazon.com')
      req_body = {
        'grant_type': 'refresh_token',
        'refresh_token': self.refresh_token,
        'client_id': self.client_id,
      }
      conn.request('POST', '/auth/o2/token', json.dumps(req_body))
      res = conn.getresponse()
      if res.status == OK:
        res_body = json.loads(res.read())
        # Update the Authorization header that the request factory has.
        auth = res_body['token_type'] + ' ' + res_body['access_token']
        self.RequestHandlersFactory.update_headers(Authorization=auth)
      else:
        print("Couldn't refresh access token. ErrCode: {}, ErrMst: {!r}".format(
            res.status, res.read()))
    else:
      print("Non sufficient info provided to refresh the access token.")
      print("To refresh access token periodically, 'refresh-token'"
            " and 'client-id' headers must be provided.")
      print("After the current access token expires, the upload will fail.")

  def periodic_job(self) -> None:
    self._refresh_access_token()


def get_upload_node(upload_location: str, extra_headers: Dict[str, str],
                    temp_dir: Optional[str] = None) -> HTTPUpload:
  """Instantiates an appropriate HTTPUpload node based on the protocol
  used in `upload_location` url.
  """

  if upload_location.startswith(("http://", "https://")):
    return HTTPUpload(upload_location, extra_headers, temp_dir)
  elif upload_location.startswith("gs://"):
    return GCSUpload(upload_location, extra_headers, temp_dir)
  elif upload_location.startswith("s3://"):
    return S3Upload(upload_location, extra_headers, temp_dir)
  else:
    raise RuntimeError("Protocol of {} isn't supported".format(upload_location))

def is_supported_protocol(upload_location: str) -> bool:
  return bool([upload_location.startswith(protocol + '://') for
               protocol in SUPPORTED_PROTOCOLS].count(True))
