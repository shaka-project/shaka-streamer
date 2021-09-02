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
import sys
import urllib.request
import setuptools # type: ignore
import setuptools.command.build_py #type: ignore
import streamer_binaries


# Version constants.
# Change to download different versions.
FFMPEG_VERSION = 'n4.4-1'
PACKAGER_VERSION = 'v2.99.5'

# A map of postfixes that will be combined with the binary download links
# to achieve a full download link.  Different postfix for each platform.
# Extend this dictionary to add more platforms.
PLATFORM_POSTFIXES = {
    # 64-bit Windows
    'win_amd64': '-win-x64.exe',
    # 64-bit Linux
    'manylinux1_x86_64': '-linux-x64',
    # Linux on ARM
    'manylinux2014_aarch64': '-linux-arm64',
    # 64-bit with 10.9 SDK
    'macosx_10_9_x86_64': '-osx-x64',
  }

FFMPEG_DL_PREFIX = 'https://github.com/joeyparrish/static-ffmpeg-binaries/releases/download/' + FFMPEG_VERSION
PACKAGER_DL_PREFIX = 'https://github.com/joeyparrish/shaka-packager/releases/download/' + PACKAGER_VERSION

# The download links to each binary.  These download links
# aren't complete, they miss the platfrom-specific postfix.
BINARIES_DL = [
    FFMPEG_DL_PREFIX + '/ffmpeg',
    FFMPEG_DL_PREFIX + '/ffprobe',
    PACKAGER_DL_PREFIX + '/packager',
  ]


class custom_build_py(setuptools.command.build_py.build_py):
  """A custom class to override the default behavior of `build_py` command."""

  platform_build_lib = ''

  def initialize_options(self):
    return_val = super().initialize_options()
    # Sets the `--build-lib` directory.
    self.build_lib = custom_build_py.platform_build_lib
    return return_val


def build_bdist_wheel(platform_name, platform_binaries):
  """Builds a wheel distribution for `platform_name` adding the files
  in `platform_binaries` to it using the `package_data` parameter."""

  sys.argv = [
      'setup.py',
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

  # Build this package in `--bdist-dir` directly.
  custom_build_py.platform_build_lib = platform_name

  # This setup() call will ingest the sys.argv command line arguments.
  setuptools.setup(
    name='shaka-streamer-binaries',
    version=streamer_binaries.__version__,
    author='Google',
    description='A package containing FFmpeg, FFprobe, and Shaka Packager static builds.',
    long_description=('An auxiliary package that provides platform-specific'
                      ' binaries used by Shaka Streamer.'),
    url='https://github.com/google/shaka-streamer/tree/master/binaries',
    packages=[streamer_binaries.__name__,],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
    ],
    package_data={
        # Only add the corresponding platform specific binaries
        # to the package for the current `platform_name`.
        streamer_binaries.__name__: platform_binaries,
    },
    # Use our custom builder.  All it does is that it sets the `--build-lib`
    # argument that we can't set from the `bdist_wheel` command interface.
    cmdclass={'build_py': custom_build_py},
  )


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
  default_permissions = 0o755
  os.chmod(binary_path, default_permissions)
  return binary_name


def main():
  # For each platform(OS+CPU), we download the its binaries and
  # create a binary wheel distribution that contains the executable
  # binaries specific to this platform.
  for platform_name, postfix in PLATFORM_POSTFIXES.items():
    binaries_to_include = []
    # Use the `postfix` specific to this platfrom to achieve
    # the full download link for each binary.
    for binary_dl in BINARIES_DL:
      download_link = binary_dl + postfix
      binary_name = download_binary(download_url=download_link,
                                    download_dir=streamer_binaries.__name__)
      binaries_to_include.append(binary_name)
    # Build a wheel distribution with for this platform
    # and include the binaries we have just downloaded.
    build_bdist_wheel(platform_name, binaries_to_include)


if  __name__ == '__main__':
  main()