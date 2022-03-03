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

Overview
========

Why Shaka Streamer?
-------------------

Shaka Streamer is packaging and streaming made easy.

* Simple, config-file-based application

  * No complicated command-lines
  * Sane defaults
  * Reusable configs

* Runs on Linux, macOS, and Windows
* Supports almost any input FFmpeg can ingest
* Can push output automatically to Google Cloud Storage or Amazon S3
* FFmpeg and Shaka Packager binaries provided

See also the more detailed list of :ref:`Features` below.


Getting started
---------------

Shaka Streamer requires `Python 3.6+`_.  Release versions of Shaka Streamer can
be installed or upgraded through ``pip3`` with:

.. code:: sh

  # To install/upgrade globally (drop the "sudo" for Windows):
  sudo pip3 install --upgrade shaka-streamer shaka-streamer-binaries

  # To install/upgrade per-user:
  pip3 install --user --upgrade shaka-streamer shaka-streamer-binaries


The ``shaka-streamer-binaries`` package contains `Shaka Packager`_ and `FFmpeg`_
binaries, for your convenience.  You may also choose to install these
dependencies separately and use ``shaka-streamer --use-system-binaries`` instead
of the binary package.

To use Shaka Streamer, you need two YAML config files: one to describe the
input, and one to describe the encoding pipeline. Sample configs can be found
in the `config_files/`_ folder. Sample inputs referenced there can be
downloaded individually over HTTPS or all at once through gsutil:

.. code:: sh

   gsutil -m cp gs://shaka-streamer-assets/sample-inputs/* .

Example command-line for live streaming to Google Cloud Storage:
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: sh

   python3 shaka-streamer \
     -i config_files/input_looped_file_config.yaml \
     -p config_files/pipeline_live_config.yaml \
     -c gs://my_gcs_bucket/folder/

Example command-line for live streaming to Amazon S3:
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: sh

   python3 shaka-streamer \
     -i config_files/input_looped_file_config.yaml \
     -p config_files/pipeline_live_config.yaml \
     -c s3://my_s3_bucket/folder/


Features
--------

* Supports:

  * VOD or live content
  * DASH and HLS output (or both at once)
  * VOD multi-period DASH (and equivalent HLS output)
  * Clear or encrypted output
  * Hardware encoding (if available from the platform)

* Lots of options for input

  * Transcode and package static input for VOD
  * Loop a file for simulated live streaming
  * Grab video from a webcam
  * Generate input from an arbitrary external command

* Gives you control over details if you want it

  * Control DASH live stream attributes
  * Control output folders and file names
  * Add arbitrary FFmpeg filters for input or output


Known issues
~~~~~~~~~~~~
We do support subtitles/captions (``media_type`` set to ``text``) for VOD
content.  But please note that at this time, we have no way to pipeline text
for live streams, loop a single text input with ``input_type`` of
``looped_file``, transform text streams from one format to another, or cut a
snippet of text using the ``start_time`` and ``end_time`` fields of the input
config.

Multiple VAAPI devices are not yet supported on Linux.  See `issue #17`_.


Development
-----------
If you wish to make changes to Shaka Streamer, you will also need to install the
`Python "yaml" module`_.

See :doc:`prerequisites` for detailed instructions on installing prerequisites
and optional dependencies.


Running tests
~~~~~~~~~~~~~

We have end-to-end tests that will start streams and check them from a headless
browser using Shaka Player. End-to-end tests can be run like so:

.. code:: sh

   python3 run_end_to_end_tests.py


Technical details
~~~~~~~~~~~~~~~~~

Shaka Streamer connects FFmpeg and Shaka Packager in a pipeline, such that
output from FFmpeg is piped directly into the packager, and packaging and
transcoding of all resolutions, bitrates, and languages occur in parallel.

The overall pipeline is composed of several nodes. At a minimum, these are
``TranscoderNode`` (which runs FFmpeg) and ``PackagerNode`` (which runs Shaka
Packager). They communicate via named pipes on Linux and macOS.

All input types are read directly by ``TranscoderNode``. If the input type is
``looped_file``, then ``TranscoderNode`` will add additional FFmpeg options to
loop that input file indefinitely.

If the ``-c`` option is given with a Google Cloud Storage URL, then an
additional node called ``CloudNode`` is added after ``PackagerNode``. It runs a
thread which watches the output of the packager and pushes updated files to the
cloud.

The pipeline and the nodes in it are constructed by ``ControllerNode`` based on
your config files. If you want to write your own front-end or interface
directly to the pipeline, you can create a ``ControllerNode`` and call the
``start()``, ``stop()``, and ``is_running()`` methods on it. You can use
the ``shaka-streamer`` script as an example of how to do this.  See also
:doc:`module_api`.


.. _config_files/: https://github.com/shaka-project/shaka-streamer/tree/main/config_files
.. _issue #8: https://github.com/shaka-project/shaka-streamer/issues/8
.. _issue #17: https://github.com/shaka-project/shaka-streamer/issues/17
.. _issue #23: https://github.com/shaka-project/shaka-streamer/issues/23
.. _Python 3.6+: https://www.python.org/downloads/
.. _Python "yaml" module: https://pyyaml.org/
.. _Shaka Packager: https://github.com/shaka-project/shaka-packager
.. _FFmpeg: https://ffmpeg.org/
