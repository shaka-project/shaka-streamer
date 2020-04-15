## 0.4.0 (???)

 - Fix shutdown of cloud upload
 - Improve the formatting of minimum version errors
 - Fix several issues with Ubuntu 16.04 and Python 3.5
 - Add `--skip_deps_check` to bypass version checks on dependencies
 - Increase preserved segments outside of the availability window, improving HLS
   playback in Shaka Player
 - Require Shaka Packager v2.4+
 - Add AV1 support
   (https://github.com/google/shaka-streamer/issues/10)
 - Drop `raw_images` input type
   (https://github.com/google/shaka-streamer/issues/25)
 - Fix duplicate transcoder outputs with multiple audio languages
 - Fix resolution autodetection boundary cases
 - Add support for extracting text streams from multiplexed inputs
   (https://github.com/google/shaka-streamer/issues/53)


## 0.3.0 (2019-10-18)

 - Added autodetection of frame rate, resolution, interlacing, track numbers
 - Added support for custom resolutions and bitrates
   (https://github.com/google/shaka-streamer/issues/5)
 - Added hardware encoding on macOS
   (https://github.com/google/shaka-streamer/issues/23)
 - Added support for NVENC-backed hardware encoding on Linux
 - Fixed several issues in the docs, including installation instructions
 - Complain if ffprobe is missing
   (https://github.com/google/shaka-streamer/issues/35)
 - Fix PyYAML deprecation warning and YAML loading vulnerability
   (https://github.com/google/shaka-streamer/issues/35)
 - Fixed resolution name (1440p vs 2k)
 - Updated default bitrates
 - Added definition of 8k resolution
 - Now rejects unsupported features in text inputs
   (https://github.com/google/shaka-streamer/issues/34)
 - Fixed cloud upload for VOD
   (https://github.com/google/shaka-streamer/issues/30)
 - Added webcam support on macOS
   (https://github.com/google/shaka-streamer/issues/29)
 - Make common errors easier to read
 - Fixed early shutdown and missing files
   (https://github.com/google/shaka-streamer/issues/32)
 - Added a check for gsutil and for cloud destination write access
 - Speed up VP9 software encoding
 - Fixed rounding errors in width in HLS playlist
   (https://github.com/google/shaka-streamer/issues/36)


## 0.2.0 (2019-10-14)

 - Comprehensive docs now on GitHub Pages: https://google.github.io/shaka-streamer/
   (https://github.com/google/shaka-streamer/issues/22)
 - Fixed orphaned processes on shutdown
   (https://github.com/google/shaka-streamer/issues/20)
 - Improved cloud upload performance
   (https://github.com/google/shaka-streamer/issues/19)
 - Added a setting for debug logging
   (https://github.com/google/shaka-streamer/issues/12)
 - Fixed support for 6-channel audio
   (https://github.com/google/shaka-streamer/issues/6)
 - Added support for arbitrary FFmpeg filters
   (https://github.com/google/shaka-streamer/issues/4)
 - Added support for setting presentation delay
   (https://github.com/google/shaka-streamer/issues/3)
 - Added support for setting availability window
   (https://github.com/google/shaka-streamer/issues/2)
 - Added support for extracting a small time range for VOD
   (https://github.com/google/shaka-streamer/issues/1)
 - Added support for external commands that generate input streams
 - Added support for push to Amazon S3 (gsutil supports both GCS and S3)
 - Added a quiet mode
 - Added control over output paths
 - Fixed output filename consistency, issues with multiple languages
 - Fixed issues with mapping multiple inputs
 - Flattened pipeline config format


## 0.1.0 (2019-08-30)

The first public release of Shaka Streamer! :tada:

This initial release was the work of @vickymin13 and @prestontai. Many thanks
to both of them for their hard work and dedication! It has been wonderful
having them on the team.
