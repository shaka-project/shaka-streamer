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

"""Utility functions used by multiple modules."""

import urllib.parse

def is_url(output_location: str) -> bool:
  """Returns True if the output location is a URL."""
  return urllib.parse.urlparse(output_location).scheme != ''

def is_http_url(output_location: str) -> bool:
  """Returns True if the output location is an HTTP/HTTPS URL."""
  scheme = urllib.parse.urlparse(output_location).scheme
  return scheme in ['http', 'https']
