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
import functools
import re

import typing
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
from typing import Generic, TypeVar, cast


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

class ConflictingFields(ConfigError):
  """An error raised when multiple fields are given and only one of them is allowed at a time."""
  
  def __init__(self, class_ref, field1_name, field2_name):
    self.field1_name = field1_name
    self.field1_type = class_ref.__dict__[field1_name].get_type_name()
    self.field2_name = field2_name
    self.field2_type = class_ref.__dict__[field2_name].get_type_name()
    super().__init__(class_ref, field1_name, class_ref.__dict__[field1_name])
  
  def __str__(self):
    return """In {}, these fields are conflicting:
    {} a {}
    and
    {} a {}\n  consider using only one of them.""".format(self.class_name,
                      self.field1_name, self.field1_type,
                      self.field2_name, self.field2_type)
    
class MissingRequiredExclusiveFields(ConfigError):
  """An error raised when one of an exclusively required fields is missing."""
  
  def __init__(self, class_ref, field1_name, field2_name):
    self.field1_name = field1_name
    self.field1_type = class_ref.__dict__[field1_name].get_type_name()
    self.field2_name = field2_name
    self.field2_type = class_ref.__dict__[field2_name].get_type_name()
    super().__init__(class_ref, field1_name, class_ref.__dict__[field1_name])
  
  def __str__(self):
    return """{} is missing a required field. Use exactly one of these fields:
    {} a {}
    or
    {} a {}""".format(self.class_name, self.field1_name, self.field1_type,
                      self.field2_name, self.field2_type)

class ValidatingType(metaclass=abc.ABCMeta):
  """A base wrapper type that validates the input against a limited range.

  Subclasses of this are handled specially by the config system, but this is
  not a real class type that can be constructed.

  Subclasses must implement a static validate() method that takes a value and
  raises TypeError if the input type is wrong or ValueError if it fails
  validation.

  Subclasses must define a "name" attribute with a human-readable name for the
  type.
  """

  @staticmethod
  @abc.abstractmethod
  def validate(value: str) -> None:
    pass

  @staticmethod
  @abc.abstractmethod
  def name() -> str:
    pass


class HexString(ValidatingType, str):
  """A wrapper that can be used in Field() to require a hex string."""

  @staticmethod
  def name() -> str:
    return 'hexadecimal string'

  @staticmethod
  def validate(value):
    if type(value) is not str:
      raise TypeError()
    if not re.match(r'^[a-fA-F0-9]+$', value):
      raise ValueError('not a hexadecimal string')


# A type parameter used by the Generic Field below.
# For example, for a Field with type=str, FieldType would be a string type and
# Type[FieldType] would be the function "str".
FieldType = TypeVar('FieldType')

