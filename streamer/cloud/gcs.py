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

"""Upload to Google Cloud Storage."""

import urllib.parse

from typing import BinaryIO, Optional

import google.cloud.storage  # type: ignore
import google.api_core.exceptions  # type: ignore

from streamer.cloud.base import CloudUploaderBase


class GCSUploader(CloudUploaderBase):
  """See base class for interface docs."""

  def __init__(self, upload_location: str) -> None:
    # Parse the upload location (URL).
    url = urllib.parse.urlparse(upload_location)

    self._client = google.cloud.storage.Client()
    # If upload_location is "gs://foo/bar", url.netloc is "foo", which is the
    # bucket name.
    self._bucket = self._client.bucket(url.netloc)

    # Strip both left and right slashes.  Otherwise, we get a blank folder name.
    self._base_path = url.path.strip('/')

    # A file-like object from the Google Cloud Storage module that we write to
    # during a chunked upload.
    self._chunked_output: Optional[BinaryIO] = None

  def write_non_chunked(self, path: str, data: bytes) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')

    # An object representing the destination blob.
    blob = self._bucket.blob(full_path)
    blob.cache_control = 'no-cache'

    # A file-like interface to that blob.
    output = blob.open('wb', retry=google.cloud.storage.retry.DEFAULT_RETRY)
    output.write(data)
    output.close()

  def start_chunked(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')

    # An object representing the destination blob.
    blob = self._bucket.blob(full_path)
    blob.cache_control = 'no-cache'

    # A file-like interface to that blob.
    self._chunked_output = blob.open(
        'wb', retry=google.cloud.storage.retry.DEFAULT_RETRY)

  def write_chunk(self, data: bytes) -> None:
    assert self._chunked_output is not None
    self._chunked_output.write(data)

  def end_chunked(self) -> None:
    self.reset()

  def delete(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')
    blob = self._bucket.blob(full_path)
    try:
      blob.delete(retry=google.cloud.storage.retry.DEFAULT_RETRY)
    except google.api_core.exceptions.NotFound:
      # Some delete calls seem to throw "not found", but the files still get
      # deleted.  So ignore these and don't fail the request.
      pass

  def reset(self) -> None:
    if self._chunked_output:
      self._chunked_output.close()
      self._chunked_output = None
