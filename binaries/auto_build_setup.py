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

# NOTE: This file is intended to be used only by the build script
# and not to be run from the terminal.
import sys
import ast
import setuptools # type: ignore

import streamer_binaries

# The last argument passed MUST be a list of binary file names
# that we wish include in the build.
# Parse this argument into a list.
# This argument will look something like this:
# 	['binary_1', 'binary_2', 'binary_3', 'binary_4']
platform_binaries = ast.literal_eval(sys.argv[-1])
assert isinstance(platform_binaries, list)

# The rest are the command line arguments given to setup() function.
sys.argv = sys.argv[:-1]

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
      # Only add the corresponding platform specific binaries to the wheel.
      streamer_binaries.__name__: platform_binaries,
  }
)