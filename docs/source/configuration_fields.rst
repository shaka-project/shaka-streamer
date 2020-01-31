..
  Copyright 2019 Google LLC

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.


Configuration Field Reference
=============================

There are two config files required by Shaka Streamer: one to describe the
inputs, and one to describe the encoding pipeline.  Through the module API,
these are taken as dictionaries.  Through the command-line front-end, these are
parsed as `YAML files <https://gettaurus.org/docs/YAMLTutorial/>`_.

*(If you aren't familiar with YAML, it fills many of the same roles as JSON,
except that it's more readable and can contain comments.)*

If you are just getting started with Shaka Streamer, you should probably look in
the `config_files/`_ folder and browse through some examples.  If you are trying
to customize one of those examples or get more details on supported options,
this document is for you.

.. _config_files/: https://github.com/google/shaka-streamer/tree/master/config_files


Input Configs
-------------

The input config describes the inputs.  In general, each needs to have an input
type (such as a looped file), a media type (such as video), and a name (such as
a file path).  Other fields may be required for certain types.

An input config is generally composed of multiple inputs, such as one high-res
video, one audio input per language, and possibly some subtitle or caption
files.

..
  Sphinx wants to sort these, but we should put the top-level config structures
  first, then the others.
.. autoclass:: streamer.input_configuration.InputConfig
.. autoclass:: streamer.input_configuration.Input
.. automodule:: streamer.input_configuration
  :exclude-members: InputConfig, Input


Pipeline Configs
----------------

The pipeline config describes the encoding pipeline.  The only required
parameters are the streaming mode (live or VOD) and the resolutions.
Everything else has default values, but you may want to customize the codecs,
resolutions, availability window, and/or encryption settings.

..
  Sphinx wants to sort these, but we should put the top-level config structure
  first, then the others.
.. autoclass:: streamer.pipeline_configuration.PipelineConfig
.. automodule:: streamer.pipeline_configuration
  :exclude-members: PipelineConfig


Custom Bitrate and Resolution Configs
-------------------------------------

To customize bitrates or resolution, you may provide a third config file
defining these.  If this config is given, it replaces the default definitions.

..
  Sphinx wants to sort these, but we should put the top-level config structure
  first, then the others.
.. autoclass:: streamer.bitrate_configuration.BitrateConfig
.. automodule:: streamer.bitrate_configuration
  :exclude-members: BitrateConfig, BitrateString, VideoResolutionName,
                    get_value, keys, set_map, sorted_values
