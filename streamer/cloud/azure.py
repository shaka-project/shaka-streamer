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

"""Upload to Azure Blob Storage."""

import io
import urllib.parse
from typing import Optional

from azure.storage.blob import BlobServiceClient, BlobClient  # type: ignore
from azure.core.exceptions import ResourceNotFoundError  # type: ignore
from azure.identity import DefaultAzureCredential  # type: ignore

from streamer.cloud.base import CloudUploaderBase


# Azure Append Blobs can accept chunks of any size, but we'll use a reasonable buffer size.
APPEND_BLOB_BUFFER_SIZE = (4 << 20)  # 4MB


class AzureStorageUploader(CloudUploaderBase):
  """See base class for interface docs."""

  def __init__(self, upload_location: str) -> None:
    # Parse the upload location (URL).
    # Expected format: azure://storageaccount.blob.core.windows.net/container/path
    url = urllib.parse.urlparse(upload_location)
    if not url.netloc:
      raise ValueError(f"Invalid Azure storage URL format: {upload_location}")

    # Extract storage account from the netloc
    # netloc format: storageaccount.blob.core.windows.net
    account_url = f"https://{url.netloc}"

    # Initialize the BlobServiceClient with DefaultAzureCredential
    try:
      credential = DefaultAzureCredential()
      self._blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
    except Exception as e:
      raise RuntimeError(f"Failed to initialize Azure credentials for {account_url}: {e}")

    # Extract container name and base path from the URL path
    # First part of path is container, everything after is base path
    path_parts = url.path.strip('/').split('/', 1)
    if not path_parts or not path_parts[0]:
      raise ValueError(f"Container name not found in URL: {upload_location}")

    self._container_name = path_parts[0]
    # Base path within the container (everything after container name)
    self._base_path = path_parts[1] if len(path_parts) > 1 else ''

    # State for chunked uploads:
    self._blob_client: Optional[BlobClient] = None
    self._data_buffer: bytes = b''

  def write_non_chunked(self, path: str, data: bytes) -> None:
    """Write the non-chunked data to the destination."""
    full_path = self._get_full_path(path)

    blob_client = self._blob_service_client.get_blob_client(
        container=self._container_name,
        blob=full_path
    )

    # Upload the blob with cache control headers
    blob_client.upload_blob(
        data=data,
        overwrite=True
    )

  def start_chunked(self, path: str) -> None:
    """Set up for a chunked transfer to the destination."""
    full_path = self._get_full_path(path)

    self._blob_client = self._blob_service_client.get_blob_client(
        container=self._container_name,
        blob=full_path
    )

    self._blob_client.create_append_blob()

    # Reset state for new chunked upload
    self._data_buffer = b''

  def write_chunk(self, data: bytes, force: bool = False) -> None:
    """Handle a single chunk of data."""
    if not self._blob_client:
      raise RuntimeError("start_chunked() must be called before write_chunk()")

    # Accumulate data in buffer
    self._data_buffer += data

    # Append data when we have enough data or when forced
    buffer_size = len(self._data_buffer)
    if buffer_size >= APPEND_BLOB_BUFFER_SIZE or (buffer_size > 0 and force):
      # Append the data to the blob
      self._blob_client.append_block(
          data=self._data_buffer
      )

      # Clear the buffer
      self._data_buffer = b''

  def end_chunked(self) -> None:
    """End the chunked transfer."""
    if not self._blob_client:
      raise RuntimeError("start_chunked() must be called before end_chunked()")

    # Upload any remaining data in the buffer
    self.write_chunk(b'', force=True)

    # For append blobs, no additional commit operation is needed
    # The data is already committed with each append_block call
    # Reset state
    self.reset()

  def delete(self, path: str) -> None:
    """Delete the file from cloud storage."""
    full_path = self._get_full_path(path)

    blob_client = self._blob_service_client.get_blob_client(
        container=self._container_name,
        blob=full_path
    )

    try:
      blob_client.delete_blob()
    except ResourceNotFoundError:
      # Blob doesn't exist, which is fine for delete operation
      pass

  def reset(self) -> None:
    """Reset any chunked output state."""
    self._blob_client = None
    self._data_buffer = b''

  def _get_full_path(self, path: str) -> str:
    """Construct the full blob path by combining base path and relative path."""
    # Remove leading slashes to avoid empty path segments
    clean_path = path.lstrip('/')

    if self._base_path:
      # Ensure proper path separation
      base = self._base_path.rstrip('/')
      return f"{base}/{clean_path}" if clean_path else base
    else:
      return clean_path
