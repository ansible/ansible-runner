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
import copy

import pytest

from ansible_runner.types.objects import Object, MapObject
from ansible_runner.types.attrs import String, Integer, Boolean
from ansible_runner.types.attrs import List, Dict, Any


class Instance(Object):
    name = String()
    strattr = String()
    intattr = Integer()
    boolattr = Boolean()
    listattr = List()
    dictattr = Dict()


class InstanceWithDefaults(Object):
    name = String()
    strattr = String(default='string')
    intattr = Integer(default=0)
    boolattr = Boolean(default=False)
    listattr = List(default=[1, 2, 3])
    dictattr = Dict(default={'one': 1, 'two': 2, 'three': 3})
    anyattr = Any(Instance)


class InstanceWithRequiredAttr(Object):
    required = String(required=True)


class InstanceWithProperty(Object):
    name = String()

    def __init__(self, *args, **kwargs):
        super(InstanceWithProperty, self).__init__(*args, **kwargs)
        self._internal = 'test'


def test_instance():
    o = Instance()
    assert repr(o) is not None

    z = Instance()
    assert o.__eq__(z)
    assert o.__cmp__(z)

    z.name = 'test'
    assert o.__neq__(z)


def test_instance_with_invalid_attribute():
    with pytest.raises(AttributeError):
        Instance(foo='bar')


def test_instance_no_attribute():
    o = Instance()
    with pytest.raises(AttributeError):
        o.test

    with pytest.raises(AttributeError):
        o.test = 'test'


def test_instance_set_internal_property():
    o = InstanceWithProperty()
    with pytest.raises(AttributeError):
        del o._internal


def test_deepcopy():
    o = Instance(name='string')
    c = copy.deepcopy(o)
    assert o == c


def test_object_serialize():
    inst = Instance(name='test')

    data = {'name': 'test', 'strattr': 'strattr', 'intattr': 10,
            'boolattr': True, 'listattr': [1, 2, 3], 'dictattr': {'one': 1},
            'anyattr': inst.serialize()}

    o = InstanceWithDefaults(
        name='test', strattr='strattr', intattr=10, boolattr=True,
        listattr=[1, 2, 3], dictattr={'one': 1}, anyattr=Instance(name='test')
    )

    assert data == o.serialize()

    data = {'name': 'test', 'strattr': 'strattr', 'intattr': 10,
            'boolattr': False, 'listattr': [1, 2, 3], 'dictattr': {'one': 1}}

    o = Instance(name='test', strattr='strattr', intattr=10, boolattr=False,
                 listattr=[1, 2, 3], dictattr={'one': 1})

    assert data == o.serialize()


def test_object_deserialize():
    inst = Instance(name='test')

    data = {'name': 'test', 'strattr': 'strattr', 'intattr': 10,
            'boolattr': True, 'listattr': [1, 2, 3], 'dictattr': {'one': 1},
            'anyattr': inst.serialize()}

    o = InstanceWithDefaults()
    o.deserialize(data)

    assert data == o.serialize()


def test_set_strattr():
    o = Instance()
    o.strattr = 'test'
    with pytest.raises(TypeError):
        o.strattr = 1
        o.strattr = True
        o.strattr = [1, 2, 3]
        o.strattr = {'one': 1, 'two': 2, 'three': 3}


def test_set_intattr():
    o = Instance()
    o.intattr = 1
    with pytest.raises(TypeError):
        o.intattr = "string"
        o.intattr = True
        o.intattr = [1, 2, 3]
        o.intattr = {'one': 1, 'two': 2, 'three': 3}


def test_set_boolattr():
    o = Instance()
    o.boolattr = True
    o.boolattr = False
    with pytest.raises(TypeError):
        o.boolattr = "string"
        o.boolattr = 0
        o.boolattr = 1
        o.boolattr = [1, 2, 3]
        o.boolattr = {'one': 1, 'two': 2, 'three': 3}


def test_set_listattr():
    o = Instance()
    o.listattr = [1, 2, 3]
    with pytest.raises(TypeError):
        o.listattr = "string"
        o.listattr = 0
        o.listattr = True
        o.listattr = {'one': 1, 'two': 2, 'three': 3}


def test_set_dictattr():
    o = Instance()
    o.dictattr = {'one': 1, 'two': 2, 'three': 3}
    for value in ('string', 0, True, [1, 2, 3]):
        with pytest.raises(TypeError):
            o.dictattr = value


def test_del_strattr():
    o = Instance()
    assert o.strattr is None
    o.strattr = 'test'
    assert o.strattr == 'test'
    del o.strattr
    assert o.strattr is None


def test_del_intattr():
    o = Instance()
    assert o.intattr is None
    o.intattr = 0
    assert o.intattr == 0
    del o.intattr
    assert o.intattr is None


def test_del_boolattr():
    o = Instance()
    assert o.boolattr is None
    o.boolattr = True
    assert o.boolattr is True
    del o.boolattr
    assert o.boolattr is None


def test_del_listattr():
    o = Instance()
    assert o.listattr == []
    o.listattr = [1, 2, 3]
    assert o.listattr == [1, 2, 3]
    del o.listattr
    assert o.listattr == []


def test_del_dictattr():
    o = Instance()
    assert o.dictattr == {}
    o.dictattr = {'one': 1, 'two': 2, 'three': 3}
    assert o.dictattr == {'one': 1, 'two': 2, 'three': 3}
    del o.dictattr
    assert o.dictattr == {}


