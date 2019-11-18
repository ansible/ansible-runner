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
from ansible_runner.playbook import Base
from ansible_runner.playbook import Delegate
from ansible_runner.playbook import Conditional


class Role(Base, Delegate, Conditional, MapObject):
    """Provides a model for creating Ansible playbook roles

    This implementation can be used to build an instance of an
    Ansible role.  The instance can be included in an Ansible
    play using the roles attribute.

    The following is an example of how to create a role entry:

    >>> from ansible_runner.playbook.roles import Role
    >>> role = Role(name='example.role')

    Variables can be directly assigned to roles using a `dict-like`
    interface:

    >>> role['var1'] = 'value1'
    >>> role['var2'] = 'value2'

    Once the role instance is created, it can be directly added to a
    ``Play`` instance.

    >>> from ansible_runner.playbook import Playbook
    >>> pb = Playbook()
    >>> play = pb.new()
    >>> play.roles.append(role)

    A new instance of ``Role`` can also be created by calling the ``new()``
    method on the Play.roles attribute.

    >>> second_role = play.roles.new(name='example.role2')

    .. note::

        The ``name`` parameter is a redefinition of the same attribute
        inhereted from ``Base`` except that with an instance of ``Role``
        the attribute is now required.

    :param name:
        Identifier. Can be used for documentation, in or tasks/handlers.
    :type name: str
    """

    name = make_attr('string', required=True)
