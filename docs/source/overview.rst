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

Features
--------

* Simple, config-file-based application

  * No complicated command-lines
  * Sane defaults provided
  * You can re-use the same pipeline config across many inputs

* Supports VOD and live content
* Supports DASH and HLS output
* Supports clear and encrypted output
* Supports hardware encoding (if available from the platform)
* Supports almost any input FFmpeg can ingest
* Can push output automatically to Google Cloud Storage or Amazon S3
* Lots of options for input

  * Transcode and package static input for VOD
  * Loop a file for simulated live streaming
  * Grab video from a webcam
  * Generate input from an arbitrary external command

* Gives you control over details if you want it

  * Control DASH live stream attributes
  * Control output folders and file names
  * Add arbitrary FFmpeg filters for input or output


Caveat: text processing
~~~~~~~~~~~~~~~~~~~~~~~

We do support subtitles/captions (``media_type`` set to ``text``) for VOD
content.  But please note that at this time, we have no way to pipeline text
for live streams, loop a single text input with ``input_type`` of
``looped_file``, transform text streams from one format to another, or cut a
snippet of text using the ``start_time`` and ``end_time`` fields of the input
config.


Platform support
----------------

We support common Linux distributions and macOS.

Multiple VAAPI devices are not yet supported on Linux.  See `issue #17`_.

Windows is not supported at this time due to our use of ``os.mkfifo``, but we
are accepting PRs if you’d like to add Windows support. See `issue #8`_.


Getting started
---------------

Release versions of Shaka Streamer can be installed or upgraded through ``pip3``
with:

.. code:: sh

  # To install/upgrade globally (drop the "sudo" for Windows):
  sudo pip3 install --upgrade shaka-streamer

  # To install/upgrade per-user:
  pip3 install --user --upgrade shaka-streamer


Shaka Streamer requires at a minimum:

* `Python 3`_
* `Python “yaml” module`_
* `Shaka Packager`_
* `FFmpeg`_

See :doc:`prerequisites` for detailed instructions on installing prerequisites
and optional dependencies.

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

Running tests
-------------

We have end-to-end tests that will start streams and check them from a headless
browser using Shaka Player. End-to-end tests can be run like so:

.. code:: sh

   python3 run_end_to_end_tests.py

Technical details
-----------------

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

.. _config_files/: https://github.com/google/shaka-streamer/tree/master/config_files
.. _issue #8: https://github.com/google/shaka-streamer/issues/8
.. _issue #17: https://github.com/google/shaka-streamer/issues/17
.. _issue #23: https://github.com/google/shaka-streamer/issues/23
.. _Python 3: https://www.python.org/downloads/
.. _Python “yaml” module: https://pyyaml.org/
.. _Shaka Packager: https://github.com/google/shaka-packager
.. _FFmpeg: https://ffmpeg.org/
