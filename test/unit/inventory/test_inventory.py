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
from ansible_runner.inventory import Inventory


def test_serialization_deserialization():
    inv = Inventory()
    inv.hosts.new('test', ansible_host='testhost')
    inv.children.new('test', ansible_connection='testchild')
    inv.vars['test'] = 'testvar'

    hosts = {'test': {'ansible_host': 'testhost'}}
    children = {'test': {'ansible_connection': 'testchild'}}
    serialized = {'all': {'hosts': hosts,
                          'children': children,
                          'vars': {'test': 'testvar'}}}

    assert inv.serialize() == serialized

    inv2 = Inventory(**serialized)
    assert inv2 == inv

    inv3 = Inventory()
    inv3.deserialize(serialized)

    assert inv3 == inv
