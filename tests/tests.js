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
const outputHttpUrl = 'http://localhost:80/';
const dashManifestUrl = flaskServerUrl + 'output_files/dash.mpd';
const hlsManifestUrl = flaskServerUrl + 'output_files/hls.m3u8';
const OUTPUT_DIR = 'output_files/'
const TEST_DIR = 'test_assets/';
let player;
let video;

async function startStreamer(inputConfig, pipelineConfig, bitrateConfig={}, outputLocation=OUTPUT_DIR) {
  // Send a request to flask server to start Shaka Streamer.
  const response = await fetch(flaskServerUrl + 'start', {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain',
    },
    body: JSON.stringify({
      'input_config': inputConfig,
      'pipeline_config': pipelineConfig,
      'bitrate_config': bitrateConfig,
      'output_location': outputLocation
    }),
  });

  // We use status code 418 for specially-formatted config errors.
  if (response.status == 418) {
    const error = await response.json();
    throw error;
  }

  if (!response.ok) {
    // For anything else, log the full text and fail with an error containing
    // the status code.
    console.log(response.status, response.statusText, await response.text());
    throw new Error('Failed to produce manifest: HTTP ' + response.status);
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

  errorTests();

  resolutionTests(hlsManifestUrl, '(hls)');
  resolutionTests(dashManifestUrl, '(dash)');

  liveTests(hlsManifestUrl, '(hls)');
  liveTests(dashManifestUrl, '(dash)');

  drmTests(hlsManifestUrl, '(hls)');
  drmTests(dashManifestUrl, '(dash)');

  codecTests(hlsManifestUrl, '(hls)');
  codecTests(dashManifestUrl, '(dash)');

  // These tests are independent of manifest type, since they are about
  // auto-detecting input features.
  autoDetectionTests(dashManifestUrl);

  languageTests(hlsManifestUrl, '(hls)');
  languageTests(dashManifestUrl, '(dash)');

  // TODO: Test is commented out until Packager outputs codecs for vtt in mp4.
  // textTracksTests(hlsManifestUrl, '(hls)');
  textTracksTests(dashManifestUrl, '(dash)');

  vodTests(hlsManifestUrl, '(hls)');
  vodTests(dashManifestUrl, '(dash)');

  channelsTests(hlsManifestUrl, 2, '(hls)');
  channelsTests(dashManifestUrl, 2, '(dash)');
  channelsTests(hlsManifestUrl, 6, '(hls)');
  channelsTests(dashManifestUrl, 6, '(dash)');

  // The HLS manifest does not indicate the availability window, so only test
  // this in DASH.
  availabilityTests(dashManifestUrl, '(dash)');

  // The HLS manifest does not indicate the presentation delay, so only test
  // this in DASH.
  delayTests(dashManifestUrl, '(dash)');

  // The HLS manifest does not indicate the update period, so only test this in
  // DASH.
  updateTests(dashManifestUrl, '(dash)');

  durationTests(hlsManifestUrl, '(hls)');
  durationTests(dashManifestUrl, '(dash)');

  mapTests(hlsManifestUrl, '(hls)');
  mapTests(dashManifestUrl, '(dash)');

  // The player doesn't have any framerate or other metadata from an HLS
  // manifest that would let us detect our filters, so only test this in DASH.
  filterTests(dashManifestUrl, '(dash)');

  // TODO: Add tests for interlaced video.  We need interlaced source material
  // for this.

  customBitrateTests();

  // TODO: Test is commented out until Packager outputs codecs for vtt in mp4.
  // muxedTextTests(hlsManifestUrl, '(hls)');
  muxedTextTests(dashManifestUrl, '(dash)');

  multiPeriodTests(dashManifestUrl, '(dash)');
});

