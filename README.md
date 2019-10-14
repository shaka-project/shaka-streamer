# ![Shaka Streamer](https://raw.githubusercontent.com/google/shaka-streamer/master/docs/source/shaka-streamer-logo.png)

Shaka Streamer offers a simple config-file based approach to preparing streaming
media. It greatly simplifies the process of using FFmpeg and Shaka Packager for
both VOD and live content.

Live documentation can be found at https://google.github.io/shaka-streamer/
and is generated from the `docs/source/` folder, as well as the source code
itself.

Sample configs can be found in the [`config_files/`] folder in the repo.

[`config_files/`]: https://github.com/google/shaka-streamer/tree/master/config_files

Release versions of Shaka Streamer can be installed or upgraded through `pip3`
with:

```sh
# To install globally (drop the "sudo" for Windows):
sudo pip3 install --upgrade shaka-streamer

# To install per-user:
pip3 install --user --upgrade shaka-streamer
```
