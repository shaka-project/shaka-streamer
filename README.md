# ![Shaka Streamer](shaka-streamer-logo.png)

Shaka Streamer offers a simple config-file based approach to preparing streaming
media. It greatly simplifies the process of using FFmpeg and Shaka Packager for
both VOD and live content.


## Platform support

We support common Linux distributions and macOS.

Windows is not supported at this time due to our use of `os.mkfifo`, but we are
accepting PRs if you'd like to add Windows support.


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
in the `config_files/` folder.

### Example command-line for live streaming to Google Cloud Storage:

```sh
./main.py \
  -i config_files/input_looped_file_config.yaml \
  -p config_files/pipeline_live_config.yaml \
  -c my_cloud_bucket
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

