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

"""A script that downloads ffmpeg, ffprobe, and packager static builds for all
the platforms we build for and then builds distribution wheels for them.
"""

import os
import shutil
import subprocess
import urllib.request

import streamer_binaries


# Version constants.
# Change to download different versions.
FFMPEG_VERSION = 'n7.1-1'
PACKAGER_VERSION = 'v3.3.0'

# A map of suffixes that will be combined with the binary download links
# to achieve a full download link.  Different suffix for each platform.
# Extend this dictionary to add more platforms.
PLATFORM_SUFFIXES = {
    # Linux x64
    'manylinux2014_x86_64': '-linux-x64',
    # Linux arm64
    'manylinux2014_aarch64': '-linux-arm64',
    # macOS x64 with 10.9 SDK
    'macosx_10_9_x86_64': '-osx-x64',
    # macOS arm64 with 11.0 SDK
    'macosx_11_0_arm64': '-osx-arm64',
    # Windows x64
    'win_amd64': '-win-x64.exe',
}

FFMPEG_DL_PREFIX = 'https://github.com/shaka-project/static-ffmpeg-binaries/releases/download/' + FFMPEG_VERSION
PACKAGER_DL_PREFIX = 'https://github.com/shaka-project/shaka-packager/releases/download/' + PACKAGER_VERSION

# The download links to each binary.  These download links aren't complete.
# They are missing the platfrom-specific suffix and optional distro-specific
# suffix (Linux only).
DISTRO_BINARIES_DL = [
    FFMPEG_DL_PREFIX + '/ffmpeg',
]
# These don't have distro-specific suffixes on Linux.
NON_DISTRO_BINARIES_DL = [
    FFMPEG_DL_PREFIX + '/ffprobe',
    PACKAGER_DL_PREFIX + '/packager',
]
# Important: wrap map() in list(), because map returns an iterator, and we need
# a real list.
UBUNTU_SUFFIXES = list(map(
    lambda version: '-ubuntu-{}'.format(version),
    streamer_binaries._ubuntu_versions_with_hw_encoders))

BINARIES_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))


def build_bdist_wheel(platform_name, platform_binaries):
  """Builds a wheel distribution for `platform_name` adding the files
  in `platform_binaries` to it using the `package_data` parameter."""

  args = [
      'python3', 'setup.py',
      # Build binary as a wheel.
      'bdist_wheel',
      # Platform name to embed in generated filenames.
      '--plat-name', platform_name,
      # Temporary directory for creating the distribution.
      '--bdist-dir', platform_name,
      # Python tag to embed in the generated filenames.
      '--python-tag', 'py3',
      # Run quietly.
      '--quiet',
  ]

  # After '--', we send the platform specific binaries that we want to include.
  args += ['--']
  args += platform_binaries

  subprocess.check_call(args, cwd=BINARIES_ROOT_DIR)

  # Remove the build directory so that it is not reused by 'setup.py'.
  shutil.rmtree(os.path.join(BINARIES_ROOT_DIR, 'build'))

def download_binary(download_url: str, download_dir: str) -> str:
  """Downloads a file and writes it to the file system.
  Returns the file name.
  """
  binary_name = download_url.split('/')[-1]
  binary_path = os.path.join(download_dir, binary_name)

  print('downloading', binary_name, flush=True, end=' ')
  urllib.request.urlretrieve(download_url, binary_path)
  print('(finished)')

  # Set executable permissions for the downloaded binaries.
  executable_permissions = 0o755
  os.chmod(binary_path, executable_permissions)

  return binary_name


def main():
  # For each platform(OS+CPU), we download the its binaries and create a binary
  # wheel distribution that contains the executable binaries specific to this
  # platform.
  download_dir = os.path.join(BINARIES_ROOT_DIR, streamer_binaries.__name__)

  for platform_name, suffix in PLATFORM_SUFFIXES.items():
    binaries_to_include = []

    # Use the suffix specific to this platfrom to construct the full download
    # link for each binary.
    for binary_dl in NON_DISTRO_BINARIES_DL:
      download_link = binary_dl + suffix
      binary_name = download_binary(download_url=download_link,
                                    download_dir=download_dir)
      binaries_to_include.append(binary_name)

    # FFmpeg binaries have extra variants for Ubuntu Linux to support hardware
    # encoding.
    for binary_dl in DISTRO_BINARIES_DL:
      download_link = binary_dl + suffix
      binary_name = download_binary(download_url=download_link,
                                    download_dir=download_dir)
      binaries_to_include.append(binary_name)

      if 'linux' in suffix:
        for ubuntu_suffix in UBUNTU_SUFFIXES:
          download_link = binary_dl + suffix + ubuntu_suffix
          binary_name = download_binary(download_url=download_link,
                                        download_dir=download_dir)
          binaries_to_include.append(binary_name)

    # Build a wheel distribution for this platform and include the binaries we
    # have just downloaded.
    build_bdist_wheel(platform_name, binaries_to_include)


if  __name__ == '__main__':
  main()
