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

import base64
import setuptools

import streamer

with open('README.md', 'r') as f:
  long_description = f.read()

setuptools.setup(
  name='shaka-streamer',
  version=streamer.__version__,
  author='Google',
  description='A simple config-file based approach to streaming media.',
  long_description=long_description,
  long_description_content_type='text/markdown',
  url='https://github.com/google/shaka-streamer',
  packages=setuptools.find_packages(),
  install_requires=[
      'PyYAML',
      'pywin32;platform_system=="Windows"',
  ],
  scripts=['shaka-streamer'],
  classifiers=[
      'Programming Language :: Python :: 3',
      'License :: OSI Approved :: Apache Software License',
      'Operating System :: POSIX :: Linux',
      'Operating System :: MacOS :: MacOS X',
      'Operating System :: Microsoft :: Windows',
  ],
  # Python 3.6 tested in GitHub Actions CI
  python_requires='>=3.6',
)
