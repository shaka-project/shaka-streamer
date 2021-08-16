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

"""A python script to automate the Shaka-Streamer-Binaries building
and packaging process for different platforms."""

import setuptools
from setuptools.command.build_py import build_py
import sys
import shutil
import os
import yaml

# os.chmod() is called for every binary at import time,
# before we put them in wheels.
import streamer_binaries


class custom_build_py(build_py):
  """A custom class to override the default behavior of `build_py` command."""

  def run(self):
    # Clean the build directory so the binaries that were added at the previous
    # build don't remain in the package for the current platform we build for.
    # This is because setuptools doesn't delete it after a build has
    # completed and doesn't also re-create it in the next `build` call,
    # that's why we can't delete it either, so let's just clean it.
    build_dir = os.path.join(self.build_lib, streamer_binaries.__name__)
    self._clean_build_dir(build_dir)
    return super().run()

  def _clean_build_dir(self, build_dir):
    try:
      # To clean the directory, we can remove it and re-create it.
      shutil.rmtree(build_dir)
      os.mkdir(build_dir)
    except FileNotFoundError:
      # At the first run, the directory might not be on the system yet.
      return


def build_wheel(platform_name, platform_binaries):
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

  # This setup() call will ingest the sys.argv command line arguments.
  setuptools.setup(
    name='shaka-streamer-binaries',
    version=streamer_binaries.__version__,
    author='Google',
    description='A package containing FFmpeg, FFprobe, and Shaka Packager static builds.',
    long_description=('An auxiliary package that provides platform-specific'
                      ' binaries used by Shaka Streamer.'),
    url='https://github.com/google/shaka-streamer/tree/master/binaries',
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
    # Use our custom builder.  All it does is cleaning the build directory
    # before using it for building, as it might contain old unwanted binaries.
    cmdclass={'build_py': custom_build_py},
  )


def main():
  try:
    # A path to a yaml file should be provided as the first argument.
    yaml_file = sys.argv[1]
  except IndexError:
    raise RuntimeError(
        'The first and only argument should be a yaml file name.\n'
        'Usage: python build.py filename.yaml') from None

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
  # that contains the executables specific to this platform.
  for platform_name, platform_binaries in platform_data_dict.items():
    # We will build the package multiple times, each time with different
    # command line arguments for a different platform.
    build_wheel(platform_name, platform_binaries)


main()
