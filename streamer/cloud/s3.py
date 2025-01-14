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

"""Upload to Amazon S3."""

import urllib.parse

from typing import Any, Optional

import boto3  # type: ignore
import botocore.config  # type: ignore

from streamer.cloud.base import CloudUploaderBase


# S3 has a minimum chunk size for multipart uploads.
MIN_S3_CHUNK_SIZE = (5 << 20)  # 5MB


class S3Uploader(CloudUploaderBase):
  """See base class for interface docs."""

  def __init__(self, upload_location: str) -> None:
    # Parse the upload location (URL).
    url = urllib.parse.urlparse(upload_location)

    config = botocore.config.Config(retries = {'mode': 'standard'})
    self._client = boto3.client('s3', config=config)

    # If upload_location is "s3://foo/bar", url.netloc is "foo", which is the
    # bucket name.
    self._bucket_name = url.netloc

    # Strip both left and right slashes.  Otherwise, we get a blank folder name.
    self._base_path = url.path.strip('/')

    # State for chunked uploads:
    self._upload_id: Optional[str] = None
    self._upload_path: Optional[str] = None
    self._next_part_number: int = 0
    self._part_info: list[dict[str,Any]] = []
    self._data: bytes = b''

  def write_non_chunked(self, path: str, data: bytes) -> None:
    # No leading slashes, or we get a blank folder name.
    full_path = (self._base_path + path).strip('/')

    # Write the whole object at once.
    self._client.put_object(Body=data, Bucket=self._bucket_name, Key=full_path,
                            ExtraArgs={'CacheControl': 'no-cache'})

  def start_chunked(self, path: str) -> None:
    # No leading slashes, or we get a blank folder name.
    self._upload_path = (self._base_path + path).strip('/')

    # Ask the client to start a multi-part upload.
    response = self._client.create_multipart_upload(
        Bucket=self._bucket_name, Key=self._upload_path,
        CacheControl='no-cache')

    # This ID is sent to subsequent calls into the S3 client.
    self._upload_id = response['UploadId']

    # We must accumulate metadata about each part to complete the file at the
    # end of the chunked transfer.
    self._part_info = []
    # We must also number the parts.
    self._next_part_number = 1
    # Multi-part uploads for S3 can't have chunks smaller than 5MB.
    # We accumulate data for chunks here.
    self._data = b''

  def write_chunk(self, data: bytes, force: bool = False) -> None:
    # Collect data until we hit the minimum chunk size.
    self._data += data

    data_len = len(self._data)
    if data_len >= MIN_S3_CHUNK_SIZE or (data_len and force):
      # Upload one "part", which may be comprised of multiple HTTP chunks from
      # Packager.
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
    self.write_chunk(b'', force=True)

    # Complete the multipart upload.
    upload_info = { 'Parts': self._part_info }
    self._client.complete_multipart_upload(
        Bucket=self._bucket_name, Key=self._upload_path,
        UploadId=self._upload_id, MultipartUpload=upload_info)
    self.reset()

  def delete(self, path: str) -> None:
    self._client.delete_object(
        Bucket=self._bucket_name, Key=self._upload_path)

  def reset(self) -> None:
    self._upload_id = None
    self._upload_path = None
    self._next_part_number = 0
    self._part_info = []
    self._data = b''
