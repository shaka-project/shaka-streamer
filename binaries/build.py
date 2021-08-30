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

import setuptools # type: ignore
from setuptools.command.build_py import build_py # type: ignore
import sys
import yaml

# os.chmod() is called for every binary at import time,
# before we put them in wheels.
import streamer_binaries


class custom_build_py(build_py):
  """A custom class to override the default behavior of `build_py` command."""

  platform_build_lib = ''

  def run(self):

    self.build_lib = custom_build_py.platform_build_lib
    return super().run()

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
        # to the package for the current platform_name.
        streamer_binaries.__name__: platform_binaries,
    },
    # Use our custom builder.  All it does is that it sets the `--build-lib`
    # argument that we can't set from the `bdist_wheel` command interface.
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
