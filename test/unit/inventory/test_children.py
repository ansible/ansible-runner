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
from ansible_runner.inventory.children import Child


def test_serialization_deserialization():
    serialized = {'vars': {'ansible_connection': 'test'}}

    child = Child()
    child.vars.ansible_connection = 'test'
    assert child.serialize() == serialized

    child1 = Child(**serialized)
    assert child1 == child

    child2 = Child()
    child2.deserialize(serialized)

    assert child2 == child
