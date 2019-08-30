// Copyright 2019 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

const flaskServerUrl = 'http://localhost:5000/';
const dashManifestUrl = flaskServerUrl + 'output_files/output.mpd';
const hlsManifestUrl = flaskServerUrl + 'output_files/master_playlist.m3u8';
const TEST_DIR = 'test_assets/';
let player;

async function startStreamer(inputConfig, pipelineConfig) {
  // Send a request to flask server to start Shaka Streamer.
  const response = await fetch(flaskServerUrl + 'start', {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain',
    },
    body: JSON.stringify({
      'input_config': inputConfig,
      'pipeline_config': pipelineConfig
    }),
  });

  if (!response.ok) {
    throw new Error('Failed to produce manifest');
  }
}

async function stopStreamer() {
  // Send a request to flask server to stop Shaka Streamer.
  const response = await fetch(flaskServerUrl + 'stop');
  if (!response.ok) {
    throw new Error('Failed to close Shaka Streamer');
  }
}

describe('Shaka Streamer', () => {
  let video;

  beforeAll(() => {
    shaka.polyfill.installAll();
    jasmine.DEFAULT_TIMEOUT_INTERVAL = 400 * 1000;
  });

  beforeEach(() => {
    video = document.createElement('video');
    video.muted = true;
    document.body.appendChild(video);

    player = new shaka.Player(video);
    player.addEventListener('error', (error) => {
      fail(error);
    });
  });

  afterEach(async () => {
    await player.destroy();
    await stopStreamer();
    document.body.removeChild(video);
  });

  resolutionTests(hlsManifestUrl, '(hls)');
  resolutionTests(dashManifestUrl, '(dash)');
  liveTests(hlsManifestUrl, '(hls)');
  liveTests(dashManifestUrl, '(dash)');
  drmTests(hlsManifestUrl, '(hls)');
  drmTests(dashManifestUrl, '(dash)');
  codecTests(hlsManifestUrl, '(hls)');
  codecTests(dashManifestUrl, '(dash)');
  autoLanguageTests(hlsManifestUrl, '(hls)');
  autoLanguageTests(dashManifestUrl, '(dash)');
  languageTests(hlsManifestUrl, '(hls)');
  languageTests(dashManifestUrl, '(dash)');
  // TODO: Test is commented out until Packager outputs codecs for vtt in mp4.
  // textTracksTests(hlsManifestUrl, '(hls)');
  textTracksTests(dashManifestUrl, '(dash)');
  vodTests(hlsManifestUrl, '(hls)');
  vodTests(dashManifestUrl, '(dash)');
  // TODO: Redo this test with both 5.1 and stereo once 5.1 is supported.
  channelsTests(hlsManifestUrl, '(hls)');
  channelsTests(dashManifestUrl, '(dash)');
});

function resolutionTests(manifestUrl, format) {
  it('has output resolutions matching the resolutions in config ' + format,
      async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'input_type': 'looped_file',
          'media_type': 'video',
          'frame_rate': 24.0,
          'resolution': '1080p',
          'track_num': 0,
        },
      ]
    };
    const pipelineConfigDict = {
      // Mode of streaming. Can either be live or vod.
      'transcoder': {
        // A list of resolutions to encode.
        'resolutions': [
          '4k',
          '1080p',
          '720p',
          '480p',
          '240p',
          '144p',
        ],
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const heightList = trackList.map(track => track.height);
    heightList.sort((a, b) => a - b);
    expect(heightList).toEqual([144, 240, 480, 720, 1080]);
  });
}

function liveTests(manifestUrl, format) {
  it('has a live streaming mode ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'input_type': 'looped_file',
          'media_type': 'video',
          'frame_rate': 24.0,
          'resolution': '1080p',
          'track_num': 0,
        },
      ]
    };
    const pipelineConfigDict = {
      // Mode of streaming. Can either be live or vod.
      'streaming_mode': 'live',
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    expect(player.isLive()).toBe(true);
  });
}

function drmTests(manifestUrl, format) {
  it('has encryption enabled ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'input_type': 'looped_file',
          'media_type': 'video',
          'frame_rate': 24.0,
          'resolution': '1080p',
          'track_num': 0,
        },
      ]
    };
    const pipelineConfigDict = {
      'packager': {
        'encryption': {
          // Enables encryption.
          'enable': true,
          'clear_lead': 0,
        },
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    // Player should raise an error and not load because the media
    // is encrypted and the player doesn't have a license server.
    await expectAsync(player.load(manifestUrl)).toBeRejected(
        "Encrypted media should not play without a license server");

    player.configure({
      drm: {
        servers: {
          'com.widevine.alpha': 'https://cwip-shaka-proxy.appspot.com/no_auth',
        },
      },
    });
    // Player should now be able to load because the player has a license server.
    await player.load(manifestUrl);
  });
}

