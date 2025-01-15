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

"""Upload to cloud storage providers."""

from streamer.cloud.base import CloudUploaderBase


# Supported protocols.  Built based on which optional modules are available for
# cloud storage providers.
SUPPORTED_PROTOCOLS: list[str] = []


# All supported protocols.  Used to provide more useful error messages.
ALL_SUPPORTED_PROTOCOLS: list[str] = ['gs', 's3']


# Try to load the GCS (Google Cloud Storage) uploader.  If we can, the user has
# the libraries needed for GCS support.
try:
  from streamer.cloud.gcs import GCSUploader
  SUPPORTED_PROTOCOLS.append('gs')
except:
  pass


# Try to load the S3 (Amazon Cloud Storage) uploader.  If we can, the user has
# the libraries needed for S3 support.
try:
  from streamer.cloud.s3 import S3Uploader
  SUPPORTED_PROTOCOLS.append('s3')
except:
  pass


def create(upload_location: str) -> CloudUploaderBase:
  """Create an uploader appropriate to the upload location URL."""

  if upload_location.startswith("gs://"):
    return GCSUploader(upload_location)
  elif upload_location.startswith("s3://"):
    return S3Uploader(upload_location)
  else:
    raise RuntimeError("Protocol of {} isn't supported".format(upload_location))
