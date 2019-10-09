..
  Copyright 2019 Google LLC

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

Hardware Encoding
=================

Setup on Linux
--------------

Hardware encoding on Linux can be enabled through FFmpeg’s vaapi support.

To get started, install the appropriate vaapi package for your device.  For
example, for Intel’s Kaby Lake family of processors, which support hardware VP9
encoding, you would install this on Ubuntu:

.. code:: sh

   sudo apt install i965-va-driver

Or build and install from source here:
https://github.com/intel/intel-vaapi-driver

You will need to install the correct vaapi drivers for your device.  These are
only examples.

If hardware encoding still does not work, you may need to recompile FFmpeg from
source. See instructions in :doc:`prerequisites` for details.

Setup on Mac and Windows
------------------------

Hardware encoding for Mac and Windows is not yet supported, but we are
accepting PRs if you’d like to contribute additional platform support.  This
doc may be a useful reference for hardware-related options in FFmpeg:
https://trac.ffmpeg.org/wiki/HWAccelIntro

Configuration
-------------

To activate hardware encoding for any video codec, simply prefix the codec name
with ``hw:`` in the pipeline config file.

For example, see this snippet from
`config_files/pipeline_live_hardware_config.yaml`:

.. code:: yaml

   audio_codecs:
     - aac
     - opus
   video_codecs:
     - h264
     - hw:vp9
