# Changelog

## [1.0.0](https://github.com/shaka-project/shaka-streamer/compare/v0.5.1...v1.0.0) (2024-11-06)


### ⚠ BREAKING CHANGES

* Bump minimum Python version to 3.9 ([#171](https://github.com/shaka-project/shaka-streamer/issues/171))

### Features

* Add OPUS mp4 support ([#143](https://github.com/shaka-project/shaka-streamer/issues/143)) ([2f38022](https://github.com/shaka-project/shaka-streamer/commit/2f38022a2708dfd29e5c6f51cd7a34c1f8478004))
* Add support for FLAC codec ([#187](https://github.com/shaka-project/shaka-streamer/issues/187)) ([2edfefe](https://github.com/shaka-project/shaka-streamer/commit/2edfefe43179d97ebe64d0c72ef3d43ce9499f0b))
* Always use HLS session keys to improve player startup performance ([#181](https://github.com/shaka-project/shaka-streamer/issues/181)) ([dc56dee](https://github.com/shaka-project/shaka-streamer/commit/dc56dee91f32752667ce161604ade2f8553a739b))
* Bump minimum Python version to 3.9 ([#171](https://github.com/shaka-project/shaka-streamer/issues/171)) ([6b4b761](https://github.com/shaka-project/shaka-streamer/commit/6b4b7610cf6c311048943b5b9461bc99755873fc))
* **cloud:** Add cloud delete support ([#164](https://github.com/shaka-project/shaka-streamer/issues/164)) ([aa1f4e7](https://github.com/shaka-project/shaka-streamer/commit/aa1f4e793750573079a71bdacd11a64cf43d5730))
* **cloud:** Upload through HTTP proxy node ([#103](https://github.com/shaka-project/shaka-streamer/issues/103)) ([20c2704](https://github.com/shaka-project/shaka-streamer/commit/20c2704deacb402e39640408ac6157e94a5f78ba)), closes [#47](https://github.com/shaka-project/shaka-streamer/issues/47)
* Expand binary platforms and hardware encoding ([#161](https://github.com/shaka-project/shaka-streamer/issues/161)) ([0c4b529](https://github.com/shaka-project/shaka-streamer/commit/0c4b529d56555ad249246cd2a8c5ea935ca9edbe))
* Use modern Dolby signaling instead of duplicate representations ([#182](https://github.com/shaka-project/shaka-streamer/issues/182)) ([db55cc6](https://github.com/shaka-project/shaka-streamer/commit/db55cc651ac85bca9757c1f1c34846e0e7820bc4))


### Bug Fixes

* **cloud:** Avoid rate limit issues on live streams ([#162](https://github.com/shaka-project/shaka-streamer/issues/162)) ([1231502](https://github.com/shaka-project/shaka-streamer/commit/1231502c068e15c6e10b856520d5fc891a5bcc20))
* **cloud:** Fix write failures from Packager ([#167](https://github.com/shaka-project/shaka-streamer/issues/167)) ([791e39f](https://github.com/shaka-project/shaka-streamer/commit/791e39f0a9ecb12252eb6ed08155653f6614c5ab))
* **cloud:** Quiet the HTTP server log ([#163](https://github.com/shaka-project/shaka-streamer/issues/163)) ([4170d21](https://github.com/shaka-project/shaka-streamer/commit/4170d218dc834f9b174019287320de64e596e54c))
* **cloud:** Retry on all failures ([#165](https://github.com/shaka-project/shaka-streamer/issues/165)) ([7bb46d4](https://github.com/shaka-project/shaka-streamer/commit/7bb46d446ae645ab0fbe471bf59ff3091a87c6e7))
* Fix frame-rate and resolution auto-detection edge case ([#129](https://github.com/shaka-project/shaka-streamer/issues/129)) ([f42188e](https://github.com/shaka-project/shaka-streamer/commit/f42188e9bb93af1e27116b42a759a8e49587f7a9)), closes [#127](https://github.com/shaka-project/shaka-streamer/issues/127)
* Fix framerate autodetection edge case ([#128](https://github.com/shaka-project/shaka-streamer/issues/128)) ([aacabdc](https://github.com/shaka-project/shaka-streamer/commit/aacabdc9bb4b82331d49e91ca41abfbb889cb49e)), closes [#127](https://github.com/shaka-project/shaka-streamer/issues/127)
* Fix typing of log_request ([#166](https://github.com/shaka-project/shaka-streamer/issues/166)) ([c38d7e9](https://github.com/shaka-project/shaka-streamer/commit/c38d7e9f4ba0962c5c9b186bc3ed13f6a747903e))
* **HLS:** Fix audio grouping by codec ([#185](https://github.com/shaka-project/shaka-streamer/issues/185)) ([7f07eec](https://github.com/shaka-project/shaka-streamer/commit/7f07eec9042ae62a1e1c6719c0ad4f8fffc2775f))
* only use the first line of ffprobe's output ([#120](https://github.com/shaka-project/shaka-streamer/issues/120)) ([4d7d077](https://github.com/shaka-project/shaka-streamer/commit/4d7d077e270474f99a2c6851133e8b97b738e990)), closes [#119](https://github.com/shaka-project/shaka-streamer/issues/119)


### Documentation

* Update cloud upload docs ([#168](https://github.com/shaka-project/shaka-streamer/issues/168)) ([fddf413](https://github.com/shaka-project/shaka-streamer/commit/fddf4139800c27c16433033c7c920daa13a0f900))

## [0.5.1](https://github.com/shaka-project/shaka-streamer/compare/v0.5.0...v0.5.1) (2021-10-14)

 - Require Shaka Packager v2.6.1+, to fix segfault in Linux binaries
   (https://github.com/shaka-project/shaka-packager/issues/996)


## [0.5.0](https://github.com/shaka-project/shaka-streamer/compare/v0.4.0...v0.5.0) (2021-10-01)

 - Command-line argument style changed (dashes instead of underscores)
 - Multi period support for DASH
   (https://github.com/shaka-project/shaka-streamer/issues/43)
   (https://github.com/shaka-project/shaka-streamer/pull/78)
   (https://github.com/shaka-project/shaka-streamer/pull/91)
 - Multi period support for HLS
   (https://github.com/shaka-project/shaka-streamer/issues/43)
   (https://github.com/shaka-project/shaka-streamer/pull/83)
   (https://github.com/shaka-project/shaka-streamer/pull/91)
 - LL-DASH support
   (https://github.com/shaka-project/shaka-streamer/pull/88)
 - Require Python 3.6+
 - Require Shaka Packager v2.6+
 - New shaka-streamer-binaries package for binary dependencies;
   add argument --use-system-binaries to use your system-installed deps instead
   (https://github.com/shaka-project/shaka-streamer/issues/60)
   (https://github.com/shaka-project/shaka-streamer/pull/87)
   (https://github.com/shaka-project/shaka-streamer/pull/92)
 - Fix framerate detection for mixed-framerate content
   (https://github.com/shaka-project/shaka-streamer/issues/90)
   (https://github.com/shaka-project/shaka-streamer/pull/93)
 - Fix cloud upload errors for S3
   (https://github.com/shaka-project/shaka-streamer/issues/67)
 - Report clear error if an input track does not exist
   (https://github.com/shaka-project/shaka-streamer/issues/89)
   (https://github.com/shaka-project/shaka-streamer/pull/94)
 - Fix orphaned subprocesses using CTRL-C
   (https://github.com/shaka-project/shaka-streamer/issues/46)
   (https://github.com/shaka-project/shaka-streamer/pull/96)
 - Add webcam and microphone support on Windows
   (https://github.com/shaka-project/shaka-streamer/pull/95)


## [0.4.0](https://github.com/shaka-project/shaka-streamer/compare/v0.3.0...v0.4.0) (2021-08-26)

 - Fix shutdown of cloud upload
 - Improve the formatting of minimum version errors
 - Fix several issues with Ubuntu 16.04 and Python 3.5
 - Add `--skip_deps_check` to bypass version checks on dependencies
 - Increase preserved segments outside of the availability window, improving HLS
   playback in Shaka Player
 - Require Shaka Packager v2.5+
 - Add AV1 support
   (https://github.com/shaka-project/shaka-streamer/issues/10)
 - Drop `raw_images` input type
   (https://github.com/shaka-project/shaka-streamer/issues/25)
 - Fix duplicate transcoder outputs with multiple audio languages
 - Fix resolution autodetection boundary cases
 - Add support for extracting text streams from multiplexed inputs
   (https://github.com/shaka-project/shaka-streamer/issues/53)
 - Improved type-checking and type annotations
 - Fix install commands in docs
   (https://github.com/shaka-project/shaka-streamer/issues/56)
 - Fix various test failures and test-runner bugs
 - Fix packaging failures with long-running content
   (https://github.com/shaka-project/shaka-streamer/issues/64)
 - Add raw-key support
   (https://github.com/shaka-project/shaka-streamer/issues/21)
   (https://github.com/shaka-project/shaka-streamer/pull/63)
 - Add support for ac3 and ec3
   (https://github.com/shaka-project/shaka-streamer/issues/37)
   (https://github.com/shaka-project/shaka-streamer/pull/69)
 - Fix running tests from any directory
   (https://github.com/shaka-project/shaka-streamer/issues/49)
   (https://github.com/shaka-project/shaka-streamer/pull/71)
 - Add config file with Apple's HLS recommendations
   (https://github.com/shaka-project/shaka-streamer/issues/70)
   (https://github.com/shaka-project/shaka-streamer/pull/72)
 - Add support for HEVC video codec
   (https://github.com/shaka-project/shaka-streamer/pull/74)
 - Restrict WebM formats to DASH, omit from HLS
   (https://github.com/shaka-project/shaka-streamer/issues/18)
   (https://github.com/shaka-project/shaka-streamer/pull/80)
 - Automatic frame rate reduction
   (https://github.com/shaka-project/shaka-streamer/pull/77)
 - Fix missing members in docs, auto-link to types in config docs
 - Change the documentation theme
 - Set channel count as an input feature, downmix as needed
   (https://github.com/shaka-project/shaka-streamer/issues/38)
   (https://github.com/shaka-project/shaka-streamer/pull/84)
 - Add Windows support
   (https://github.com/shaka-project/shaka-streamer/issues/8)
   (https://github.com/shaka-project/shaka-streamer/pull/85)
 - Add HTTP url output support
   (https://github.com/shaka-project/shaka-streamer/pull/82)
 - Fix accidental live-type DASH output in VOD mode


## [0.3.0](https://github.com/shaka-project/shaka-streamer/compare/v0.2.0...v0.3.0) (2019-10-18)

 - Added autodetection of frame rate, resolution, interlacing, track numbers
 - Added support for custom resolutions and bitrates
   (https://github.com/shaka-project/shaka-streamer/issues/5)
 - Added hardware encoding on macOS
   (https://github.com/shaka-project/shaka-streamer/issues/23)
 - Added support for NVENC-backed hardware encoding on Linux
 - Fixed several issues in the docs, including installation instructions
 - Complain if ffprobe is missing
   (https://github.com/shaka-project/shaka-streamer/issues/35)
 - Fix PyYAML deprecation warning and YAML loading vulnerability
   (https://github.com/shaka-project/shaka-streamer/issues/35)
 - Fixed resolution name (1440p vs 2k)
 - Updated default bitrates
 - Added definition of 8k resolution
 - Now rejects unsupported features in text inputs
   (https://github.com/shaka-project/shaka-streamer/issues/34)
 - Fixed cloud upload for VOD
   (https://github.com/shaka-project/shaka-streamer/issues/30)
 - Added webcam support on macOS
   (https://github.com/shaka-project/shaka-streamer/issues/29)
 - Make common errors easier to read
 - Fixed early shutdown and missing files
   (https://github.com/shaka-project/shaka-streamer/issues/32)
 - Added a check for gsutil and for cloud destination write access
 - Speed up VP9 software encoding
 - Fixed rounding errors in width in HLS playlist
   (https://github.com/shaka-project/shaka-streamer/issues/36)


## [0.2.0](https://github.com/shaka-project/shaka-streamer/compare/v0.1.0...v0.2.0) (2019-10-14)

 - Comprehensive docs now on GitHub Pages: https://shaka-project.github.io/shaka-streamer/
   (https://github.com/shaka-project/shaka-streamer/issues/22)
 - Fixed orphaned processes on shutdown
   (https://github.com/shaka-project/shaka-streamer/issues/20)
 - Improved cloud upload performance
   (https://github.com/shaka-project/shaka-streamer/issues/19)
 - Added a setting for debug logging
   (https://github.com/shaka-project/shaka-streamer/issues/12)
 - Fixed support for 6-channel audio
   (https://github.com/shaka-project/shaka-streamer/issues/6)
 - Added support for arbitrary FFmpeg filters
   (https://github.com/shaka-project/shaka-streamer/issues/4)
 - Added support for setting presentation delay
   (https://github.com/shaka-project/shaka-streamer/issues/3)
 - Added support for setting availability window
   (https://github.com/shaka-project/shaka-streamer/issues/2)
 - Added support for extracting a small time range for VOD
   (https://github.com/shaka-project/shaka-streamer/issues/1)
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
