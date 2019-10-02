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

"""A module that organizes the pipeline config."""

from . import default_config
from . import validation

MODE = 'streaming_mode'
QUIET = 'quiet'
TRANSCODER = 'transcoder'
PACKAGER = 'packager'
ENCRYPTION = 'encryption'

class PipelineConfig():

  def __init__(self, user_config,
               default_config = default_config.OUTPUT_DEFAULT_CONFIG,
               valid_values = default_config.OUTPUT_VALID_VALUES):
    validation.setup_config(user_config, default_config, valid_values)
    self.dict = user_config
    self.mode = self.dict[MODE]
    self.quiet = self.dict[QUIET]
    self.transcoder = self.dict[TRANSCODER]
    self.packager = self.dict[PACKAGER]
    self.encryption = self.packager[ENCRYPTION]
