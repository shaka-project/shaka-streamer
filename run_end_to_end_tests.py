#!/usr/bin/env python3
#
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import flask
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import threading
import urllib

from streamer.controller_node import ControllerNode

OUTPUT_DIR = 'output_files/'
TEST_DIR = 'test_assets/'
CLOUD_TEST_ASSETS = (
    'https://storage.googleapis.com/shaka-streamer-assets/test-assets/')

# Changes relative path to where this file is.
os.chdir(os.path.dirname(__file__))
controller = None

app = flask.Flask(__name__, static_folder=OUTPUT_DIR)
# Stops browser from caching files to prevent cross-test contamination.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

def cleanupFiles():
  # Check if the directory for outputted Packager files exists, and if it
  # does, delete it and remake a new one.
  if os.path.exists(OUTPUT_DIR):
    shutil.rmtree(OUTPUT_DIR)
  os.mkdir(OUTPUT_DIR)

def hasSegment(representation):
  return re.search('<S t', representation.group())

def createCrossOriginResponse(body=None, status=200):
  # Enable CORS because karma and flask are cross-origin.
  resp = flask.Response(response=body, status=status)
  resp.headers.add('Access-Control-Allow-Origin', '*')
  resp.headers.add('Access-Control-Allow-Methods', 'GET,POST')
  return resp

def waitDashManifest(dash_path):
  # Does not read manifest until it is created.
  while not os.path.exists(dash_path):
    time.sleep(1)

  # Waiting until every resolution has an initial segment,
  # so the manifest can be loaded properly.
  missing_segment = True
  pattern = re.compile('<Representation.*?((\n).*?)*?Representation>')
  while missing_segment:
    time.sleep(1)
    with open(dash_path) as dash_file:
      missing_segment = False
      for representation in pattern.finditer(dash_file.read()):
        if not hasSegment(representation):
          missing_segment = True

def hlsReadyStreamCount(stream_list):
  init_count = 0
  for stream_path in stream_list:
    with open(stream_path) as stream_file:
      if '#EXTINF' in stream_file.read():
        init_count += 1
  return init_count

def waitHlsManifest(hls_path):
  # Does not read manifest until it is created.
  while not os.path.exists(hls_path):
    time.sleep(1)

  # Parsing master playlist to see how many streams there are.
  stream_pattern = re.compile('stream_\d+\.m3u8')
  with open(hls_path) as hls_file:
    stream_count = len(set(stream_pattern.findall(hls_file.read())))

  # Waiting until the correct number of streams exist.
  stream_path_glob = OUTPUT_DIR + 'stream_*.m3u8'
  while len(glob.glob(stream_path_glob)) != stream_count:
    time.sleep(1)

  # Waiting until each stream has enough segments.
  stream_list = glob.glob(stream_path_glob)
  while hlsReadyStreamCount(stream_list) != stream_count:
    time.sleep(1)

@app.route('/start', methods = ['POST'])
def start():
  global controller
  if controller is not None:
    return createCrossOriginResponse(
        status=403, body='Instance already running!')
  cleanupFiles()

  # Receives configs from the tests to start Shaka Streamer.
  configs = json.loads(flask.request.data)

  controller = ControllerNode()
  try:
    controller.start(OUTPUT_DIR, configs['input_config'],
                     configs['pipeline_config'])
  except:
    # If the controller throws an exception during startup, we want to call
    # stop() to shut down any external processes that have already been started.
    # Then, re-raise the exception.
    controller.stop()
    raise

  return createCrossOriginResponse()

@app.route('/stop')
def stop():
  global controller
  if controller is not None:
    controller.stop()
  controller = None
  cleanupFiles()
  return createCrossOriginResponse()

@app.route('/output_files/<path:filename>', methods = ['GET','OPTIONS'])
def send_file(filename):
  if controller.is_vod():
    # If streaming mode is vod, needs to wait until packager is completely
    # done packaging contents.
    while controller.is_running():
      time.sleep(1)
  else:
    # If streaming mode is live, needs to wait for specific content in
    # manifest until it can be loaded by the player.
    if filename == 'output.mpd':
      waitDashManifest(OUTPUT_DIR + 'output.mpd')
    elif filename == 'master_playlist.m3u8':
      waitHlsManifest(OUTPUT_DIR + 'master_playlist.m3u8')

  # Sending over requested files.
  try:
    response = flask.send_file(OUTPUT_DIR + filename);
  except FileNotFoundError:
    response = flask.Response(response='File not found', status=404)

  response.headers.add('Access-Control-Allow-Origin', '*')
  response.headers.add('Access-Control-Allow-Headers', 'RANGE')
  return response

def fetch_cloud_assets():
  file_list = [
      'BigBuckBunny.1080p.mp4',
      'Sintel.2010.720p.Small.mkv',
      'Sintel.2010.Arabic.vtt',
      'Sintel.2010.Chinese.vtt',
      'Sintel.2010.English.vtt',
      'Sintel.2010.Esperanto.vtt',
      'Sintel.2010.French.vtt',
      'Sintel.2010.Spanish.vtt',
  ]

  # Downloading all the assests for tests.
  for file in file_list:
    if not os.path.exists(TEST_DIR + file):
      response = urllib.request.urlretrieve(CLOUD_TEST_ASSETS +
                                            file,
                                            TEST_DIR + file)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--runs', default=1, type=int,
                      help='Number of trials to run')
  parser.add_argument('--reporters', nargs='+',
                      help='Enables specified reporters in karma')
  args = parser.parse_args()

  # Install test dependencies.
  subprocess.check_call(['npm', 'install'])

  # Fetch streams used in tests.
  if not os.path.exists(TEST_DIR):
    os.mkdir(TEST_DIR)

  fetch_cloud_assets()

  # Start up flask server on a thread.
  # Daemon is set to True so that this thread automatically gets
  # killed when exiting main.  Flask does not have any clean alternatives
  # to be killed.
  threading.Thread(target=app.run, daemon=True).start()

  fails = 0
  trials = args.runs
  print('Running', trials, 'trials')
  # Start up karma.
  for i in range(trials):
    # Start up karma.
    karma_args = [
        'node_modules/karma/bin/karma',
        'start',
        'tests/karma.conf.js',
        # DRM currently is not compatible with headless, so it's run in Chrome.
        # Linux: If you want to run tests as "headless", wrap it with "xvfb-run -a".
        '--browsers', 'Chrome',
        '--single-run',
      ]

    if args.reporters:
      converted_string = ','.join(args.reporters)
      karma_args += [
          '--reporters',
          converted_string,
      ]
    # If the exit code was not 0, the tests in karma failed or crashed.
    if subprocess.call(karma_args) != 0:
      fails += 1

  print('\n\nNumber of failures:', fails, '\nNumber of trials:', trials)
  print('\nSuccess rate:', 100 * (trials - fails) / trials, '%')
  return fails

if __name__ == '__main__':
  # Exit code based on test results from subprocess call.
  sys.exit(main())
