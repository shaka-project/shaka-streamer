# Hardware Encoding with Shaka Streamer

## Setup on Linux

Hardware encoding on Linux can be enabled through FFmpeg's vaapi support.

To get started, install the appropriate vaapi package for your device.  For
example, for Intel's Kaby Lake family of processors, which support hardware VP9
encoding, you would install this on Ubuntu:

```sh
sudo apt install i965-va-driver
```

Or build & install from source here: https://github.com/intel/intel-vaapi-driver

You will need to install the correct vaapi drivers for your device.  These are
only examples.

If hardware encoding still does not work, you may need to recompile FFmpeg from
source.  See instructions in [PREREQS.md](PREREQS.md) for details.

## Setup on Mac & Windows

Hardware encoding for Mac & Windows is not yet supported, but we are accepting
PRs if you'd like to contribute additional platform support.  This doc may be a
useful reference for hardware-related options in FFmpeg:
https://trac.ffmpeg.org/wiki/HWAccelIntro

## Configuration

TODO
