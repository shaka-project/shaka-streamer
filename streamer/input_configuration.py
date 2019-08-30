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

from . import default_config
from . import validation

INPUTS = 'inputs'

class InputConfig():

  def __init__(self, user_config,
               default_config = default_config.INPUT_DEFAULT_CONFIG,
               valid_values = default_config.INPUT_VALID_VALUES):
    validation.setup_config(user_config, default_config, valid_values)
    self.dict = user_config
    self.inputs = [Input(i) for i in self.dict[INPUTS]]

class Input():

  def __init__(self, input):
    self._input = input

  def get_name(self):
    return self._input['name']

  def get_input_type(self):
    if 'input_type' in self._input:
      return self._input['input_type']
    return None

  def get_media_type(self):
    return self._input['media_type']

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

  def has_video(self):
    if 'input_type' in self._input:
      if (self._input['input_type'] == 'webcam' or
          self._input['input_type'] == 'raw_images'):
        return True
    if 'media_type' in self._input:
      if self._input['media_type'] == 'video':
        return True
    return False

  def has_audio(self):
    if 'media_type' in self._input:
      if self._input['media_type'] == 'audio':
        return True
    return False

  def has_text(self):
    if 'media_type' in self._input:
      if self._input['media_type'] == 'text':
        return True
    return False

  def check_text_entry(self):
    if 'language' not in self._input:
      raise RuntimeError('language must be specified for text track')

  def check_input_entry(self):
    if 'name' not in self._input:
      raise RuntimeError('name field must be in dictionary entry!')
    elif 'media_type' not in self._input:
      if (self._input['input_type'] != 'webcam' and
          self._input['input_type'] != 'raw_images'):
        raise RuntimeError('media_type field must be in dictionary entry!')

  def check_video_entry(self):
    if 'frame_rate' not in self._input:
      raise RuntimeError('frame_rate field must be in video dictionary entry!')
    elif 'resolution' not in self._input:
      raise RuntimeError('resolution field must be in video dictionary entry!')

  def check_live_validity(self):
    if self.has_text():
      self.check_text_entry()
      return
    if self.has_video():
      self.check_video_entry()
    self.check_input_entry()
    if 'input_type' not in self._input:
      raise RuntimeError('input_type field must be in dictionary entry!')

  def check_vod_validity(self):
    if self.has_text():
      self.check_text_entry()
      return
    if self.has_video():
      self.check_video_entry()
    self.check_input_entry()
    if 'track_num' not in self._input:
      raise RuntimeError('track_num field must be in dictionary entry!')

