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

import abc
import enum
import re

from . import metadata


def enum_from_keys(name, dictionary):
  """Create an enum dynamically from the keys of a dictionary.

  Used to create enums for config validation based on the hard-coded resolution
  settings in the |metadata| module.
  """

  # This is the functional API of the enum module, which is documented here:
  # https://docs.python.org/3/library/enum.html#functional-api

  # Here the keys match the values, unless the key starts with a numeral.
  # Keys starting with numbers would be unusable as enum keys in Python (for
  # example, "480p").  So these will be prefixed with an underscore.
  enum_keys_and_values = []
  for key in dictionary:
    if key[0] >= '0' and key[0] <= '9':
      enum_keys_and_values.append(('_' + key, key))
    else:
      enum_keys_and_values.append((key, key))

  return enum.Enum(name, enum_keys_and_values)


class ConfigError(Exception):
  """A base class for config errors.

  Each subclass provides a meaningful, human-readable string representation in
  English.
  """

  def __init__(self, class_ref, field_name, field):
    self.class_ref = class_ref
    """A reference to the config class that the error refers to."""

    self.class_name = class_ref.__name__
    """The name of the config class that the error refers to."""

    self.field_name = field_name
    """The name of the field that the error refers to."""

    self.field = field
    """The Field metadata object that the error refers to."""


class UnrecognizedField(ConfigError):
  """An error raised when an unrecognized field is encountered in the input."""

  def __str__(self):
    return '{} contains unrecognized field: {}'.format(
        self.class_name, self.field_name)

class WrongType(ConfigError):
  """An error raised when a field in the input has the wrong type."""

  def __str__(self):
    return 'In {}, {} field requires a {}'.format(
        self.class_name, self.field_name, self.field.get_type_name())

class MissingRequiredField(ConfigError):
  """An error raised when a required field is missing from the input."""

  def __str__(self):
    return '{} is missing a required field: {}, a {}'.format(
        self.class_name, self.field_name, self.field.get_type_name())

class MalformedField(ConfigError):
  """An error raised when a field is malformed."""

  def __init__(self, class_ref, field_name, field, reason):
    super().__init__(class_ref, field_name, field)
    self.reason = reason

  def __str__(self):
    return 'In {}, {} field is malformed: {}'.format(
        self.class_name, self.field_name, self.reason)


class ValidatingType(object):
  """A base wrapper type that validates the input against a limited range.

  Subclasses of this are handled specially by the config system, but this is
  not a real class type that can be constructed.

  Subclasses must implement a static validate() method that takes a value and
  raises TypeError if the input type is wrong or ValueError if it fails
  validation.

  Subclasses must define a "name" attribute with a human-readable name for the
  type.
  """

  @abc.abstractmethod
  def __init__(self):
    pass


class HexString(ValidatingType):
  """A wrapper that can be used in Field() to require a hex string."""

  name = 'hexadecimal string'

  @staticmethod
  def validate(value):
    if type(value) is not str:
      raise TypeError()
    if not re.match(r'^[a-fA-F0-9]+$', value):
      raise ValueError('not a hexadecimal string')


class Field(object):
  """A container for metadata about individual config fields."""

  def __init__(self, type, required=False, subtype=None, default=None):
    """
    Args:
        type (class): The required type for values of this field.
        required (bool): True if this field is required on input.
        subtype (class): The required type inside lists (type=list).
        default: The default value if the field is not specified.
    """
    self.type = type
    self.required = required
    self.subtype = subtype
    self.default = default

  def get_type_name(self):
    """Get a human-readable string for the name of self.type."""
    return Field.get_type_name_static(self.type, self.subtype)

  @staticmethod
  def get_type_name_static(type, subtype):
    """Get a human-readable string for the name of type."""

    # Make these special cases a little more readable.
    if type is str:
      # Call it a string, not a "str".
      return 'string'
    elif type is list:
      # Mention the subtype.
      return 'list of {}'.format(Field.get_type_name_static(subtype, None))
    elif type is None:
      # This is only here to allow generic handling of UnrecognizedField errors.
      return 'None'
    elif issubclass(type, enum.Enum):
      # Get the list of valid options as quoted strings.
      options = [repr(str(member.value)) for member in type]
      return '{} (one of {})'.format(type.__name__, ', '.join(options))
    elif issubclass(type, ValidatingType):
      return type.name

    # Otherwise, return the name of the type.
    return type.__name__


