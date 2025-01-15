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

"""Upload to cloud storage providers.

Base class definition."""

import abc


class CloudUploaderBase(object):
  @abc.abstractmethod
  def write_non_chunked(self, path: str, data: bytes) -> None:
    """Write the non-chunked data to the destination."""
    pass

  @abc.abstractmethod
  def start_chunked(self, path: str) -> None:
    """Set up for a chunked transfer to the destination."""
    pass

  @abc.abstractmethod
  def write_chunk(self, data: bytes) -> None:
    """Handle a single chunk of data."""
    pass

  @abc.abstractmethod
  def end_chunked(self) -> None:
    """End the chunked transfer."""
    pass

  @abc.abstractmethod
  def delete(self, path: str) -> None:
    """Delete the file from cloud storage."""
    pass

  @abc.abstractmethod
  def reset(self) -> None:
    """Reset any chunked output state."""
    pass
