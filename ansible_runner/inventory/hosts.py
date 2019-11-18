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
from ansible_runner.types.objects import MapObject
from ansible_runner.helpers import make_attr
from ansible_runner.inventory import AnsibleVars


class Host(AnsibleVars, MapObject):
    """Represents an inventory host

    The implementation of this class provides an Ansible inventory
    host.  Host objects provide a typed set of properties as well
    as implement a 'dict-like' interface for handling arbitrary
    key / value pairs.

    >>> from ansible_runner.inventory.hosts import Host
    >>> host = Host()
    >>> host.name = 'localhost'
    >>> host.ansible_connection = 'local'
    >>> host['key'] = 'value'

    Host instances can be assign directly to the inventory or to
    children in the inventory.

    >>> from ansible_runner.inventory import Inventory
    >>> inventory = Inventory()
    >>> inventory.hosts['localhost'] = host

    Host entries can also be created from an instance of ``Inventory``.

    >>> host = inventory.hosts.new('localhost')

    :param ansible_host:
        The name of the host to connect to, if different from the alias
        you wish to give to it.
    :type ansible_host: str
    """

    ansible_host = make_attr('string')
