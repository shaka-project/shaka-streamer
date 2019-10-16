## 0.3.0 (?)

 - Added autodetection of frame rate, resolution, interlacing, track numbers
 - #5: Added support for custom resolutions and bitrates
 - #23: Added hardware encoding on macOS
 - Added support for NVENC-backed hardware encoding on Linux
 - Fixed several issues in the docs, including installation instructions
 - #35: Complain if ffprobe is missing
 - #35: Fix PyYAML deprecation warning and YAML loading vulnerability
 - Fixed resolution name (1440p vs 2k)
 - Updated default bitrates
 - Added definition of 8k resolution
 - #34: Now rejects unsupported features in text inputs
 - #30: Fixed cloud upload for VOD
 - #29: Added webcam support on macOS
 - Make common errors easier to read
 - #32: Fix early shutdown and missing files
 - Added a check for gsutil and for cloud destination write access


## 0.2.0 (2019-10-14)

 - #22: Comprehensive docs now on GitHub Pages: https://google.github.io/shaka-streamer/
 - #20: Fixed orphaned processes on shutdown
 - #19: Improved cloud upload performance
 - #12: Added a setting for debug logging
 - #6: Fixed support for 6-channel audio
 - #4: Added support for arbitrary FFmpeg filters
 - #3: Added support for setting presentation delay
 - #2: Added support for setting availability window
 - #1: Added support for extracting a small time range for VOD
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
