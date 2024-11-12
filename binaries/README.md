# ![Shaka Streamer](https://raw.githubusercontent.com/shaka-project/shaka-streamer/main/docs/source/shaka-streamer-logo.png)

Shaka Streamer Binaries is a companion package to [Shaka Streamer][] that
provides platform-specific binaries for Streamer's dependencies: [FFmpeg][] and
[Shaka Packager][].

FFmpeg binaries are built from open, verifiable, automated workflows at
https://github.com/shaka-project/static-ffmpeg-binaries

Shaka Packager binaries are official releases from
https://github.com/shaka-project/shaka-packager

Install or upgrade Shaka Streamer and its binaries through `pip3` with:

```sh
# To install globally (drop the "sudo" for Windows):
sudo pip3 install --upgrade shaka-streamer shaka-streamer-binaries

# To install per-user:
pip3 install --user --upgrade shaka-streamer shaka-streamer-binaries
```

[FFmpeg]: https://ffmpeg.org/
[Shaka Packager]: https://github.com/shaka-project/shaka-packager
[Shaka Streamer]: https://pypi.org/project/shaka-streamer/
