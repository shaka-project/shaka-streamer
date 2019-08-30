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

"""A module that validates the config file.
It also fills in default values in empty fields."""

def _assert_valid_keys(user_config, default_config):
  """Checks if user config keys are valid

  Raises:
    KeyError: If user_config key does not exist in default_config.
  """
  invalid_config = set(user_config.keys()) - set(default_config.keys())
  if invalid_config:
    invalid_args = ', '.join(invalid_config)
    raise KeyError(
        "These are unrecognized field(s) in your config: {}".format(
            invalid_args))

def _assert_valid_type(user_value, default_val, key):
  """Type checks user config to defaults.

  Raises:
    TypeError: If user_value type is different from the default_value type.
  """
  config_type = type(user_value)
  default_type = type(default_val)

  if config_type is int and default_type is float:
    config_type = float

  if config_type is not default_type:
    raise TypeError(
        "The field '{}' has a {} value when it should be a {}".format(
            key,
            config_type,
            default_type))

def _assert_valid_value(user_value, valid_values, key):
  if key in valid_values:
    valid_set = valid_values[key]
    # Value checking every item in the user config list is valid.
    if type(user_value) is list and set(user_value) - valid_set:
      raise ValueError(
          "The field '{}' has a value {} which is not one of {}".format(
              key,
              set(user_value) - valid_set,
              valid_set))
    # Value checking user config item is valid.
    elif type(user_value) is not list and user_value not in valid_set:
      raise ValueError(
          "The field '{}' has a value {} which is not one of {}".format(
              key,
              user_value,
              valid_set))

def _set_defaults(user_config, default_key, default_val):
  """Sets the user config to default if value not set.

  Args:
    user_config: A dict containing the passed config values.
    default_key: The key from the default_config.
    default_val: The value corresponding to the default_key in default_config.
  Returns:
    A boolean saying if a default value was set or not.
    Modifies user_config if default key not found in user_config yet.
  """
  if default_key not in user_config.keys():
    user_config[default_key] = default_val
    return True
  return False

def setup_config(user_config, default_config, valid_values):
  """Validates a given config dict then combines with defaults.

  Args:
    user_config: A dict containing the passed config values.
    default_config: A dict containing default config values.

  Returns:
    Nothing.  It modifies the user_config it is given.
  """
  _assert_valid_keys(user_config, default_config)

  # I am going to iterate over the defaults to change the user config instead.
  # Although it will be not as clean as .update(config), I think it will be
  # better to have a read-only dict since .update(config) modifies the default.
  for key, default_val in default_config.items():
    if _set_defaults(user_config, key, default_val):
      continue

    _assert_valid_type(user_config[key], default_val, key)
    _assert_valid_value(user_config[key], valid_values, key)

    if type(user_config[key]) is list:
      # If a configuration is an empty list, set it to equal the list in the
      # default configuration.
      if not user_config[key]:
        user_config[key] = default_val

      for user_val in user_config[key]:
        _assert_valid_type(user_val, default_val[0], key)
        if type(user_val) is dict:
          for key in user_val:
            _assert_valid_type(user_val[key], default_val[0][key], key)
            _assert_valid_value(user_val[key], valid_values, key)

    if type(default_val) is dict:
      setup_config(user_config[key], default_val, valid_values)