def test_strattr_with_defaults():
    o = InstanceWithDefaults()
    assert o.strattr == 'string'
    o.strattr = 'text'
    assert o.strattr == 'text'
    del o.strattr
    assert o.strattr == 'string'


def test_intattr_with_defaults():
    o = InstanceWithDefaults()
    assert o.intattr == 0
    o.intattr = 2
    assert o.intattr == 2
    del o.intattr
    assert o.intattr == 0


def test_boolattr_with_defaults():
    o = InstanceWithDefaults()
    assert o.boolattr is False
    o.boolattr = True
    assert o.boolattr is True
    del o.boolattr
    assert o.boolattr is False


def test_listattr_with_defaults():
    o = InstanceWithDefaults()
    assert o.listattr == [1, 2, 3]
    o.listattr = [4, 5, 6]
    assert o.listattr == [4, 5, 6]
    del o.listattr
    assert o.listattr == [1, 2, 3]


def test_dictattr_with_defaults():
    o = InstanceWithDefaults()
    assert o.dictattr == {'one': 1, 'two': 2, 'three': 3}
    o.dictattr = {'four': 4, 'five': 5, 'six': 6}
    assert o.dictattr == {'four': 4, 'five': 5, 'six': 6}
    del o.dictattr
    assert o.dictattr == {'one': 1, 'two': 2, 'three': 3}


def test_object_init_with_values():
    o = Instance(strattr='string', intattr=100, boolattr=True,
                 listattr=[1, 2, 3], dictattr={'one': 1, 'two': 2, 'three': 3})
    assert o.strattr == 'string'
    assert o.intattr == 100
    assert o.boolattr is True
    assert o.listattr == [1, 2, 3]
    assert o.dictattr == {'one': 1, 'two': 2, 'three': 3}


def test_object_with_required_attr():
    o = InstanceWithRequiredAttr(required='foo')
    assert o.required == 'foo'

    with pytest.raises(ValueError):
        del o.required

    with pytest.raises(ValueError):
        InstanceWithRequiredAttr()


class Aliases(Object):

    attr1 = String(
        aliases=('attr2', 'attr3')
    )

    attr2 = String()


def test_attr1_alias():
    o = Aliases()

    o.attr1 = 'test'

    assert o.attr1 == 'test'
    assert o.attr2 is None
    assert o.attr3 == 'test'

    o.attr2 = 'test2'

    assert o.attr1 == 'test'
    assert o.attr2 == 'test2'
    assert o.attr3 == 'test'

    del o.attr1

    assert o.attr1 is None
    assert o.attr2 == 'test2'
    assert o.attr3 is None

    o.attr1 = 'test'
    del o.attr2

    assert o.attr1 == 'test'
    assert o.attr2 is None
    assert o.attr3 == 'test'

    o = Aliases(attr3='test')

    assert o.attr1 == 'test'
    assert o.attr2 is None
    assert o.attr3 == 'test'


class InstanceWithRequireOneOfAttr(Object):
    attr1 = String(require_one_of=('attr1', 'attr2'))
    attr2 = String(require_one_of=('attr1', 'attr2'))


def test_require_one_of():
    with pytest.raises(ValueError):
        InstanceWithRequireOneOfAttr()

    o = InstanceWithRequireOneOfAttr(attr1='foo')

    assert o.attr1 == 'foo'
    assert o.attr2 is None


class InstanceWithMutuallyExclusiveAttr(Object):
    attr1 = String(mutually_exclusive_group = 'group1',
                   mutually_exclusive_priority=1)
    attr2 = String(mutually_exclusive_group = 'group1')


def test_mutually_exclusive_with():
    o = InstanceWithMutuallyExclusiveAttr(attr1='test')

    assert o.attr1 == 'test'
    assert o.attr2 is None

    o.attr2 = 'test'

    assert o.attr1 == 'test'
    assert o.attr2 == 'test'

    serialized = o.serialize()
    assert serialized.get('attr1') == 'test'
    assert serialized.get('attr2') is None


class MapInstance(MapObject):
    name = String()


def test_init():
    o = MapInstance(name='test')
    assert o.name == 'test'
    assert o._vars == {}


def test_init_with_vars():
    o = MapInstance(name='test', test1='test1')
    assert o.name == 'test'
    assert o['test1'] == 'test1'


def test_get_item():
    o = MapInstance()
    o['test'] = 'test'
    assert o['test'] == 'test'


def test_set_item():
    o = MapInstance(name='test')
    assert o._vars == {}
    o['test'] = 'test'
    assert o._vars['test'] == 'test'


def test_del_item():
    o = MapInstance(name='test')
    assert o._vars == {}
    o['test'] = 'test'
    assert o._vars['test'] == 'test'
    del o['test']
    assert 'test' not in o._vars


def test_mapobject_serialize():
    o = MapInstance()
    o['test'] = 'test'
    assert o.serialize() == {'test': 'test'}


def test_mapobject_deserialize():
    o = MapInstance()
    assert 'test' not in o._vars
    o.deserialize({'test': 'test'})
    assert o._vars['test'] == 'test'


def test_iter():
    o = MapInstance()
    o['test1'] = 'test1'
    o['test2'] = 'test2'
    for item in o:
        assert item in ('test1', 'test2')