class Field(Generic[FieldType]):
  # TODO: This class is populated with actual configuration
  # info at runtime. The correctness of the type/value pairs
  # is checked by Base._check_and_convert_type().

  """A container for metadata about individual config fields."""

  def __init__(self,
               type: Optional[Type[FieldType]],
               required: bool = False,
               default: Optional[FieldType] = None) -> None:
    """
    Args:
        type (class or typing module hint): The required type for values of this
            field.
        required (bool): True if this field is required on input.
        default: The default value if the field is not specified.
    """
    subtypes = Field.get_subtypes(type)  # keytype, subtype

    self.type: Optional[Type] = Field.get_underlying_type(type)
    self.keytype: Optional[Type] = subtypes[0]
    self.subtype: Optional[Type] = subtypes[1]
    self.required: bool = required
    self.default: Optional[FieldType] = default

  def get_type_name(self) -> str:
    """Get a human-readable string for the name of self.type."""
    return Field.get_type_name_static(self.type, self.keytype, self.subtype)

  def cast(self) -> FieldType:
    """Called on every Field instance where it is assigned to a configuration
    class property.  For example:

    class FooConfig(configuration.Base):
      name = configuration.Field(type=str, default="Susan").cast()

    At the class level, configuration fields are all Field instances.  At the
    instance level, the configuration Base class constructor sets all the fields
    to the appropriate config value, whose type is the type parameter FieldType.
    In our example above, the "name" Field from the class-level is replaced by a
    string at the instance level.

    Without this cast() method, mypy would be confused, because it would not see
    the metaprogramming that goes on the Base class constructor.  It would think
    that all configuration instances have properties of type "Field".

    To help mypy understand the type of the instance properties without changing
    the class-level property, this cast() method returns "self", but with the
    type info changed to FieldType for mypy's sake.

    In the example above, mypy knows that "name" is not just a Field, but a
    Field[str], based on the "type=str" parameter in the Field constructor.  It
    uses the type parameter FieldType ("str" in this example) to see that cast()
    returns the type "str".

    This allows the metaprogramming approach we take to configuration to remain
    compatible with mypy's static analysis."""
    return cast(FieldType, self)

  @staticmethod
  def get_underlying_type(type: Optional[Type]) -> Optional[Type]:
    """Get the underlying type from a typing module type hint."""

    # In Python 3.8+, you can use typing.get_origin.  It returns None if "type"
    # is something like "str" or "int" instead of "typing.List" or
    # "typing.Dict", so fall back to type itself.
    if hasattr(typing, 'get_origin'):
      return typing.get_origin(type) or type  # type: ignore

    # Before Python 3.8, you can use this undocumented attribute to get the
    # original type.  If this doesn't exist, you are probably dealing with a
    # basic type like "str" or "int".
    if hasattr(type, '__origin__'):
      return type.__origin__ or type  # type: ignore

    return type

  @staticmethod
  def get_subtypes(
      type: Optional[Type]) -> Tuple[Optional[Type], Optional[Type]]:
    """For Dict hints, returns (keytype, valuetype).

    For List hints, returns (None, valuetype).

    For everything else, returns (None, None)."""

    # In Python 3.8+, you can use typing.get_args.  It returns () if "type"
    # is something like "str" or "int" instead of "typing.List" or
    # "typing.Dict".
    if hasattr(typing, 'get_args'):
      args = typing.get_args(type)  # type: ignore
    elif hasattr(type, '__args__'):
      # Before Python 3.8, you can use this undocumented attribute to get the
      # type parameters.  If this doesn't exist, you are probably dealing with a
      # basic type like "str" or "int".
      args = getattr(type, '__args__')
    else:
      args = ()

    underlying = Field.get_underlying_type(type)
    if underlying in [dict, Dict]:
      return cast(Tuple[Optional[Type], Optional[Type]], args)
    if underlying in [list, List]:
      return (None, args[0])
    return (None, None)

  @staticmethod
  def get_type_name_static(type: Optional[Type],
                           keytype: Optional[Type],
                           subtype: Optional[Type]) -> str:
    """Get a human-readable string for the name of type."""

    # Make these special cases a little more readable.
    if type is str:
      # Call it a string, not a "str".
      return 'string'
    elif type in [list, List]:
      # Mention the subtype.
      return 'list of {}'.format(
          Field.get_type_name_static(subtype, None, None))
    elif type in [dict, Dict]:
      # Mention the subtype.
      return 'dictionary of {} to {}'.format(
          Field.get_type_name_static(keytype, None, None),
          Field.get_type_name_static(subtype, None, None))
    elif type is None:
      # This is only here to allow generic handling of UnrecognizedField errors.
      return 'None'
    elif issubclass(type, enum.Enum):
      # Get the list of valid options as quoted strings.
      options = [repr(str(member.value)) for member in type]
      return '{} (one of {})'.format(type.__name__, ', '.join(options))
    elif issubclass(type, ValidatingType):
      return type.name()

    # Otherwise, return the name of the type.
    return type.__name__


class Base(object):
  """A base class for config objects.

  This will handle all validation, type-checking, defaults, and extraction of
  values from an input dictionary.

  Subclasses must define class-level Field objects defining their fields.
  The base class does the rest.
  """

  def __init__(self, dictionary: Dict[str, Any]) -> None:
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

  def _check_and_convert_type(self,
                              field: Field,
                              key: str,
                              value: Any) -> Any:
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
    assert field.type is not None, 'No type info for Field {}'.format(key)
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
    if field.type in [list, List]:
      if not isinstance(value, list):
        raise WrongType(self.__class__, key, field)

      subfield = Field(field.subtype)
      try:
        return [self._check_and_convert_type(subfield, key, v) for v in value]
      except WrongType as e:
        # If conversion raises WrongType on the subfield, raise a WrongType
        # error on this field instead, so that the printed error makes sense.
        if e.field == subfield:
          raise WrongType(self.__class__, key, field) from None
        else:
          raise

    # For dictionaries, check the type of the value itself, then check the
    # type of the dictionary keys, then the type of the dictionary values.
    if field.type in [dict, Dict]:
      if not isinstance(value, dict):
        raise WrongType(self.__class__, key, field)

      keyfield = Field(field.keytype)
      subfield = Field(field.subtype)
      try:
        converted_dict = {}
        for subkey, subvalue in value.items():
          subkey = self._check_and_convert_type(keyfield, key, subkey)
          subvalue = self._check_and_convert_type(subfield, key, subvalue)
          converted_dict[subkey] = subvalue
        return converted_dict
      except WrongType as e:
        # If conversion raises WrongType on the subfield or keyfield, raise a
        # WrongType error on this field instead, so that the printed error
        # makes sense.
        if e.field == keyfield or e.field == subfield:
          raise WrongType(self.__class__, key, field) from None
        else:
          raise

    # For enums, try to case the value to the enum type, and raise a WrontType
    # error if this fails.
    if issubclass(field.type, enum.Enum):
      try:
        return field.type(value)
      except ValueError:
        raise WrongType(self.__class__, key, field) from None

    # A float should be permissive and accept an int, as well.
    if field.type is float:
      if not isinstance(value, (float, int)):
        raise WrongType(self.__class__, key, field)
      return value

    # For strings, accept bools, ints, and floats, too.  For example, "true",
    # "7", and "10.2" are all valid strings, but will come out of the YAML
    # parser as a bool, and int, and a float, respectively.  Convert these to
    # string.
    if field.type is str:
      if isinstance(value, (bool, float, int, str)):
        return str(value)
      raise WrongType(self.__class__, key, field)

    # These aren't true types, but validation classes for specific types of
    # limited input.  Run the validate() method to check the input.
    if issubclass(field.type, ValidatingType):
      try:
        field.type.validate(value)
      except TypeError:
        raise WrongType(self.__class__, key, field) from None
      except ValueError as e:
        raise MalformedField(self.__class__, key, field, str(e)) from None
      return value

    # For all other types, just do a basic type check and return the original
    # value.
    if not isinstance(value, field.type):
      raise WrongType(self.__class__, key, field)
    return value


