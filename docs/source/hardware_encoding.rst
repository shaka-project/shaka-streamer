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

Setup on Linux (Intel)
----------------------

By default, hardware encoding on Linux uses FFmpeg’s VAAPI support, which
supports Intel devices.

To use VAAPI, you must also install the appropriate VAAPI driver for your
device.  For example, on Ubuntu, you can install all available VAAPI drivers
with:

.. code:: sh

   sudo apt -y install va-driver-all

VAAPI support is enabled by default in Debian & Ubuntu packages for FFmpeg.

Setup on Linux (Nvidia)
-----------------------

You may also use FFmpeg's NVENC support on Linux, which supports Nvidia devices.

For this, set ``hwaccel_api`` in the pipeline config to ``'nvenc'``.

The underlying driver and special FFmpeg headers can be installed with:

.. code:: sh

  sudo apt -y install libnvidia-encode1
  git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git
  (cd nv-codec-headers && make & sudo make install)

NVENC support is **not** enabled by default in Debian & Ubuntu packages for
FFmpeg.  To use it, you may need to build FFmpeg from source and pass
``--enable-nvenc`` to configure.  See instructions in :doc:`prerequisites` for
details on building FFmpeg from source.

Setup on macOS
--------------

Hardware encoding on macOS uses Apple's VideoToolbox API.  No setup is required.

Setup on Windows
----------------

Hardware encoding for Windows is not yet supported, but we are accepting PRs if
you’d like to contribute additional platform support.  This doc may be a useful
reference for hardware-related options in FFmpeg:
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

Note that not all codecs are supported by all devices or APIs.  For a list of
supported hardware codecs, see: https://trac.ffmpeg.org/wiki/HWAccelIntro