function errorTests() {
  function getBasicInputConfig() {
    // Return a standard input config that each test can change and break
    // without repeating everything.
    return {
      inputs: [
        {
          name: TEST_DIR + 'BigBuckBunny.1080p.mp4',
          media_type: 'video',
        },
      ],
    };
  }

  const minimalPipelineConfig = {
    streaming_mode: 'vod',
    resolutions: ['144p'],
  };

  it('fails when extra fields are present', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].foo = 'bar';

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'UnrecognizedField',
          field_name: 'foo',
        }));
  });

  it('fails when media_type is missing', async () => {
    const inputConfig = getBasicInputConfig();
    delete inputConfig.inputs[0].media_type;

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MissingRequiredField',
          field_name: 'media_type',
        }));
  });

  it('fails when missing fields cannot be autodetected', async () => {
    const inputConfig = getBasicInputConfig();
    // This input_type doesn't support autodetection.
    inputConfig.inputs[0].input_type = 'external_command';
    // frame_rate is required.
    inputConfig.inputs[0].frame_rate = 24;
    // resolution is required, but missing.

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MissingRequiredField',
          field_name: 'resolution',
        }));

    // now resolution is present, but frame_rate is missing.
    delete inputConfig.inputs[0].frame_rate;
    inputConfig.inputs[0].resolution = '1080p';

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MissingRequiredField',
          field_name: 'frame_rate',
        }));
  });

  it('fails when frame_rate is not a number', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].frame_rate = '99';

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'WrongType',
          field_name: 'frame_rate',
        }));
  });

  it('fails when resolution is unrecognized', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].resolution = 'wee';

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MalformedField',
          field_name: 'resolution',
        }));
  });

  it('fails when track_num is not an int', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].track_num = 1.1;

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'WrongType',
          field_name: 'track_num',
        }));
  });

  it('fails when start_time/end_time used with non-file inputs', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].input_type = 'external_command';
    inputConfig.inputs[0].frame_rate = 24;
    inputConfig.inputs[0].resolution = '1080p';
    inputConfig.inputs[0].start_time = '0:30'

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MalformedField',
          field_name: 'start_time',
        }));

    delete inputConfig.inputs[0].start_time
    inputConfig.inputs[0].end_time = '0:90'

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MalformedField',
          field_name: 'end_time',
        }));
  });

  it('fails when filters is not a list of strings', async () => {
    const inputConfig = getBasicInputConfig();
    inputConfig.inputs[0].filters = 'foo';

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'WrongType',
          field_name: 'filters',
        }));

    inputConfig.inputs[0].filters = [{}];

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'WrongType',
          field_name: 'filters',
        }));
  });

  it('fails when segment_per_file is false for live', async () => {
    const inputConfig = getBasicInputConfig();
    const pipelineConfig = {
      streaming_mode: 'live',
      resolutions: [],
      segment_per_file: false,
    };

    await expectAsync(startStreamer(inputConfig, pipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MalformedField',
          field_name: 'segment_per_file',
        }));
  });

  it('fails when content_id is not a hex string', async () => {
    const inputConfig = getBasicInputConfig();
    const pipelineConfig = {
      streaming_mode: 'vod',
      resolutions: [],
      encryption: {
        enable: true,
        content_id: 'foo',
      },
    };

    await expectAsync(startStreamer(inputConfig, pipelineConfig))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MalformedField',
          field_name: 'content_id',
        }));
  });

  it('fails when both "inputs" and "multiperiod_inputs_list" are given', async() => {
    const inputConfig = getBasicInputConfig();
    inputConfig.multiperiod_inputs_list = [
      getBasicInputConfig(),
      getBasicInputConfig(),
    ];
    const pipeline_config = {
      streaming_mode: 'vod',
      resolutions: [],
    };

    await expectAsync(startStreamer(inputConfig, pipeline_config))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'ConflictingFields',
          field_name: 'inputs',
        }));
  });

  it('fails when neither "inputs" nor "multiperiod_inputs_list" is given', async() => {
    const inputConfig = {};
    const pipeline_config = {
      streaming_mode: 'vod',
      resolutions: [],
    };

    await expectAsync(startStreamer(inputConfig, pipeline_config))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'MissingRequiredExclusiveFields',
          field_name: 'inputs',
        }));
  });

  it('fails when segment_per_file is false with a HTTP url output', async () => {
    const inputConfig = getBasicInputConfig();
    const pipelineConfig = {
      streaming_mode: 'vod',
      resolutions: [],
      segment_per_file: false,
    };

    await expectAsync(startStreamer(inputConfig, pipelineConfig, {}, outputHttpUrl))
    .toBeRejectedWith(jasmine.objectContaining({
      error_type: 'RuntimeError',
    }));
  });

  it('fails when multiperiod_inputs_list is used with a HTTP url output', async () => {
    const inputConfig = {
      'multiperiod_inputs_list': [
        getBasicInputConfig(),
      ],
    };

    await expectAsync(startStreamer(inputConfig, minimalPipelineConfig, {}, outputHttpUrl))
        .toBeRejectedWith(jasmine.objectContaining({
          error_type: 'RuntimeError',
        }));
  });
}

