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
import json

from six import with_metaclass, iteritems

from ansible_runner.types.attrs import Attribute
from ansible_runner.types.attrs import LazyAttribute
from ansible_runner.types.attrs import SERIALIZE_WHEN_NEVER
from ansible_runner.helpers import isvalidattrname
from ansible_runner.helpers import make_attr


class BaseMeta(type):

    def __new__(cls, name, parents, dct):
        dct['_attributes'] = {}

        def _create_attrs(attr_dct):
            for attr_name in attr_dct:
                attr = attr_dct[attr_name]
                if isinstance(attr, Attribute):
                    attr.name = attr_name

                    isvalidattrname(attr_name)
                    dct['_attributes'][attr_name] = attr

                    removed = set()

                    for entry in list(attr.aliases):
                        if entry not in attr_dct:
                            isvalidattrname(entry)
                            dct['_attributes'][entry] = attr
                        elif entry in attr_dct:
                            removed.add(entry)

                    attr.aliases = tuple(set(attr.aliases).difference(removed))

        # process parents first to allow more specific overrides
        for parent in parents:
            _create_attrs(parent.__dict__)

        _create_attrs(dct)

        return super(BaseMeta, cls).__new__(cls, name, parents, dct)


class Object(with_metaclass(BaseMeta)):
    """The base class for all typed instances

    This class provides the base implementation from which all
    typed classes derive from.  The Object class handles setting
    up and validating configured attributes (properties).  Typically
    this class should not be directly instantiated.
    """

    def __init__(self, **kwargs):
        require_one_of = list()

        for key, attr in iteritems(self._attributes.copy()):
            if isinstance(attr, LazyAttribute):
                attr.kwargs['name'] = key
                attr = make_attr(**attr.kwargs)
                self._attributes[attr.name] = attr
                self.__dict__[attr.name] = attr

            value = kwargs.pop(key, attr.default)

            if attr.require_one_of is not None:
                require_one_of.append(attr)

            if key == attr.name:
                attrval = getattr(self, key)
                if attrval is None or isinstance(attrval, Attribute):
                    setattr(self, key, value)
            elif key in attr.aliases:
                setattr(self, attr.name, value)

        if kwargs:
            raise AttributeError("unknown keyword argument")

        for attr in require_one_of:
            for name in attr.require_one_of:
                if getattr(self, name) is not None:
                    break
            else:
                raise ValueError("missing required_one_of value")

    def __repr__(self):
        return json.dumps(self.serialize())

    def __setattr__(self, key, value):
        if key in self._attributes:
            attr = self._attributes[key]

            value = attr(value)

            if attr.name != key:
                self.__dict__[attr.name] = value

            for item in attr.aliases:
                if item != key:
                    self.__dict__[item] = value

            mutually_exclusive_with = attr.mutually_exclusive_with

            if mutually_exclusive_with and value is not None:
                delattr(self, mutually_exclusive_with)

        elif not key.startswith('_'):
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__.__name__, key))

        self.__dict__[key] = value

    def __delattr__(self, key):
        if key not in self._attributes and key in dir(self):
            raise AttributeError("cannot delete attribute '{}'".format(key))
        self.__setattr__(key, None)

    def __eq__(self, other):
        return self.serialize() == other.serialize()

    def __neq__(self, other):
        return not self.__eq__(other)

    def __cmp__(self, other):
        return self.__eq__(other)

    def __deepcopy__(self, memo):
        return type(self)(**self.serialize())

    def serialize(self):
        obj = {}

        for item, attr in iteritems(self._attributes):
            value = getattr(self, item)

            if attr.type is bool and value in (True, False) and \
               attr.serialize_when < SERIALIZE_WHEN_NEVER:
                obj[item] = value

            elif value and attr.serialize_when < SERIALIZE_WHEN_NEVER:
                if hasattr(value, 'serialize'):
                    obj[item] = value.serialize()
                else:
                    obj[item] = value

        return obj

    def deserialize(self, ds):
        assert isinstance(ds, dict), "argument must be of type 'dict'"
        for key, value in iteritems(ds):
            attr = getattr(self, key)
            if hasattr(attr, 'deserialize'):
                attr.deserialize(value)
            else:
                setattr(self, key, value)


class MapObject(Object):
    """Creates an object that can have arbitrary key/value pairs

    This object acts very much like a normal Python `dict` object in
    that aribtrary key/value pairs can be associated with an instance;
    however, it is not a `dict` object.  There are some patterns that
    will not work as expected.
    """

    def __init__(self, **kwargs):
        self._vars = {}
        for item in set(kwargs).difference(self._attributes):
            self._vars[item] = kwargs.pop(item)
        super(MapObject, self).__init__(**kwargs)

    def __getitem__(self, key):
        if key in self._attributes:
            return getattr(self, key)
        else:
            return self._vars[key]

    def __setitem__(self, key, value):
        if key in self._attributes:
            setattr(self, key, value)
        else:
            self._vars[key] = value

    def __delitem__(self, key):
        if key in self._attributes:
            delattr(self, key)
        else:
            del self._vars[key]

    #def __len__(self):
    #    return len(self._vars)

    def __iter__(self):
        return iter(self._vars)

    def serialize(self):
        obj = super(MapObject, self).serialize()
        obj.update(self._vars)
        return obj

    def deserialize(self, ds):
        assert isinstance(ds, dict), "argument must be of type 'dict'"
        kwargs = {}
        for name in self._attributes:
            if name in ds:
                kwargs[name] = ds.pop(name)
        super(MapObject, self).deserialize(kwargs)
        self._vars.update(ds)
