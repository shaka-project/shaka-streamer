# Installing Prerequisites for Shaka Streamer

## Yaml Module

We use the Python YAML module to parse config files.  To install it on Ubuntu:

```sh
sudo apt -y install python3-yaml
```

This can also be installed via pip on any platform:

```sh
pip3 install --user pyyaml
```

## Shaka Packager

Pre-built Shaka Packager binaries can be downloaded from github here:
https://github.com/google/shaka-packager/releases

To install a Shaka Packager binary on Linux:

```sh
sudo install -m 755 ~/Downloads/packager-linux /usr/local/bin/packager
```

To build Shaka Packager from source, follow instructions here:
https://google.github.io/shaka-packager/html/build_instructions.html

## FFmpeg

If your Linux distribution has FFmpeg v4.1+, you can just install the package.
For example, this will work in Ubuntu 19.04+:

```sh
sudo apt -y install ffmpeg
```

For older versions of Ubuntu or any other Linux distro which does not have a new
enough version of FFmpeg, you can build it from source.  For example:

```sh
sudo apt -y install \
  libx264-dev libvpx-dev libopus-dev libfreetype6-dev \
  libfontconfig1-dev libsdl2-dev yasm

git clone https://github.com/FFmpeg/FFmpeg ffmpeg
cd ffmpeg
git checkout n4.1.3
./configure \
  --enable-libx264 --enable-libvpx --enable-libopus --enable-gpl \
  --enable-libfreetype --enable-libfontconfig --enable-vaapi
make
sudo make install
```

For Mac, you can either build FFmpeg from source or you can use
[Homebrew](https://brew.sh/) to install it:

```sh
brew install ffmpeg
```

## Cloud Storage (optional)

Shaka Streamer can push content directly to a Google Cloud Storage or Amazon S3
bucket.  To use this feature, the Google Cloud SDK is required.

See https://cloud.google.com/sdk/install for details on installing the Google
Cloud SDK on your platform.

### Google Cloud Storage

If you haven't already, you will need to initialize your gcloud environment and
log in through your browser.

```sh
gcloud init
```

Follow the instructions given to you by gcloud to initialize the environment and
login.

### Amazon S3

To authenticate to Amazon S3, you can either add credentials to your [boto
config file](http://boto.cloudhackers.com/en/latest/boto_config_tut.html) or
login interactively using the [AWS CLI](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html).


## Test Dependencies (optional)

To run the end-to-end tests, you must install Flask & NPM.  In Ubuntu 19.04+:

```sh
sudo apt -y python3-flask nodejs npm
# Upgrade to a recent npm, which is not packaged:
sudo npm install -g npm
```

Flask can also be installed via pip on any platform:

```sh
pip3 install --user flask
```

To install Node.js & NPM on any other platform, you can try one of these:
 - https://github.com/nodesource/distributions
 - https://nodejs.org/en/download/

