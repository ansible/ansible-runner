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
from ansible_runner.types.validators import ChoiceValidator
from ansible_runner.helpers import make_attr
from ansible_runner.playbook import Base


VALID_ORDER_VALUES = ChoiceValidator(frozenset([
    'inventory', 'sorted', 'reverse_sorted', 'reverse_inventory', 'shuffle'
]))


class Play(Base, Object):
    """Provides a model for dynamically creating Ansible plays

    This class provides an implementation that represents an
    Ansible play.  An instance of this class can be directly
    injected into an Ansible playbook.

    The following is an example play.

    >>> from ansible_runner.playbook.plays import Play
    >>> p = Play()
    >>> p.gather_facts = False
    >>> p.connection = 'local'

    The newly created instance of ``Play`` can be added to an existing
    playbook instance.

    >>> from ansible_runner.playbook import Playbook
    >>> pb = Playbook()
    >>> pb.append(p)

    A new instance of ``Play`` can also be created directly from the
    playbook object using the ``new()`` method.

    >>> new_play = pb.new()

    :param force_handlers:
        Will force notified handler execution for hosts even if they
        failed during the play. Will not trigger if the play itself fails.
    :type force_handlers: bool

    :param gather_facts:
        A boolean that controls if the play will automatically run the
        ‘setup’ task to gather facts for the hosts.
    :type gather_facts: bool

    :param gather_subset:
        Allows you to pass subset options to the fact gathering plugin
        controlled by gather_facts.
    :type gather_subset: list

    :param gather_timeout:
        Allows you to set the timeout for the fact gathering plugin
        controlled by gather_facts.
    :type gather_timeout: int

    :param handlers:
        A section with tasks that are treated as handlers, these won’t
        get executed normally, only when notified after each section of
        tasks is complete. A handler’s listen field is not templatable.
    :type handlers: list

    :param hosts:
        A list of groups, hosts or host pattern that translates into a
        list of hosts that are the play’s target.
    :type hosts: str

    :param max_fail_precentage:
        can be used to abort the run after a given percentage of hosts
        in the current batch has failed.
    :type max_fail_precentage: float

    :param order:
        Controls the sorting of hosts as they are used for executing
        the play. Possible values are inventory (default), sorted,
        reverse_sorted, reverse_inventory and shuffle.
    :type order: str

    :param post_tasks:
        A list of tasks to execute after the tasks section.
    :type post_tasks: Tasks

    :param pre_tasks:
        A list of tasks to execute before roles.
    :type pre_tasks: Tasks

    :param roles:
        List of roles to be imported into the play
    :type roles: IndexContainer

    :param serial:
        Explicitly define how Ansible batches the execution of the
        current play on the play’s target
    :type serial: int

    :param strategy:
        Allows you to choose the connection plugin to use for the play.
    :type strategy: str

    :param tasks:
        Main list of tasks to execute in the play, they run after roles
        and before post_tasks.
    :type tasks: Tasks

    :param vars_prompt:
        list of variables to prompt for.
    :type vars_prompt: str
    """

    force_handlers = make_attr('boolean')
    gather_facts = make_attr('boolean')
    gather_subset = make_attr('list')
    gather_timeout = make_attr('integer')
    handlers = make_attr('list')
    hosts = make_attr('string', default='all')
    max_fail_precentage = make_attr('float')
    order = make_attr('string', validators=(VALID_ORDER_VALUES,))
    post_tasks = make_attr('ansible_runner.playbook.tasks:Tasks')
    pre_tasks = make_attr('ansible_runner.playbook.tasks:Tasks')
    roles = make_attr('index', cls='ansible_runner.playbook.roles:Role')
    serial = make_attr('integer')
    strategy = make_attr('string')
    tasks = make_attr('ansible_runner.playbook.tasks:Tasks')
    vars_prompt = make_attr('string')