function resolutionTests(manifestUrl, format) {
  it('has output resolutions matching the resolutions in config ' + format,
      async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          'resolution': '1080p',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ]
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      // A list of resolutions to encode.
      'resolutions': [
        '4k',
        '1440p',
        '1080p',
        '720p',
        '480p',
        '240p',
        '144p',
      ],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const heightList = trackList.map(track => track.height);
    heightList.sort((a, b) => a - b);
    // No 4k or 1440p, since those are above the 1080p input res.
    expect(heightList).toEqual([144, 240, 480, 720, 1080]);
  });
}

function liveTests(manifestUrl, format) {
  it('has a live streaming mode ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'input_type': 'looped_file',
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
        },
      ]
    };
    const pipelineConfigDict = {
      'streaming_mode': 'live',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    expect(player.isLive()).toBe(true);
  });
}

function drmTests(manifestUrl, format) {
  it('has widevine encryption enabled ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ]
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'encryption': {
        // Enables encryption.
        'enable': true,
        'clear_lead': 0,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    // Player should raise an error and not load because the media
    // is encrypted and the player doesn't have a license server.
    await expectAsync(player.load(manifestUrl)).toBeRejectedWith(
        jasmine.objectContaining({
          code: shaka.util.Error.Code.NO_LICENSE_SERVER_GIVEN,
        }));

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

  it('has raw key encryption enabled ' + format, async () => {
    // Clear Key format is not supported in HLS with Shaka Player yet
    // so for now we bypass the hls tests.
    // See: https://github.com/google/shaka-player/issues/2146
    if (manifestUrl.indexOf('hls.m3u8') !== -1) {
      return pending();
    }
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ]
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'encryption': {
        // Enables encryption.
        'enable': true,
        // Enables raw keys
        'encryption_mode': 'raw',
        'keys': [
          {
            'key_id': '1e044b199a81850e1927e776e7228cad',
            'key': '0c3b6b7882ecbf9683bd34e189a5acf8',
          }
        ],
        'clear_lead': 0,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    // Player should raise an error and not load because the media
    // is encrypted and the player doesn't have a license server.
    await expectAsync(player.load(manifestUrl)).toBeRejectedWith(
        jasmine.objectContaining({
          code: shaka.util.Error.Code.NO_LICENSE_SERVER_GIVEN,
        }));

    player.configure({
      drm: {
        clearKeys: {
          '1e044b199a81850e1927e776e7228cad': '0c3b6b7882ecbf9683bd34e189a5acf8'
        },
      },
    });
    // Player should now be able to load because the player has a license server.
    await player.load(manifestUrl);
  });

  it('has raw key drm label support ' + format, async () => {
    // Clear Key format is not supported in HLS with Shaka Player yet
    // so for now we bypass the hls tests.
    // See: https://github.com/google/shaka-player/issues/2146
    if (manifestUrl.indexOf('hls.m3u8') !== -1) {
      return pending();
    }
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ]
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'encryption': {
        // Enables encryption.
        'enable': true,
        // Enables raw keys
        'encryption_mode': 'raw',
        'keys': [
          {
            'label': 'SD',
            'key_id': '1e044b199a81850e1927e776e7228cad',
            'key': '0c3b6b7882ecbf9683bd34e189a5acf8',
          }
        ],
        'clear_lead': 0,
      },
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    // Player should raise an error and not load because the media
    // is encrypted and the player doesn't have a license server.
    await expectAsync(player.load(manifestUrl)).toBeRejectedWith(
        jasmine.objectContaining({
          code: shaka.util.Error.Code.NO_LICENSE_SERVER_GIVEN,
        }));

    player.configure({
      drm: {
        clearKeys: {
          '1e044b199a81850e1927e776e7228cad': '0c3b6b7882ecbf9683bd34e189a5acf8'
        },
      },
    });
    // Player should now be able to load because the player has a license server.
    await player.load(manifestUrl);
  });
}

function codecTests(manifestUrl, format) {
  // Returns the audio codecs and video codecs, in that order.
  // Will not fail due to a lack of browser support for any codec.
  async function getAudioAndVideoCodecs(manifestUrl) {
    // In case the browser can't play it, check the manifest early in the
    // loading of the content.  We should at least be able to check the tracks
    // before they are filtered out.
    let codecs = null;
    player.addEventListener('manifestparsed', () => {
      const trackList = player.getVariantTracks();
      const audioCodecList = trackList.map(track => track.audioCodec)
          .filter((x) => x != null);
      const videoCodecList = trackList.map(track => track.videoCodec)
          .filter((x) => x != null);
      codecs = audioCodecList.concat(videoCodecList);
    });

    try {
      await player.load(manifestUrl);
    } catch (error) {
      // It's fine if the browser can't play any given codec.
      // Most browsers won't play HEVC, for example, as of 2021-06-08.
      // Any other error should be propagated up and fail the test.
      if (error.code != shaka.util.Error.Code.CONTENT_UNSUPPORTED_BY_BROWSER) {
        throw error;
      }
    }

    // Ensure that our event handler fired.  If not, fail the test.
    if (codecs == null) {
      throw new Error('manifestparsed event never fired!');
    }
    return codecs;
  }

  it('has output codecs matching the codecs in config ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'audio_codecs': ['aac'],
      'video_codecs': ['h264'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);

    const codecList = await getAudioAndVideoCodecs(manifestUrl);
    expect(codecList).toEqual(['mp4a.40.2', 'avc1.4d400c']);
  });

  it('supports AV1 ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'video_codecs': ['av1'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);

    const codecList = await getAudioAndVideoCodecs(manifestUrl);
    expect(codecList).toEqual(['av01.0.00M.08']);
  });

  it('supports HEVC ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'video_codecs': ['hevc'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);

    let codecList = await getAudioAndVideoCodecs(manifestUrl);
    // In HLS, we get "hvc1", but in DASH, it's "hev1".  Accept both.
    codecList = codecList.map((x) => x.replace('hvc1', 'hev1'));
    expect(codecList).toEqual(['hev1.1.6.L60.90']);
  });

  it('appropriately filters WebM formats ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': [],
      'audio_codecs': ['aac', 'opus'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const audioCodecList = trackList.map(track => track.audioCodec);
    if (manifestUrl == hlsManifestUrl) {
      expect(audioCodecList).not.toContain('opus');
    } else if (manifestUrl == dashManifestUrl) {
      expect(audioCodecList).toContain('opus');
    } 
  })
}

