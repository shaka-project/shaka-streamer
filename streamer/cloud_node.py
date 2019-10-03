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

from google.cloud import storage

import os
import time

from . import node_base

# This is the value for the HTTP header "Cache-Control" which will be attached
# to the Cloud Storage blobs uploaded by this tool.  When the browser requests
# a file from Cloud Storage, the server will use this as the value of the
# "Cache-Control" header it returns.
# Here "no-store" means that the response must not be stored in a cache, and
# "no-transform" means that the response must not be manipulated in any way
# (including Chrome's data saver features which might want to re-encode
# content).
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
CACHE_CONTROL_HEADER = 'no-store, no-transform'

class CloudNode(node_base.ThreadedNodeBase):
  def __init__(self, input_dir, bucket_url, temp_dir):
    super().__init__(thread_name='cloud', continue_on_exception=True)
    self._input_dir = input_dir
    self._temp_dir = temp_dir
    self._storage_client = storage.Client()
    self._bucket_url = bucket_url
    bucket, path = self._bucket_url.replace('gs://', '').split('/', 1)
    self._bucket = self._storage_client.get_bucket(bucket)
    # Strip trailing slashes to make sure we don't construct paths later like
    # foo//bar, which is _not_ the same as foo/bar in Google Cloud Storage.
    self._subdir_path = path.rstrip('/')

  def _thread_single_pass(self):
    all_files = os.listdir(self._input_dir)
    is_manifest_file = lambda x: x.endswith('.mpd') or x.endswith('.m3u8')
    manifest_files = filter(is_manifest_file, all_files)
    segment_files = filter(lambda x: not is_manifest_file(x), all_files)

    # The manifest at any moment will reference existing segment files.
    # We must be careful not to upload a manifest that references segments that
    # haven't been uploaded yet.  So first we will capture manifest contents,
    # then upload current segments, then upload the manifest contents we
    # captured.

    manifest_contents = {}
    for filename in manifest_files:
      source_path = os.path.join(self._input_dir, filename)
      contents = b''

      # Capture manifest contents, and retry until the file is non-empty or
      # until the thread is killed.
      while not contents and self._is_running():
        time.sleep(0.1)

        with open(source_path, 'rb') as f:
          contents = f.read()

      manifest_contents[filename] = contents

    for filename in segment_files:
      # Check if the thread has been interrupted.
      if not self._is_running():
        return

      source_path = os.path.join(self._input_dir, filename)
      destination_path = self._subdir_path + '/' + filename
      self._sync_file(source_path, destination_path)

    for filename, contents in manifest_contents.items():
      # Check if the thread has been interrupted.
      if not self._is_running():
        return

      destination_path = self._subdir_path + '/' + filename
      self._upload_string(contents, destination_path)

    # Finally, list blobs and delete any that don't exist locally.  This will
    # help avoid excessive storage costs from content that is outside the
    # availability window.  We use the prefix parameter to limit ourselves to
    # the folder this client is uploading to.
    all_blobs = self._storage_client.list_blobs(self._bucket,
                                                prefix=self._subdir_path + '/')
    for blob in all_blobs:
      # Check if the thread has been interrupted.
      if not self._is_running():
        return

      assert blob.name.startswith(self._subdir_path + '/')
      filename = blob.name.replace(self._subdir_path + '/', '')
      local_path = os.path.join(self._input_dir, filename)
      if not os.path.exists(local_path):
        blob.delete()

  def _sync_file(self, source_file, dest_blob_name):
    blob = self._bucket.blob(dest_blob_name)
    blob.cache_control = CACHE_CONTROL_HEADER

    try:
      if blob.exists(self._storage_client):
        blob.reload(self._storage_client)
        modified_datetime = os.path.getmtime(source_file)
        if modified_datetime <= blob.updated.timestamp():
          # We already have an up-to-date copy in cloud storage.
          return

      blob.upload_from_filename(source_file)

    except FileNotFoundError:
      # The file was deleted by the Packager between the time we saw it and now.
      # Ignore this one.
      return

  def _upload_string(self, source_string, dest_blob_name):
    blob = self._bucket.blob(dest_blob_name)
    blob.cache_control = CACHE_CONTROL_HEADER
    blob.upload_from_string(source_string)

  def _is_running(self):
    return self.check_status() == node_base.ProcessStatus.Running
