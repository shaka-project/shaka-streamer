# Copyright 2019 Google LLC
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

"""Pushes output from packager to cloud."""

import glob
import os
import subprocess
import time

from . import node_base

# This is the HTTP header "Cache-Control" which will be attached to the Cloud
# Storage blobs uploaded by this tool.  When the browser requests a file from
# Cloud Storage, the server will use this as the "Cache-Control" header it
# returns.
#
# Here "no-store" means that the response must not be stored in a cache, and
# "no-transform" means that the response must not be manipulated in any way
# (including Chrome's data saver features which might want to re-encode
# content).
#
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
CACHE_CONTROL_HEADER = 'Cache-Control: no-store, no-transform'

COMMON_GSUTIL_ARGS = [
    'gsutil',
    '-q', # quiet mode: report errors, but not progress
    '-h', CACHE_CONTROL_HEADER, # set the appropriate cache header on uploads
    '-m', # parllelize the operation
    'rsync', # operation to perform
    '-C', # still try to push other files if one fails
    '-r', # recurse into folders
]

class CloudNode(node_base.ThreadedNodeBase):
  def __init__(self, input_dir, bucket_url, temp_dir):
    super().__init__(thread_name='cloud', continue_on_exception=True)
    self._input_dir = input_dir
    self._bucket_url = bucket_url
    self._temp_dir = temp_dir

  def _thread_single_pass(self):
    # With recursive=True, glob's ** will also match the base dir.
    manifest_files = (
        glob.glob(self._input_dir + '/**/*.mpd', recursive=True) +
        glob.glob(self._input_dir + '/**/*.m3u8', recursive=True))

    # The manifest at any moment will reference existing segment files.
    # We must be careful not to upload a manifest that references segments that
    # haven't been uploaded yet.  So first we will capture manifest contents,
    # then upload current segments, then upload the manifest contents we
    # captured.

    for manifest_path in manifest_files:
      # The path within the input dir.
      subdir_path = os.path.relpath(manifest_path, self._input_dir)

      # Capture manifest contents, and retry until the file is non-empty or
      # until the thread is killed.
      contents = b''
      while (not contents and
             self.check_status() == node_base.ProcessStatus.Running):
        time.sleep(0.1)

        with open(manifest_path, 'rb') as f:
          contents = f.read()

      # Now that we have manifest contents, put them into a temp file so that
      # the manifests can be pushed en masse later.
      temp_file_path = os.path.join(self._temp_dir, subdir_path)
      # Create any necessary intermediate folders.
      temp_file_dir_path = os.path.dirname(temp_file_path)
      os.makedirs(temp_file_dir_path, exist_ok=True)
      # Write the temp file.
      with open(temp_file_path, 'wb') as f:
        f.write(contents)

    # Sync all files except manifest files.
    args = COMMON_GSUTIL_ARGS + [
        '-d', # delete remote files that are no longer needed
        '-x', '.*m3u8', # skip m3u8 files, which we'll push separately later
        '-x', '.*mpd', # skip mpd files, which we'll push separately later
        self._input_dir, # local input folder to sync
        self._bucket_url, # destination in cloud storage
    ]
    # NOTE: The -d option above will not result in the files ignored by -x
    # being deleted from the remote storage location.
    subprocess.check_call(args)

    # Sync the temporary copies of the manifest files.
    args = COMMON_GSUTIL_ARGS + [
        '-J', # compress all files in transit, since they are text
        self._temp_dir, # local input folder to sync
        self._bucket_url, # destination in cloud storage
    ]
    subprocess.check_call(args)
