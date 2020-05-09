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
from ansible_runner.types.objects import MapObject
from ansible_runner.helpers import make_attr
from ansible_runner.inventory import AnsibleVars


class Vars(AnsibleVars, MapObject):
    """Implements well-known Ansible varialbles for Child vars

    An instance of this class provides access to the Ansible
    well known Ansible inventory varialbles asl well as allows
    for the assigning of arbitrary key / value pairs that will be
    associated with the child instance.
    """
    pass


class Child(Object):
    """Provides an implementation of a Child inventory object

    This class implements an Ansible child group in the inventory.
    Child objects are effectively ways to group related hosts and
    variables together in children.

    >>> from ansible_runner.inventory.children import Child
    >>> child = Child()
    >>> child.vars.ansible_connection = 'local'
    >>> child.vars['key'] = 'value'

    Child objects can be added to Children on an Ansible inventory object.

    >>> from ansible_runner.inventory import Inventory
    >>> inventory = Inventory()
    >>> inventory.children['group_x'] = child

    Child objects can also be created from children attributes on the
    inventory object.

    >>> child_2 = inventory.children.new('group_y')
    >>> child_2.vars.ansible_user = 'admin'

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
    vars = make_attr('any', cls='ansible_runner.inventory.children:Vars')
    children = make_attr(
        'map',
        cls='ansible_runner.inventory.children:Child',
        lazy=True
    )

    def __init__(self, **kwargs):
        childvars = kwargs.pop('vars', None)
        if childvars and isinstance(childvars, dict):
            kwargs['vars'] = Vars(**childvars)
        super(Child, self).__init__(**kwargs)

