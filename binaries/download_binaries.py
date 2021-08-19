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

"""A script that downloads the static builds for all the platforms we build
for and output a yaml file for platform<->binaries mapping.
"""

import time
import os
import yaml
from typing import List
from threading import Thread

import streamer_binaries
import requests


YAML_OUTPUT_FILE = 'package_data.yaml'


def download_github_release_binaries(
    output_dir: str,
    github_api_end_points: List[str],
    only_download_files_starting_with: List[str] = ['']):
  """Downloads the latest releases for a github repo.
  `output_dir` is the directory that files will be downloaded in.
  This function is blocking, it will wait until all the assets are downloaded.
  
  `github_api_end_point` should be a releases end point for a github repo.

  Check the Releases API at https://docs.github.com/en/rest/reference/repos#releases

  `only_download_files_starting_with` is an optional argument, if passed, the function
  will try to only download files starting with one of this list elements.
  """

  def download_binary(download_url: str, downloaded_files: List[str]):
    """Downloads a file and write it to the file system."""

    file_name = download_url.split('/')[-1]
    # Don't try to download files other than the ones starting with
    # one of the strings in `only_download_files_starting_with`.
    if not file_name.startswith(tuple(only_download_files_starting_with)):
      return
    file_path = os.path.join(output_dir, file_name)
    # Download with `stream=True` so not to use so much memory.
    with requests.get(url=download_url, stream=True) as res:
      # Was the connection successful?
      try:
        res.raise_for_status()
      except Exception as ex:
        RuntimeError('\'{}\' couldn\'t be downloaded\nException: {}\n'.format(
            download_url, ex))
      print('downloading', file_name)
      with open(file_path, 'wb') as binary:
        for content in res.iter_content(chunk_size=65536):
          binary.write(content)
      print(file_name, 'is downloaded.')
    # Set executable permissions for the downloaded binaries.
    default_permissions = 0o755
    os.chmod(file_path, default_permissions)
    # Add the this file we just downloaded to the downloaded files.
    downloaded_files.append(file_name)

  assets: List[dict] = []
  for end_point in github_api_end_points:
    res = requests.get(end_point,
                       # This header is recommended by github docs.
                       headers={'Accept': 'application/vnd.github.v3+json'})
    res.raise_for_status()
    res_in_json = res.json()
    # `res_in_json[0]` will grab the latest release.
    assets.extend(res_in_json[0]['assets'])

  download_threads: List[Thread] = []
  downloaded_files: List[str] = []

  # Loop over all the assets and download them.
  for asset in assets:
    download_url: str = asset['browser_download_url']
    download_threads.append(Thread(target=download_binary,
                                   args=(download_url, downloaded_files)))
    # Start downloading the asset.
    download_threads[-1].start()

  # Wait until all the binaries are downloaded.
  while(any(download_thread.is_alive() for
            download_thread in download_threads)):
    time.sleep(1)

  return downloaded_files


def select_binaries(binaries_names: List[str],
                    name_contains: List[str]) -> List[str]:
  """A non-reliable method to automate selecting which binaries goes
  for which platform."""

  # The subset of the binaries we will select.
  selected_binaries: List[str] = []
  for binary_name in binaries_names:
    # If we have every substring the `binary_name` so we can select it safely.
    if all(substring.lower() in binary_name.lower() for
           substring in name_contains):
      selected_binaries.append(binary_name)
  return selected_binaries


def main():
  # https://api.github.com/repos/{owner}/{repo}/releases
  releases_urls = ['https://api.github.com/repos/joeyparrish/static-ffmpeg-binaries/releases',
                   'https://api.github.com/repos/google/shaka-packager/releases']

  # Download file whose names starting with one of these strings.
  starts_with = ['ffmpeg', 'ffprobe', 'packager']
  binaries_names = download_github_release_binaries(streamer_binaries.__name__,
                                                    releases_urls,
                                                    starts_with)

  # Sort the binaries based on platform.
  package_data = {
      # 64-bit Windows
      'win_amd64': select_binaries(binaries_names,
                                   name_contains=['win',]),
      # 64-bit Linux
      'manylinux1_x86_64': select_binaries(binaries_names,
                                           name_contains=['linux', 'x64',]),
      # Linux on ARM
      'manylinux2014_aarch64': select_binaries(binaries_names,
                                               name_contains=['linux', 'arm64',]),
      # 64-bit with 10.9 SDK
      'macosx_10_9_x86_64': select_binaries(binaries_names,
                                            name_contains=['osx',]),
  }

  # Dump `package_data` into a yaml file.
  yaml.dump(package_data, open(YAML_OUTPUT_FILE, 'w'))


main()