function codecTests(manifestUrl, format) {
  it('has output codecs matching the codecs in config ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          'track_num': 0,
          'frame_rate': 24.0,
          'resolution': '4k',
          'is_interlaced': false,
        },
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          'track_num': 1,
        },
      ],
    };
    const pipelineConfigDict = {
      'transcoder': {
        'resolutions': [
          '144p',
        ],
        'audio_codecs': [
          'opus',
        ],
        'video_codecs': [
          'h264',
        ],
      },
      'packager': {
        'manifest_format': [
          'dash',
          'hls',
        ],
      },
      'streaming_mode': 'vod',
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const videoCodecList = trackList.map(track => track.videoCodec);
    const audioCodecList = trackList.map(track => track.audioCodec);
    expect(videoCodecList).toEqual(['avc1.42c01e']);
    expect(audioCodecList).toEqual(['opus']);
  });
}

function autoLanguageTests(manifestUrl, format) {
  it('correctly autodetects the language embedded in the stream ' + format,
      async () => {
    // No language is specified in the input config, so the streamer will try
    // to find the one embedded in the metadata.
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          'input_type': 'looped_file',
          'track_num': 1,
        },
      ],
    };
    const pipelineConfigDict = {
      'transcoder': {
        'resolutions': [
          '144p',
        ],
      },
      'packager': {
        'manifest_format': [
          'dash',
          'hls',
        ],
      },
      'streaming_mode': 'live',
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const lang = trackList.map(track => track.language);
    expect(lang).toEqual(['en']);
  });
}

function languageTests(manifestUrl, format) {
  it('correctly sets the language read from the input config ' + format,
      async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          'track_num': 1,
          'language': 'zh',
        },
      ],
    };
    const pipelineConfigDict = {
      'transcoder': {
        'resolutions': [
          '144p',
        ],
      },
      'packager': {
        'manifest_format': [
          'dash',
          'hls',
        ],
      },
      'streaming_mode': 'vod',

    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const lang = trackList.map(track => track.language);
    expect(lang).toEqual(['zh']);
  });
}

function textTracksTests(manifestUrl, format) {
  it('outputs correct text tracks ' + format, async () => {
    const inputConfigDict = {
      // List of inputs. Each one is a dictionary.
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'input_type': 'looped_file',
          'media_type': 'video',
          'frame_rate': 24.0,
          'resolution': '1080p',
          'track_num': 0,
        },
        {
          'name': TEST_DIR + 'Sintel.2010.English.vtt',
          'media_type': 'text',
          'language': 'en',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.Spanish.vtt',
          'media_type': 'text',
          'language': 'es',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.Esperanto.vtt',
          'media_type': 'text',
          'language': 'eo',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.Arabic.vtt',
          'media_type': 'text',
          'language': 'ar',
        },
      ],
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'transcoder': {
        'resolutions': [
          '144p',
        ],
        // This test currently only tests aac with h264, which means webm
        // won't be an output.  With webm, it doesnt work on chrome.
        'audio_codecs': [
          'aac',
        ],
        'video_codecs': [
          'h264',
        ],
      },
      'packager': {
        'segment_per_file': false,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getTextTracks();
    const languageList = trackList.map(track => track.language);
    languageList.sort();
    expect(languageList).toEqual(['ar', 'en', 'eo', 'es']);
  });
}

function vodTests(manifestUrl, format) {
  it('has a vod streaming mode', async () => {
    const inputConfigDict = {
      // List of inputs. Each one is a dictionary.
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'input_type': 'looped_file',
          'media_type': 'video',
          'frame_rate': 24.0,
          'resolution': '1080p',
          'track_num': 0,
        },
      ],
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'transcoder': {
        'resolutions': [
          '144p',
        ],
        'audio_codecs': [
          'aac',
        ],
        'video_codecs': [
          'h264',
        ],
      },
      'packager': {
        'segment_per_file': false,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    expect(player.isLive()).toBe(false);
  });
}

function channelsTests(manifestUrl, format) {
  it('outputs the correct number of channels', async () => {
    const inputConfigDict = {
      // List of inputs. Each one is a dictionary.
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'input_type': 'looped_file',
          'media_type': 'audio',
          'track_num': 1,
        },
      ],
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'transcoder': {
        'resolutions': [
          '144p',
        ],
        'audio_codecs': [
          'aac',
        ],
        'video_codecs': [
          'h264',
        ],
        'channels': 2,
      },
      'packager': {
        'segment_per_file': false,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    const trackList = player.getVariantTracks();
    expect(trackList.length).toBe(1);
    expect(trackList[0].channelsCount).toBe(2);
  });
}
