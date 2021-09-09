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
from streamer.packager_node import PackagerNode
import subprocess
import time

from streamer.node_base import ProcessStatus, ThreadedNodeBase
from typing import Optional, List

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

class CloudAccessError(Exception):
  """Raised when the cloud URL cannot be written to by the user."""
  pass

class CloudNode(ThreadedNodeBase):
  def __init__(self,
               input_dir: str,
               bucket_url: str,
               temp_dir: str,
               packager_nodes: List[PackagerNode],
               is_vod: bool):
    super().__init__(thread_name='cloud', continue_on_exception=True, sleep_time=1)
    self._input_dir: str = input_dir
    self._bucket_url: str = bucket_url
    self._temp_dir: str = temp_dir
    self._packager_nodes: List[PackagerNode] = packager_nodes
    self._is_vod: bool = is_vod

  @staticmethod
  def check_access(bucket_url: str) -> None:
    """Called early to test that the user can write to the destination bucket.

    Writes an empty file called ".shaka-streamer-access-check" to the
    destination.  Raises CloudAccessError if the destination cannot be written
    to.
    """

    # Note that we make sure there are not two slashes in a row here, which
    # would create a subdirectory whose name is "".
    destination = bucket_url.rstrip('/') + '/.shaka-streamer-access-check'
    # Note that this can't be "gsutil ls" on the destination, because the user
    # might have read-only access.  In fact, some buckets grant read-only
    # access to anonymous (non-logged-in) users.  So writing to the bucket is
    # the only way to check.
    args = ['gsutil', 'cp', '-', destination]
    status = subprocess.run(args,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    # If the command failed, raise an error.
    if status.returncode != 0:
      message = """Unable to write to cloud storage URL: {}

Please double-check that the URL is correct, that you are signed into the
Google Cloud SDK or Amazon AWS CLI, and that you have access to the
destination bucket.

Additional output from gsutil:
  {}""".format(bucket_url, status.stderr)
      raise CloudAccessError(message)

  def _thread_single_pass(self) -> None:
    
    # Sync the files with the cloud storage.
    self._upload()
    
    for packager_node in self._packager_nodes:
      status = packager_node.check_status()
      if status == ProcessStatus.Running:
        return
    
    # Do one last sync to be sure that the latest versions of the files are uploaded.
    self._upload()
    self._status = ProcessStatus.Finished
    
  def _upload(self) -> None:
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
      with open(manifest_path, 'rb') as f:
        contents = f.read()

      while (not contents and
             self.check_status() == ProcessStatus.Running):
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

    compression_args = []
    if self._bucket_url.startswith('gs:'):
      # This arg seems to fail on S3, but still works for GCS.
      compression_args = [
          '-J', # compress all files in transit, since they are text
      ]

    # Sync the temporary copies of the manifest files.
    args = COMMON_GSUTIL_ARGS + compression_args + [
        self._temp_dir, # local input folder to sync
        self._bucket_url, # destination in cloud storage
    ]
    subprocess.check_call(args)

  def stop(self,
           status: Optional[ProcessStatus]) -> None:
    super().stop(status)

    # A fix for issue #30:
    if self._is_vod:
      # After processing the stop, run _one more_ pass.  This is how we ensure
      # that the final version of a VOD asset gets uploaded to cloud storage.
      # Otherwise, we might not have the final manifest or every single segment
      # uploaded.
      self._thread_single_pass()

