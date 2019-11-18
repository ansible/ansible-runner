# -*- coding: utf-8 -*-
#
# Copyright (c) 2019 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
import pytest

from ansible_runner.types import attrs
from ansible_runner.types.objects import Object
from ansible_runner.types.attrs import Attribute
from ansible_runner.types.attrs import String, Integer, Boolean, List, Dict
from ansible_runner.types.attrs import Bytes, Float
from ansible_runner.types.attrs import Map, Index, Any
from ansible_runner.types.containers import MapContainer
from ansible_runner.types.containers import IndexContainer
from ansible_runner.playbook import Playbook


class Item(Object):
    name = String()


def test_create_attribute_defaults():
    a = Attribute(type=None)
    assert a.type is None
    assert a.default is None
    assert isinstance(a.validators, set)
    assert a.aliases == tuple()
    assert a.serialize_when == 0


def test_str_attribute():
    a = String()
    assert a.type == str
    assert a.default is None


def test_bool_attribute():
    a = Boolean()
    assert a.type == bool
    assert a.default is None


def test_int_attribute():
    a = Integer()
    assert a.type == int
    assert a.default is None


def test_list_attribute():
    a = List()
    assert a.type == list
    assert a.default == []


def test_dict_attribute():
    a = Dict()
    assert a.type == dict
    assert a.default == {}


def test_bytes_attribute():
    a = Bytes()
    assert a.type == bytes
    assert a.default is None


def test_float_attribute():
    a = Float()
    assert a.type == float
    assert a.default is None


def test_attribute_requires_type():
    with pytest.raises(TypeError):
        Attribute()


def test_invalid_default_type():
    with pytest.raises(TypeError):
        Attribute(type=str, default=1)


def test_call_list_with_default_value():
    """Ensure a copy of the default value is returned
    """
    default_value = [1, 2, 3]
    a = List(default=default_value)
    z = a(None)
    assert id(z) != id(default_value)
    assert z == default_value


def test_call_dict_with_default_value():
    """Ensure a copy of the default value is returned
    """
    default_value = {'one': 1, 'two': 2, 'three': 3}
    a = Dict(default=default_value)
    z = a(None)
    assert id(z) != id(default_value)
    assert z == default_value


def test_map_container():
    c = Map(Item)
    assert isinstance(c, Map)
    r = c(None)
    assert isinstance(r, MapContainer)


def test_index_container():
    c = Index(Item)
    assert isinstance(c, Index)
    r = c(None)
    assert isinstance(r, IndexContainer)


def test_any():
    c = Any(object)
    assert isinstance(c, Any)
    r = c('test')
    assert isinstance(r, str)
    r = c(1)
    assert isinstance(r, int)
    r = c(True)
    assert isinstance(r, bool)
    r = c(list())
    assert isinstance(r, list)
    r = c({})
    assert isinstance(r, dict)


def test_enums():
    assert attrs.SERIALIZE_WHEN_ALWAYS == 0
    assert attrs.SERIALIZE_WHEN_PRESENT == 1
    assert attrs.SERIALIZE_WHEN_NEVER == 2


def test_bad_serialize_when_value():
    with pytest.raises(ValueError):
        Attribute(None, serialize_when=3)


def test_bad_value_type():
    with pytest.raises(TypeError):
        item = Item()
        item.name = 1


def test_validators_raises_error():
    with pytest.raises(AttributeError):
        Attribute(None, validators=1)


def test_required_mutually_exclusive():
    with pytest.raises(AttributeError):
        Attribute(None, required=True, require_one_of=('foo', 'bar'))


def test_required_with_serialized_when():
    with pytest.raises(AttributeError):
        Attribute(None, required=True, serialize_when=2)


def test_normalize_string_attribute():
    s = String()
    assert s(u'test') == 'test'


def test_map_loads_entry_point():
    a = Map('ansible_runner.types.objects:Object')
    assert a.cls == Object


def test_map_creates_new_instance():
    a = Map('ansible_runner.types.objects:Object')
    assert isinstance(a(value={}), MapContainer)


def test_index_loads_entry_point():
    a = Index('ansible_runner.types.objects:Object')
    assert a.cls == Object


def test_index_creates_new_instance():
    a = Index('ansible_runner.types.objects:Object')
    assert isinstance(a(value=[]), IndexContainer)


def test_list_coerce():
    a = List(coerce=True)
    assert a('test') == ['test']


def test_any_with_entrypoint():
    a = Any('ansible_runner.playbook:Playbook')
    assert isinstance(a.default, Playbook)
