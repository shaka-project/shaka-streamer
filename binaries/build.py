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

"""A python script to automate the Shaka-Streamer-Binaries building
and packaging process for different platforms."""

import setuptools
import sys
import shutil
import os
import yaml

import streamer_binaries


def clean_dir(dir):
  # To clean the directory, we can remove it and re-create it.
  shutil.rmtree(dir)
  os.mkdir(dir)

def build_wheel(platform_name, platform_binaries):
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
  # This setup() call will ingest the sys.argv command line arguments.
  setuptools.setup(
    name='shaka-streamer-binaries',
    version=streamer_binaries.__version__,
    author='Google',
    description='A package containing FFmpeg, FFprobe, and Shaka Packager static builds.',
    long_description=('An auxiliary package that provides platform-specific'
                      ' binaries used by Shaka Streamer.'),
    url='https://github.com/google/shaka-streamer',
    packages=['streamer_binaries'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
    ],
    package_data={
        # Only add the corresponding platform specific binaries
        # to the package for the current platform_name.
        'streamer_binaries': platform_binaries,
    },
  )

def main():
  try:
    # A path to a yaml file should be provided as the first argument.
    yaml_file = sys.argv[1]
  except IndexError:
    print(
      'Error: The first and only argument should be a yaml file name.\n'
      'Usage: python build.py filename.yaml')
    exit(1)

  with open(yaml_file) as platform_data_file:
    platform_data_dict = yaml.safe_load(platform_data_file)

  # Assert for the expected input structure.
  assert isinstance(platform_data_dict, dict), 'The yaml file did not resolve to a dictionary.'
  for key, value in platform_data_dict.items():
    assert isinstance(key, str), 'The dictionary keys should be strings.'
    assert isinstance(value, list), 'The dictionary values should be lists of file names.'
    for item in value:
      assert isinstance(item, str), 'A file name should be a string.'

  # For each platform(OS+CPU), create a binary wheel distribution
  # that contains the executables specific for this platform.
  for platform_name, platform_binaries in platform_data_dict.items():
    # We will build the package multiple times, each time with differnt
    # command line arguments for a differnt platform.
    build_wheel(platform_name, platform_binaries)
    # Clean the build directory so the binaries that were just added
    # doesn't remain in the package for the next platform to build for.
    # This is because setuptools doesn't delete it after a build has
    # completed and doesn't also re-create it in the next `build` call,
    # that's why we can't delete it either, so let's just clean it.
    clean_dir('build/lib/streamer_binaries')

  clean_dir('build')
  os.rmdir('build')

main()
