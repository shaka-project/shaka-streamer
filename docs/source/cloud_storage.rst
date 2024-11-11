..
  Copyright 2024 Google LLC

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

Cloud Storage
=============
Shaka Streamer can output to an HTTP/HTTPS server or to cloud storage.

HTTP or HTTPS URLs will be passed directly to Shaka Packager, which will make
PUT requests to the HTTP/HTTPS server to write output files.  The URL you pass
will be a base for the URLs Packager writes to.  For example, if you pass
https://localhost:8080/foo/bar/, Packager would make a PUT request to
https://localhost:8080/foo/bar/dash.mpd to write the manifest (with default
settings).

Cloud storage URLs can be either Google Cloud Storage URLs (beginning with
gs://) or Amazon S3 URLs (beginning with s3://).  Like the HTTP support
described above, these are a base URL.  If you ask for output to gs://foo/bar/,
Streamer will write to gs://foo/bar/dash.mpd (with default settings).

Cloud storage output uses the storage provider's Python libraries.  Find more
details on setup and authentication below.


Google Cloud Storage Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~

Install the Python module if you haven't yet:

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

Example command-line for live streaming to Google Cloud Storage:

.. code:: sh

   python3 shaka-streamer \
     -i config_files/input_looped_file_config.yaml \
     -p config_files/pipeline_live_config.yaml \
     -o gs://my_gcs_bucket/folder/


Amazon S3 Setup
~~~~~~~~~~~~~~~

Install the Python module if you haven't yet:

.. code:: sh

   python3 -m pip install boto3

To authenticate to Amazon S3, you can either add credentials to your `boto
config file`_ or login interactively using the `AWS CLI`_.

.. code:: sh

   aws configure

Example command-line for live streaming to Amazon S3:

.. code:: sh

   python3 shaka-streamer \
     -i config_files/input_looped_file_config.yaml \
     -p config_files/pipeline_live_config.yaml \
     -o s3://my_s3_bucket/folder/


.. _boto config file: http://boto.cloudhackers.com/en/latest/boto_config_tut.html
.. _AWS CLI: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
