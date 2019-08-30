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

/** @param {!Object} config */
module.exports = function(config) {
  config.set({
    basePath: __dirname,
    browserNoActivityTimeout: 5 * 60 * 1000, // Disconnect after 5m silence
    client: {
      captureConsole: true,
    },
    frameworks: ['jasmine'],
    files: [
      // Shaka Player
      '../node_modules/shaka-player/dist/shaka-player.compiled.js',

      // End to end tests
      'tests.js',
    ],
  });
};