class Base(object):
  """A base class for config objects.

  This will handle all validation, type-checking, defaults, and extraction of
  values from an input dictionary.

  Subclasses must define class-level Field objects defining their fields.
  The base class does the rest.
  """

  def __init__(self, dictionary):
    """Ingests, type-checks, and validates the input dictionary."""

    # Collect all the config fields for this type.
    config_fields = {}
    for key, field in self.__class__.__dict__.items():
      if isinstance(field, Field):
        config_fields[key] = field

    for key, value in dictionary.items():
      field = config_fields.get(key)

      # Look for unrecognized fields in the input.
      if not field:
        raise UnrecognizedField(self.__class__, key, Field(None))

      # Check types on recognized fields.
      value = self._check_and_convert_type(field, key, value)

      # Assign the value to self.
      setattr(self, key, value)

    # Look for missing fields.
    for key, field in config_fields.items():
      if not key in dictionary:
        # If it's required, raise an error.
        if field.required:
          raise MissingRequiredField(self.__class__, key, field)

        # Otherwise, assign a default.
        setattr(self, key, field.default)

  def _check_and_convert_type(self, field, key, value):
    """Check the type of |value| and convert it as necessary.

    Args:
        field (Field): The field definition.
        key (str): The name of the field.
        value: The value to be checked and converted.

    This checks the type of |value| according to |field| and performs any
    necessary conversions to the target type.  This is where any type-specific
    logic or special cases are handled.

    Note that automatic type coercion is avoided.  We wouldn't want a string
    containing the word "False" coerced to boolean True.
    """

    # For fields containing other config objects, specially check and convert
    # them.
    if issubclass(field.type, Base):
      # A config object at this stage should be a dictionary.
      if not isinstance(value, dict):
        raise WrongType(self.__class__, key, field)

      # Let the type of the sub-object validate its contents.
      sub_object = field.type(value)

      # Return this typed object, which will be assigned to self.
      return sub_object

    # For lists, check the type of the value itself, then check the subtype of
    # the list items.
    if field.type is list:
      if not isinstance(value, list):
        raise WrongType(self.__class__, key, field)

      subfield = Field(field.subtype)
      try:
        return [self._check_and_convert_type(subfield, key, v) for v in value]
      except WrongType as e:
        # If conversion raises WrongType on the subfield, raise a WrongType
        # error on this field instead.  For any other error, just re-raise.  If
        # conversion succeeds, replace the original item with the converted
        # one.
        if e.field == subfield:
          raise WrongType(self.__class__, key, field) from None
        else:
          raise

      return value

    # For enums, try to cast the value to the enum type, and raise a WrongType
    # error if this fails.
    if issubclass(field.type, enum.Enum):
      try:
        return field.type(value)
      except ValueError:
        raise WrongType(self.__class__, key, field) from None

    # A float should be permissive and accept an int, as well.
    if field.type is float:
      if not isinstance(value, float) and not isinstance(value, int):
        raise WrongType(self.__class__, key, field)
      return value

    # These aren't true types, but validation classes for specific types of
    # limited input.  Run the validate() method to check the input.
    if issubclass(field.type, ValidatingType):
      try:
        field.type.validate(value)
      except TypeError:
        raise WrongType(self.__class__, key, field)
      except ValueError as e:
        raise MalformedField(self.__class__, key, field, str(e))
      return value

    # For all other types, just do a basic type check and return the original
    # value.
    if not isinstance(value, field.type):
      raise WrongType(self.__class__, key, field)
    return value