function autoDetectionTests(manifestUrl) {
  it('correctly autodetects the language embedded in the stream', async () => {
    // No language is specified in the input config, so the streamer will try
    // to find the one embedded in the metadata.
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': [],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    const lang = trackList.map(track => track.language);
    expect(lang).toEqual(['en']);
  });

  it('correctly autodetects the frame_rate of a video stream', async () => {
    // No frame rate is specified in the input config, so the streamer will try
    // to find the one embedded in the metadata.
    const inputConfigDict = {
      'inputs': [
        {
          // NOTE: https://github.com/google/shaka-packager/issues/662 prevents
          // this from working on Sintel.2010.720p.Small.mkv.  The Packager bug
          // does not seem to affect typical inputs.
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);

    await player.load(manifestUrl);
    const trackList = player.getVariantTracks();
    expect(trackList[0].frameRate).toBe(30);
  });

  it('correctly autodetects the input resolution of the video', async () => {
    // No resolution is specified in the input config, so the streamer will try
    // to find the one embedded in the metadata.
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      // If the 720p input is correctly detected, it will encode 720p only.
      // If the detected resolution is too high, there will be multiple tracks.
      // If the detected resolution is too low, startStreamer() will fail
      // because there will be nothing to encode.
      'resolutions': [
        '4k',
        '1440p',
        '1080p',
        '720p',
      ],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);

    await player.load(manifestUrl);
    const trackList = player.getVariantTracks();
    expect(trackList.length).toBe(1);
  });

  // This is a regression test for content which has a smaller aspect ratio than
  // the defined resolutions.  We had a bug in which a fit by width would be
  // used even if the input height was over the resolution's maximum.  This test
  // defines custom resolutions with wider aspect ratio than the input.
  it('correctly buckets the input resolution of the video', async () => {
    // The resolution of this content is 1280x544.
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };

    const bitrateConfigDict = {
      video_resolutions: {
        too_small: {
          max_width: 1300,  // Big enough
          max_height: 480,  // Not big enough
          bitrates: {
            h264: '1M',
          },
        },
        big_enough: {
          max_width: 1500,  // Big enough
          max_height: 544,  // Just right
          bitrates: {
            h264: '1M',
          },
        },
        much_bigger: {
          max_width: 2000, // Bigger than input
          max_height: 700, // Bigger than input
          bitrates: {
            h264: '1M',
          },
        },
      }
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': [
        'too_small',
        'big_enough',
        'much_bigger',
      ],
    };

    await startStreamer(inputConfigDict, pipelineConfigDict, bitrateConfigDict);

    await player.load(manifestUrl);
    const trackList = player.getVariantTracks();

    // If the input is correctly detected as the higher resolution, this will
    // encode two tracks for 'too_small' and 'big_enough', but not 'much_bigger'
    // (which would be upscaled).  Before the detection bug was fixed, this
    // would be only one track ('too_small'), since 'big_enough' would have been
    // seen (incorrectly) as upscaling.
    expect(trackList.length).toBe(2);
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
          'language': 'zh',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': [],
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
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
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
      // Text inputs are currently only supported for VOD.
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
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
  it('has a vod streaming mode ' + format, async () => {
    const inputConfigDict = {
      // List of inputs. Each one is a dictionary.
      'inputs': [
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    expect(player.isLive()).toBe(false);
  });
}

function channelsTests(manifestUrl, channels, format) {
  it('outputs ' + channels + ' channels ' + format, async () => {
    const inputConfigDict = {
      // List of inputs. Each one is a dictionary.
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };

    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': [],
      'channels': channels,
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    const trackList = player.getVariantTracks();
    expect(trackList.length).toBe(1);
    expect(trackList[0].channelsCount).toBe(channels);
  });
}

function availabilityTests(manifestUrl, format) {
  it('outputs the correct availability window ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'input_type': 'looped_file',
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'live',
      'resolutions': ['144p'],
      'availability_window': 500,
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    const response = await fetch(manifestUrl);
    const bodyText = await response.text();
    const re = /timeShiftBufferDepth="([^"]*)"/;
    const found = bodyText.match(re);
    expect(found).not.toBe(null);
    if (found) {
      expect(found[1]).toBe('PT500S');
    }
  });
}

