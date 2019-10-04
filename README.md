# ![Shaka Streamer](shaka-streamer-logo.png)

Shaka Streamer offers a simple config-file based approach to preparing streaming
media. It greatly simplifies the process of using FFmpeg and Shaka Packager for
both VOD and live content.


## Platform support

We support common Linux distributions and macOS.

Windows is not supported at this time due to our use of `os.mkfifo`, but we are
accepting PRs if you'd like to add Windows support.
See [issue #8](https://github.com/google/shaka-streamer/issues/8).


## Getting started

Shaka Streamer requires at a minimum:
 - [Python 3](https://www.python.org/downloads/)
 - [Python "yaml" module](https://pyyaml.org/)
 - [Shaka Packager](https://github.com/google/shaka-packager)
 - [FFmpeg](https://ffmpeg.org/)

See the file [PREREQS.md](PREREQS.md) for detailed instructions on installing
prerequisites and optional dependencies.

To use Shaka Streamer, you need two YAML config files: one to describe the
input, and one to describe the encoding pipeline.  Sample configs can be found
in the `config_files/` folder.  Sample inputs referenced there can be downloaded
individually over HTTPS or all at once through gsutil:

```sh
gsutil -m cp gs://shaka-streamer-assets/sample-inputs/* .
```

### Example command-line for live streaming to Google Cloud Storage:

```sh
python3 shaka_streamer.py \
  -i config_files/input_looped_file_config.yaml \
  -p config_files/pipeline_live_config.yaml \
  -c gs://my_gcs_bucket/folder/
```


### Example command-line for live streaming to Amazon S3:

```sh
python3 shaka_streamer.py \
  -i config_files/input_looped_file_config.yaml \
  -p config_files/pipeline_live_config.yaml \
  -c s3://my_s3_bucket/folder/
```

## Running tests

We have end-to-end tests that will start streams and check them from a headless
browser using Shaka Player.  End-to-end tests can be run like so:

```sh
python3 run_end_to_end_tests.py
```

## Hardware encoding

For details on hardware encoding support, see the file
[HARDWARE_ENCODING.md](HARDWARE_ENCODING.md).


## Technical details

Shaka Streamer connects FFmpeg and Shaka Packager in a pipeline, such that
output from FFmpeg is piped directly into the packager, and packaging and
transcoding of all resolutions, bitrates, and languages occur in parallel.

The overall pipeline is composed of several nodes.  At a minimum, these are
`TranscoderNode` (which runs FFmpeg) and `PackagerNode` (which runs Shaka
Packager).  They communicate via named pipes on Linux and macOS.

If the input type is `looped_file`, then `LoopInputNode` is placed before
`TranscoderNode` in the pipeline.  `LoopInputNode` runs another instance of
FFmpeg to encode the input file in a never-ending loop, and output to a named
pipe.  For all other input types, the input files are read directly by
`TranscoderNode`.

If the `-c` option is given with a Google Cloud Storage URL, then an additional
node called `CloudNode` is added after `PackagerNode`.  It runs a thread which
watches the output of the packager and pushes updated files to the cloud.

The pipeline and the nodes in it are constructed by `ControllerNode` based on
your config files.  If you want to write your own front-end or interface
directly to the pipeline, you can create a `ControllerNode` and call the
`start()`, `stop()`, and `is_running()` methods on it.  You can use
`shaka_streamer.py` as an example of how to do this.
