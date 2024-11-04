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

Installing Prerequisites
========================

TL;DR
-----

If you installed Shaka Streamer via pip, you already have the necessary Python
dependencies.  If you don't want to use your own FFmpeg and Shaka Packager,
install our prebuilt binaries with:

.. code:: sh

  pip3 install shaka-streamer-binaries

The rest of this document only matters for development setup if you plan to
make changes to Shaka Streamer.


Required runtime modules
------------------------

To install required modules via Ubuntu or Debian packages:

.. code:: sh

  sudo apt -y install python3-yaml python3-distro


For any platform, you can install them via pip:

.. code:: sh

  pip3 install -r requirements.txt


Development modules
-------------------

To install development modules via Ubuntu or Debian packages:

.. code:: sh

  sudo apt -y install \
      python3-flask python3-mypy python3-setuptools \
      python3-sphinx python3-wheel


For any platform, you can install them via pip:

.. code:: sh

  pip3 install -r optional_requirements.txt



Shaka Streamer Binaries package (recommended)
---------------------------------------------

Shaka Streamer requires `Shaka Packager`_ and `FFmpeg`_ as it uses them
internally.

These binaries can be installed for your platform easily with the
``shaka-streamer-binaries`` package:

.. code:: sh

  pip3 install shaka-streamer-binaries

The static FFmpeg builds are pulled from here:
https://github.com/shaka-project/static-ffmpeg-binaries

The static Shaka Packager builds are pulled from here:
https://github.com/shaka-project/shaka-packager

FFmpeg builds for Ubuntu require you to install vaapi packages:

.. code:: sh

  sudo apt -y install libva2 libva-drm2


Shaka Packager (manual installation, not recommended)
-----------------------------------------------------

Pre-built Shaka Packager binaries can be downloaded from github here:
https://github.com/shaka-project/shaka-packager/releases

To install a Shaka Packager binary on Linux:

.. code:: sh

   sudo install -m 755 ~/Downloads/packager-linux \
     /usr/local/bin/packager

To build Shaka Packager from source, follow instructions here:
https://shaka-project.github.io/shaka-packager/html/build_instructions.html


FFmpeg (manual installation, not recommended)
---------------------------------------------

If your Linux distribution has FFmpeg v4.1+, you can just install the package.
For example, this will work in Ubuntu 19.04+:

.. code:: sh

   sudo apt -y install ffmpeg

For older versions of Ubuntu or any other Linux distro which does not have a
new enough version of FFmpeg, you can build it from source. For example:

.. code:: sh

   sudo apt -y install \
     libx264-dev libvpx-dev libopus-dev libfreetype6-dev \
     libfontconfig1-dev libsdl2-dev yasm \
     va-driver-all libnvidia-encode1

   git clone https://github.com/FFmpeg/FFmpeg ffmpeg
   cd ffmpeg
   git checkout n4.1.3
   ./configure \
     --enable-libx264 --enable-libvpx --enable-libopus \
     --enable-gpl --enable-libfreetype --enable-libfontconfig
   make
   sudo make install

For macOS, you can either build FFmpeg from source or you can use `Homebrew`_
to install it:

.. code:: sh

   brew install ffmpeg


Cloud Storage (optional)
------------------------

Shaka Streamer can push content directly to a Google Cloud Storage or Amazon S3
bucket. To use this feature, additional Python modules are required.


Google Cloud Storage
~~~~~~~~~~~~~~~~~~~~

First install the Python module if you haven't yet:

.. code:: sh

   python3 -m pip install google-cloud-storage

To use the default authentication, you will need default application
credentials installed.  On Linux, these live in
``~/.config/gcloud/application_default_credentials.json``.

The easiest way to install default credentials is through the Google Cloud SDK.
See https://cloud.google.com/sdk/docs/install-sdk to install the SDK.  Then run:

.. code:: sh

   gcloud init
   gcloud auth application-default login

Follow the instructions given to you by gcloud to initialize the environment
and login.


Amazon S3
~~~~~~~~~

First install the Python module if you haven't yet:

.. code:: sh

   python3 -m pip install boto3

To authenticate to Amazon S3, you can either add credentials to your `boto
config file`_ or login interactively using the `AWS CLI`_.

.. code:: sh

   aws configure


Test Dependencies (optional)
----------------------------

To run the end-to-end tests, you must also install nodejs and NPM.

To install these via Ubuntu or Debian packages:

.. code:: sh

  sudo apt -y install nodejs npm

To install Node.js and NPM on any other platform, you can try one of these:

* https://github.com/nodesource/distributions
* https://nodejs.org/en/download/

.. _Shaka Packager: https://github.com/shaka-project/shaka-packager
.. _FFmpeg: https://ffmpeg.org/
.. _Homebrew: https://brew.sh/
.. _boto config file: http://boto.cloudhackers.com/en/latest/boto_config_tut.html
.. _AWS CLI: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