function delayTests(manifestUrl, format) {
  it('outputs the correct presentation delay ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'input_type': 'looped_file',
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'live',
      'resolutions': ['144p'],
      'presentation_delay': 100,
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    delay = player.getManifest().presentationTimeline.getDelay();
    expect(delay).toBe(100);
  });
}

function updateTests(manifestUrl, format) {
  it('outputs the correct update period ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'input_type': 'looped_file',
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'live',
      'resolutions': ['144p'],
      'update_period': 42,
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    const response = await fetch(manifestUrl);
    const bodyText = await response.text();
    const re = /minimumUpdatePeriod="([^"]*)"/;
    const found = bodyText.match(re);
    expect(found).not.toBe(null);
    if (found) {
      expect(found[1]).toBe('PT42S');
    }
  });
}

function durationTests(manifestUrl, format) {
  it('outputs the correct duration of video ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
           // The original clip is 10 seconds long.
          'start_time': '00:00:02',
          'end_time': '00:00:05',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);
    // We took from 2-5, so the output should be about 3 seconds long.
    expect(video.duration).toBeCloseTo(3, 1 /* decimal points to check */);
  });
}

function mapTests(manifestUrl, format) {
  it('maps the correct inputs to outputs ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        // The order of inputs here is sensitive.
        // This is a regression test for a bug in which all VOD outputs were
        // mapped to input file 0, so the order of inputs here is sensitive.
        // Input #0 has only one track (0 for video).  Input #1 has more tracks
        // (0 for video, 1 for audio, 2 for subs).  So we ask for input #1 track
        // 1, and the bug would have mapped non-existent input #0 track 1.
        {
          'name': TEST_DIR + 'BigBuckBunny.1080p.mp4',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    // The failure would happen at the ffmpeg level, so we can be sure now that
    // the bug is fixed.  But let's go further and expect a single track with
    // both audio and video.
    const trackList = player.getVariantTracks();
    expect(trackList.length).toBe(1);
    expect(trackList[0].videoCodec).not.toBe(null);
    expect(trackList[0].audioCodec).not.toBe(null);
  });
}