# A type parameter used by the Generic RuntimeMap below.  Concrete types used
# here must inherit from the RuntimeMap base class.
RuntimeMapSubclass = TypeVar('RuntimeMapSubclass', bound='RuntimeMap')

# This decorator makes it so that we only have to implement __eq__ and __lt__
# to make the instances sortable.  These magic methods in turn depend on
# _sortable_properties, which subclasses must implement.
@functools.total_ordering
class RuntimeMap(Generic[RuntimeMapSubclass], Base):
  """Maintains a map of keys to specific instances from the config file.

  This means a Field can have its type defined before the valid keys/values of
  that type are known.  For example, this is used for resolutions, which are
  defined by a config file.

  After calling set_map on the subclass, the get_value method can be used to
  look up a value from its key.  For example, after setting the map to
  {'foo': 'bar'}, 'foo' becomes the only valid key.  Passing the key 'foo' to
  the get_value then results in the value 'bar' being returned.
  """

  _map: Dict[str, RuntimeMapSubclass] = {}


  def get_key(self) -> str:
    """This defines the synthetic 'get_key' property which will be attached to
    instances later inside set_map.  This definition is only for the sake of
    mypy's type analysis, and will never be called."""

    raise RuntimeError('Synthetic get_key is missing on RuntimeMapSubclass!')

  # NOTE: mypy 0.770 won't accept the @abc.abstractmethod decorator here.  The
  # error is "Only concrete class can be given where
  # Type[RuntimeMap[RuntimeMapSubclass]] is expected."  Removing the decorator
  # makes this class technically concrete.  We still have the RuntimeError below
  # if a subclass doesn't implement this required method.
  def _sortable_properties(self) -> Tuple:
    """Return a tuple of sortable properties.  Implemented by subclasses."""
    raise RuntimeError('_sortable_properties missing on RuntimeMapSubclass!')

  def __eq__(self, other: Any) -> bool:
    return self._sortable_properties() == other._sortable_properties()

  def __lt__(self, other: Any) -> bool:
    return self._sortable_properties() < other._sortable_properties()

  def __hash__(self) -> int:
      return super().__hash__()

  @classmethod
  def set_map(cls,
              map: Dict[str, RuntimeMapSubclass]) -> None:
    """Set the map of valid values for this class."""

    assert cls != RuntimeMap, 'Do not use the base class directly!'
    cls._map = map

    # Synthesize a method on each value to allow the key to be recovered.
    # Use a default parameter in the lambda to effectively bind the parameter,
    # as described here: https://stackoverflow.com/a/19837683
    # Not doing this causes the lambda to always return the key from the final
    # iteration of the loop (a problem familiar to many JavaScript developers).
    for key, value in map.items():
      setattr(value, 'get_key', lambda bound_key=key: bound_key)

  @classmethod
  def get_value(cls, key: str) -> RuntimeMapSubclass:
    """Get a valid value by its key."""

    assert cls != RuntimeMap, 'Do not use the base class directly!'
    try:
      return cls._map[key]
    except KeyError:
      raise ValueError(
          '{} is not a valid {}'.format(key, cls.__name__)) from None

  @classmethod
  def keys(cls):
    """This allows the config system to print the list of allowed strings."""
    return cls._map.keys()

  @classmethod
  def sorted_values(cls) -> List[RuntimeMapSubclass]:
    return sorted(cls._map.values())


class RuntimeMapKeyValidator(ValidatingType, str):
  """A validator that only allows the valid keys for a certain RuntimeMap
  subclass.

  A RuntimeMap subclass should be paired with a RuntimeMapKeyValidator subclass.
  The RuntimeMapKeyValidator subclass should have a "map_class" variable which
  points to the RuntimeMap subclass."""

  """Must be provided by subclasses and point to the matching RuntimeMap
  subclass."""
  map_class: Type[RuntimeMap] = None  # type: ignore

  @classmethod
  def name(cls) -> str:
    options = [repr(str(key)) for key in cls.map_class.keys()]
    return '{} name (one of {})'.format(
        cls.map_class.__name__, ', '.join(options))

  @classmethod
  def validate(cls, key):
    if type(key) is not str:
      raise TypeError()

    if key not in cls.map_class.keys():
      raise ValueError(
          '{} is not a valid {}'.format(key, cls.name()))

