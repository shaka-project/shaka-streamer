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
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import threading
import traceback
import urllib

from mypy import api as mypy_api
from streamer import node_base
from streamer.controller_node import ControllerNode
from streamer.configuration import ConfigError

OUTPUT_DIR = 'output_files/'
TEST_DIR = 'test_assets/'
CLOUD_TEST_ASSETS = (
    'https://storage.googleapis.com/shaka-streamer-assets/test-assets/')

# Turn down Flask's logging so that the console isn't flooded with messages
# about every request.  Because flask is built on top of another tool called
# "werkzeug", this the name we use to retrieve the log instance.
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Changes relative path to where this file is.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
controller = None

app = flask.Flask(__name__)
# Stops browser from caching files to prevent cross-test contamination.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

def cleanup():
  # If the controller is running, stop it.
  global controller
  if controller is not None:
    controller.stop()
  controller = None

  # If the output directory exists, delete it and make a new one.
  if os.path.exists(OUTPUT_DIR):
    shutil.rmtree(OUTPUT_DIR)
  os.mkdir(OUTPUT_DIR)

def createCrossOriginResponse(body=None, status=200, mimetype='text/plain'):
  # Enable CORS because karma and flask are cross-origin.
  resp = flask.Response(response=body, status=status)
  resp.headers.add('Content-Type', mimetype)
  resp.headers.add('Access-Control-Allow-Origin', '*')
  resp.headers.add('Access-Control-Allow-Methods', 'GET,POST')
  return resp

def dashStreamsReady(manifest_path):
  """Wait for DASH streams to be ready.

  Return True if the DASH manifest exists and each Representation has at least
  one segment in it.
  """

  # Check to see if the DASH manifest exists yet.
  if not os.path.exists(manifest_path):
    return False

  # Waiting until every Representation has a segment.
  pattern = re.compile(r'<Representation.*?((\n).*?)*?Representation>')
  with open(manifest_path) as manifest_file:
    for representation in pattern.finditer(manifest_file.read()):
      if not re.search(r'<S t', representation.group()):
        # This Representation has no segments.
        return False

  return True

def hlsStreamsReady(master_playlist_path):
  """Wait for HLS streams to be ready.

  Return True if the HLS master playlist exists, and all of the media playlists
  referenced by it exist, and each of those media playlists have at least one
  segment in it.
  """

  # Check to see if the HLS master playlist exists yet.
  if not os.path.exists(master_playlist_path):
    return False

  # Parsing master playlist to see how many media playlists there are.
  # Do this every time, since the master playlist contents may change.
  with open(master_playlist_path) as hls_file:
    contents = hls_file.read()
    media_playlist_list = re.findall(r'^.*\.m3u8$', contents, re.MULTILINE)
    media_playlist_count = len(media_playlist_list)

  # See how many playlists exist so far.
  playlist_list = glob.glob(OUTPUT_DIR + '*.m3u8')

  # Return False if we don't have the right number.  The +1 accounts for the
  # master playlist.
  if len(playlist_list) != media_playlist_count + 1:
    return False

  for playlist_path in playlist_list:
    if playlist_path == master_playlist_path:
      # Skip the master playlist
      continue

    with open(playlist_path) as playlist_file:
      if '#EXTINF' not in playlist_file.read():
        # This doesn't have segments yet.
        return False

  return True

@app.route('/start', methods = ['POST'])
def start():
  global controller
  if controller is not None:
    return createCrossOriginResponse(
        status=403, body='Instance already running!')
  cleanup()

  # Receives configs from the tests to start Shaka Streamer.
  try:
    configs = json.loads(flask.request.data)
  except Exception as e:
    return createCrossOriginResponse(status=400, body=str(e))

  # Enforce quiet mode without needing it specified in every test.
  configs['pipeline_config']['quiet'] = True

  controller = ControllerNode()
  try:
    controller.start(OUTPUT_DIR,
                     configs['input_config'],
                     configs['pipeline_config'],
                     configs['bitrate_config'],
                     check_deps=False)
  except Exception as e:
    # If the controller throws an exception during startup, we want to call
    # stop() to shut down any external processes that have already been started.
    controller.stop()
    controller = None

    # Then, fail the request with a message that indicates what the error was.
    if isinstance(e, ConfigError):
      body = json.dumps({
        'error_type': type(e).__name__,
        'class_name': e.class_name,
        'field_name': e.field_name,
        'field_type': e.field.get_type_name(),
        'message': str(e),
      })
      return createCrossOriginResponse(
          status=418, mimetype='application/json', body=body)
    else:
      traceback.print_exc()
      return createCrossOriginResponse(status=500, body=str(e))

  return createCrossOriginResponse()

@app.route('/stop')
def stop():
  global controller
  resp = createCrossOriginResponse()
  if controller is not None:
    # Check status to see if one of the processes exited.
    if controller.check_status() == node_base.ProcessStatus.Errored:
      resp = createCrossOriginResponse(
          status=500, body='Some processes exited with non-zero exit codes')

  cleanup()
  return resp

@app.route('/output_files/<path:filename>', methods = ['GET', 'OPTIONS'])
def send_file(filename):
  if not controller:
    return createCrossOriginResponse(
        status=403, body='Instance already shut down!')
  elif controller.is_vod():
    # If streaming mode is vod, needs to wait until packager is completely
    # done packaging contents.
    while True:
      status = controller.check_status()
      if status == node_base.ProcessStatus.Finished:
        break
      elif status != node_base.ProcessStatus.Running:
        return createCrossOriginResponse(
            status=500, body='Some processes exited with non-zero exit codes')

      time.sleep(1)
  else:
    # If streaming mode is live, needs to wait for specific content in
    # manifest until it can be loaded by the player.
    if filename.endswith('.mpd'):
      while not dashStreamsReady(OUTPUT_DIR + filename):
        time.sleep(1)
    elif filename.endswith('.m3u8') and not filename.startswith('stream_'):
      while not hlsStreamsReady(OUTPUT_DIR + filename):
        time.sleep(1)

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
      'Sintel.with.subs.mkv',
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

  # Do static type checking on the project first.
  type_check_result = mypy_api.run(['streamer/'])
  if type_check_result[2] != 0:
    print('The type checker found the following errors: ')
    print(type_check_result[0])
    return 1

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
  cleanup()
  return fails

if __name__ == '__main__':
  # Exit code based on test results from subprocess call.
  sys.exit(main())
