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

"""A module that organizes the input configs."""

import shlex

from . import default_config
from . import validation

INPUTS = 'inputs'

class InputConfig(object):

  def __init__(self, user_config,
               default_config = default_config.INPUT_DEFAULT_CONFIG,
               valid_values = default_config.INPUT_VALID_VALUES):
    validation.setup_config(user_config, default_config, valid_values)
    self.dict = user_config
    self.inputs = [Input(i) for i in self.dict[INPUTS]]

class Input(object):

  def __init__(self, input):
    self._input = input

  def get_name(self):
    self.check_name()
    return self._input['name']

  def get_input_type(self):
    if 'input_type' not in self._input:
      return None
    return self._input['input_type']

  def get_media_type(self):
    if 'media_type' not in self._input:
      raise RuntimeError('media type must be specified for all inputs')
    return self._input['media_type']

  def get_extra_input_args(self):
    # shlex understands the rules of quoting and separating command-lines into
    # arguments, so the user can specify a simple string in the config file,
    # and we can split it into an argument array.  Note that splitting an empty
    # string in shlex results in an empty array.
    return shlex.split(self._input.get('extra_input_args', ''))

  def get_frame_rate(self):
    return self._input['frame_rate']

  def get_resolution(self):
    return self._input['resolution']

  def get_track(self):
    if 'track_num' in self._input:
      return self._input['track_num']
    return 0

  def get_interlaced(self):
    if 'is_interlaced' in self._input:
      return self._input['is_interlaced']
    return False

  def get_language(self):
    if 'language' in self._input:
      return self._input['language']
    return None

  def get_start_time(self):
    if 'start_time' in self._input:
      return self._input['start_time']
    return None

  def get_end_time(self):
    if 'end_time' in self._input:
      return self._input['end_time']
    return None

  def get_filters(self):
    return self._input.get('filters', [])

  def check_entry(self):
    self.check_name()
    if self.get_media_type() == 'video':
      self.check_video_entry()

  def check_name(self):
    if 'name' not in self._input:
      raise RuntimeError('name field must be in dictionary entry!')

  def check_video_entry(self):
    if 'frame_rate' not in self._input:
      raise RuntimeError('frame_rate field must be in video dictionary entry!')
    if 'resolution' not in self._input:
      raise RuntimeError('resolution field must be in video dictionary entry!')

  def check_input_type(self):
    if 'input_type' not in self._input:
      raise RuntimeError('input_type field must be in dictionary entry!')
