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
from ansible_runner.inventory.hosts import Host


def test_serialization_deserialization():
    host = Host()
    host.ansible_host = 'test'
    host.ansible_user = 'admin'
    host.ansible_password = 'admin'

    serialized = {'ansible_host': 'test',
                  'ansible_user': 'admin', 'ansible_ssh_user': 'admin',
                  'ansible_password': 'admin', 'ansible_ssh_pass': 'admin'}


    assert host.serialize() == serialized

    host1 = Host(**serialized)

    assert host1 == host

    host2 = Host()
    host2.deserialize(serialized)

    assert host2 == host
