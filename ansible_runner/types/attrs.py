#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
from copy import deepcopy

from six import string_types

from ansible_runner.types.containers import IndexContainer
from ansible_runner.types.containers import MapContainer
from ansible_runner.types.validators import TypeValidator
from ansible_runner.types.validators import RequiredValueValidator
from ansible_runner.helpers import load_module
from ansible_runner.helpers import to_list
from ansible_runner.utils import ensure_str


SERIALIZE_WHEN_ALWAYS = 0
SERIALIZE_WHEN_PRESENT = 1
SERIALIZE_WHEN_NEVER = 2


class Attribute(object):
    """Meta data that describes an attribute associated with an Object

    Attributes are attached to Objects to create typed instances.
    The meta data that handles how a particular property is evaluated
    is based on an instance of Attribute

    :param type:
        the Python object type for this attribute
    :type type: object

    :param name:
        the name of the Object attribute
    :type name: str

    :param required:
        whether or not the attribute is required to be set
    :type required: bool

    :param validators:
        an interable list of validators for the value
    :type validators: tuple

    :param serialize_when:
        controls when an attribute should be serialized
    :type serialize_when: int

    :param aliases:
        one or more alias attribute names
    :type aliases: tuple

    :param mutually_exclusive_group:
        assigns the named attribute to a mutally exclusive configuration
        group where one and only one attribute will be used.  all attributes
        with the same group name will be considered.
    :type mutually_exclusive_group: str

    :param mutually_exclusive_priority:
        used to influence which attribute in a group is selected.  all
        attributes are assigned a priority of 255 by default.  the lowest
        priority attribute with a configured value wins.
    :type mutually_exclusive_priority: int

    :param require_one_of:
        set of attribute names where at most one value must be set
    :type reuqired_one_of: tuple

    :returns:
        an instance of Attribute
    :rtype: Attribute
    """

    def __init__(self, type, name=None, default=None, required=None,
                 validators=None, serialize_when=None, aliases=None,
                 mutually_exclusive_group=None, require_one_of=None,
                 mutually_exclusive_priority=255):

        self.type = type
        self.name = name
        self.default = default
        self.validators = validators or set()
        self.aliases = aliases or ()
        self.serialize_when = serialize_when or SERIALIZE_WHEN_ALWAYS
        self.mutually_exclusive_group = mutually_exclusive_group
        self.mutually_exclusive_priority = int(mutually_exclusive_priority)
        self.require_one_of = require_one_of

        try:
            self.validators = set(self.validators)
        except TypeError:
            raise AttributeError("validators must be iterable")

        if serialize_when is not None:
            if serialize_when not in (0, 1, 2):
                raise ValueError("invalid value for serialize_when")

        self.validators.add(TypeValidator(self.type))

        if required is True and self.require_one_of is not None:
            raise AttributeError("required and require_one_of are mutually exclusive")

        if required:
            self.validators.add(RequiredValueValidator())
            if self.serialize_when > 0:
                raise AttributeError(
                    "required attributes must always be serialized"
                )

        if self.default is not None:
            for item in self.validators:
                item(self.default)

    def __call__(self, value):
        value = value if value is not None else self.default
        for item in self.validators:
            item(value)
        return deepcopy(value)


class LazyAttribute(Attribute):

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        super(LazyAttribute, self).__init__(None)


class String(Attribute):

    def __init__(self, *args, **kwargs):
        super(String, self).__init__(str, *args, **kwargs)

    def __call__(self, value):
        if value:
            value = ensure_str(value)
        return super(String, self).__call__(value)


class Integer(Attribute):

    def __init__(self, *args, **kwargs):
        return super(Integer, self).__init__(int, *args, **kwargs)


class Float(Attribute):

    def __init__(self, *args, **kwargs):
        return super(Float, self).__init__(float, *args, **kwargs)


class Bytes(Attribute):

    def __init__(self, *args, **kwargs):
        return super(Bytes, self).__init__(bytes, *args, **kwargs)


class Boolean(Attribute):

    def __init__(self, *args, **kwargs):
        return super(Boolean, self).__init__(bool, *args, **kwargs)


class List(Attribute):

    def __init__(self, coerce=None, *args, **kwargs):
        self.coerce = coerce
        if kwargs.get('default') is None:
            kwargs['default'] = []
        super(List, self).__init__(list, *args, **kwargs)

    def __call__(self, value):
        if self.coerce:
            value = to_list(value)
        return super(List, self).__call__(value)


class Dict(Attribute):

    def __init__(self, *args, **kwargs):
        if kwargs.get('default') is None:
            kwargs['default'] = {}
        super(Dict, self).__init__(dict, *args, **kwargs)


class Any(Attribute):

    def __init__(self, cls, *args, **kwargs):
        if isinstance(cls, string_types):
            cls = load_module(cls)
        if kwargs.get('default') is None:
            kwargs['default'] = cls()
        kwargs['type'] = cls
        super(Any, self).__init__(*args, **kwargs)


class Map(Attribute):

    def __init__(self, cls, *args, **kwargs):
        if isinstance(cls, string_types):
            cls = load_module(cls)

        self.cls = cls

        if kwargs.get('default') is None:
            kwargs['default'] = MapContainer(self.cls)

        super(Map, self).__init__(MapContainer, *args, **kwargs)

    def __call__(self, value):
        if isinstance(value, dict):
            obj = MapContainer(self.cls)
            obj.deserialize(value)
            value = obj
        return super(Map, self).__call__(value)


class Index(Attribute):

    def __init__(self, cls, unique=False, *args, **kwargs):
        if isinstance(cls, string_types):
            cls = load_module(cls)

        self.cls = cls
        self.unique = unique

        if kwargs.get('default') is None:
            kwargs['default'] = IndexContainer(cls, unique)

        super(Index, self).__init__(IndexContainer, *args, **kwargs)

    def __call__(self, value):
        # because a Index is serialialized as a list object, the
        # deserialization process will attempt to pass a native list into the
        # this method.  this will attempt to recreate the Index object
        if isinstance(value, list):
            obj = IndexContainer(self.cls, self.unique)
            obj.deserialize(value)
            value = obj
        return super(Index, self).__call__(value)
