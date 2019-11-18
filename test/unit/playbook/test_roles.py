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
from ansible_runner.playbook.roles import Role


def test_serialization_deserialization():
    role = Role(name='test')
    role.delegate_facts = True
    role.delegate_to = 'test'

    data = role.serialize()

    assert data == {'name': 'test', 'delegate_facts': True, 'delegate_to': 'test'}

    newrole = Role(name='test')
    newrole.deserialize(data)

    assert newrole == role
