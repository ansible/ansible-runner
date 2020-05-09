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

from collections import MutableMapping, MutableSequence

from six import iteritems


class Container(object):

    def __init__(self, cls):
        self.cls = cls
        self.store = None

    def __repr__(self):
        return json.dumps(self.serialize())

    def __eq__(self, other):
        if hasattr(other, 'serialize'):
            other = other.serialize()
        return self.serialize() == other

    def __neq__(self, other):
        return not self.__eq__(other)

    def __cmp__(self, other):
        return self.__eq__(other)

    def __deepcopy__(self, memo):
        kwargs = self.serialize()
        o = type(self)(self.cls)
        o.deserialize(kwargs)
        return o

    def _type_check(self, value):
        if not isinstance(value, self.cls):
            raise TypeError(
                "invalid type, got {}, expected {}".format(
                    type(value), type(self.cls)
                )
            )

    def new(self, **kwargs):
        raise NotImplementedError

    def serialize(self):
        raise NotImplementedError

    def deserialize(self, ds):
        raise NotImplementedError


class IndexContainer(MutableSequence, Container):

    def __init__(self, cls, unique=False):
        super(IndexContainer, self).__init__(cls)
        self.store = list()
        self.unique = unique

    def __getitem__(self, index):
        return self.store[index]

    def __setitem__(self, index, value):
        self._type_check(value)
        if not self.unique or (self.unique and value not in self.store):
            self.store[index] = value

    def __delitem__(self, index):
        del self.store[index]

    def __len__(self):
        return len(self.store)

    def insert(self, index, value):
        self._type_check(value)
        self.store.insert(index, value)

    def append(self, value):
        self._type_check(value)
        if not self.unique or (self.unique and value not in self.store):
            super(IndexContainer, self).append(value)

    def new(self, **kwargs):
        obj = self.cls(**kwargs)
        self.append(obj)
        return obj

    def __deepcopy__(self, memo):
        kwargs = self.serialize()
        o = type(self)(self.cls, self.unique)
        o.deserialize(kwargs)
        return o

    def serialize(self):
        objects = list()
        for item in self.store:
            if hasattr(item, 'serialize'):
                objects.append(item.serialize())
            else:
                objects.append(item)
        return objects

    def deserialize(self, ds):
        assert isinstance(ds, list), "argument must be of type 'list'"
        for item in ds:
            self.new(**item)


class MapContainer(MutableMapping, Container):

    def __init__(self, cls):
        super(MapContainer, self).__init__(cls)
        self.store = {}

    def __getitem__(self, index):
        return self.store[index]

    def __setitem__(self, index, value):
        self._type_check(value)
        self.store[index] = value

    def __delitem__(self, index):
        del self.store[index]

    def __len__(self):
        return len(self.store)

    def __iter__(self):
        return iter(self.store)

    def new(self, _key, **kwargs):
        if _key in self.store:
            raise ValueError("item with key {} already exists".format(_key))
        obj = self.cls(**kwargs)
        self[_key] = obj
        return obj

    def serialize(self):
        return dict([(k, v.serialize()) for k, v in iteritems(self.store)])

    def deserialize(self, ds):
        assert isinstance(ds, dict), "argument must be of type 'dict'"
        for key, value in iteritems(ds):
            self.new(key, **value)
