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


import sys
import setuptools # type: ignore

import streamer_binaries

separator_index = sys.argv.index('--')
platform_binaries = sys.argv[separator_index + 1:]
sys.argv = sys.argv[:separator_index]

setuptools.setup(
  name='shaka-streamer-binaries',
  version=streamer_binaries.__version__,
  author='Google',
  description='A package containing FFmpeg, FFprobe, and Shaka Packager static builds.',
  long_description=('An auxiliary package that provides platform-specific'
                    ' binaries used by Shaka Streamer.'),
  url='https://github.com/shaka-project/shaka-streamer/tree/main/binaries',
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
