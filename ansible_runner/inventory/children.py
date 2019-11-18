# -*- coding: utf-8 -*-
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
from ansible_runner.types.objects import Object
from ansible_runner.helpers import make_attr
from ansible_runner.inventory import AnsibleVars


class Child(AnsibleVars, Object):
    """Provides an implementation of a Child inventory object

    This class implements an Ansible child group in the inventory.
    Child objects are effectively ways to group related hosts and
    variables together in children.

    >>> from ansible_runner.inventory.children import Child
    >>> child = Child()
    >>> child.name = 'group_x'
    >>> child.ansible_connection = 'local'
    >>> child.vars['key'] = 'value'

    Child objects can be added to Children on an Ansible inventory object.

    >>> from ansible_runner.inventory import Inventory
    >>> inventory = Inventory()
    >>> inventory.children['group_x'] = child

    Child objects can also be created from children attributes on the
    inventory object.

    >>> child_2 = inventory.children.new('group_y')
    >>> child_2.ansible_user = 'admin'

    Children properties are fully recursive for building nested groups
    in the inventory.

    :param hosts:
        The set of hosts associated with this child
    :type hosts: MapContainer

    :param children:
        List of children supported for this inventory
    :type children: MapContainer

    :param vars:
        Arbitrary set of key/value pairs associated with this child
    :type vars: dict
    """

    hosts = make_attr('map', cls='ansible_runner.inventory.hosts:Host')
    children = make_attr(
        'map',
        cls='ansible_runner.inventory.children:Child',
        lazy=True
    )
    vars = make_attr('dict')