function filterTests(manifestUrl, format) {
  it('filters inputs ' + format, async() => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'video',
          'filters': [
            // Resample frames to 90fps, which we can later detect.
            'fps=fps=90',
          ],
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
        {
          'name': TEST_DIR + 'Sintel.2010.720p.Small.mkv',
          'media_type': 'audio',
          'filters': [
            // Resample audio to 88.2kHz, which we can later detect.
            'aresample=88200',
          ],
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getVariantTracks();
    expect(trackList.length).toBe(1);
    expect(trackList[0].frameRate).toBe(90);
    // TODO(joeyparrish): expose sampleRate through Shaka Player API
    //expect(trackList[0].sampleRate).toBe(88200);
  });
}

function customBitrateTests() {
  const minimalInputConfig = {
    inputs: [
      {
        name: TEST_DIR + 'BigBuckBunny.1080p.mp4',
        media_type: 'video',
      },
    ],
  };

  function getPipelineConfig(resolutions) {
    return {
      streaming_mode: 'vod',
      resolutions: resolutions,
    };
  }

  it('allows custom resolutions', async () => {
    const bitrateConfig = {
      video_resolutions: {
        wee: {
          max_width: 200,
          max_height: 100,
          bitrates: {
            h264: '10k',
            vp9: '5k',
          },
        },
        middlin: {
          max_width: 1920,
          max_height: 1080,
          bitrates: {
            h264: '1M',
            vp9: '500k',
          },
        },
        fhuge: {
          max_width: 8675309,
          max_height: 4390116,
          bitrates: {
            h264: '100M',
            vp9: '50M',
          },
        },
      },
    };

    const pipelineConfig = getPipelineConfig([
      'wee',
      'middlin',
      'fhuge',
    ]);

    await startStreamer(minimalInputConfig, pipelineConfig, bitrateConfig);
    await player.load(dashManifestUrl);

    const trackList = player.getVariantTracks();
    const heightList = trackList.map(track => track.height);
    heightList.sort((a, b) => a - b);
    // We expect 'wee' and 'middlin' to be used, but not 'fhuge', because it's
    // bigger than the input.
    expect(heightList).toEqual([100, 1080]);
  });

  it('rejects standard resolutions when redefined', async () => {
    const bitrateConfig = {
      video_resolutions: {
        foo: {
          max_width: 3000,
          max_height: 2000,
          bitrates: {
            h264: '4M',
            vp9: '2M',
          },
        },
      },
    };

    const pipelineConfig = getPipelineConfig([
      '1080p',
    ]);

    const start = startStreamer(
        minimalInputConfig, pipelineConfig, bitrateConfig);
    await expectAsync(start).toBeRejectedWith(jasmine.objectContaining({
      error_type: 'MalformedField',
      field_name: 'resolutions',
    }));
  });
}

function muxedTextTests(manifestUrl, format) {
  it('can extract text streams from muxed inputs ' + format, async () => {
    const inputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.with.subs.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
        {
          'name': TEST_DIR + 'Sintel.with.subs.mkv',
          'media_type': 'audio',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
        {
          'name': TEST_DIR + 'Sintel.with.subs.mkv',
          'media_type': 'text',
        },
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'audio_codecs': ['aac'],
      'video_codecs': ['h264'],
    };
    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    const trackList = player.getTextTracks();
    expect(trackList).toEqual([
      jasmine.objectContaining({
        'language': 'eo',  // Autodetected from the mkv input
      }),
    ]);
  });
}

function multiPeriodTests(manifestUrl, format) {
  it('can process multiperiod_inputs_list ' + format, async() => {
    const singleInputConfigDict = {
      'inputs': [
        {
          'name': TEST_DIR + 'Sintel.with.subs.mkv',
          'media_type': 'video',
          // Keep this test short by only encoding 1s of content.
          'end_time': '0:01',
        },
      ],
    };
    const inputConfigDict = {
      'multiperiod_inputs_list': [
        singleInputConfigDict,
        singleInputConfigDict,
      ],
    };
    const pipelineConfigDict = {
      'streaming_mode': 'vod',
      'resolutions': ['144p'],
      'audio_codecs': ['aac'],
      'video_codecs': ['h264'],
    };

    await startStreamer(inputConfigDict, pipelineConfigDict);
    await player.load(manifestUrl);

    // Since we processed only 0:01s, the total duration shoud be 2s.
    // Be more tolerant with float comparison, (D > 1.9 * length) instead of (D == 2 * length).
    expect(video.duration).toBeGreaterThan(1.9);
  });
}