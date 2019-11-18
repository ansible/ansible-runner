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
from ansible_runner.helpers import make_attr
from ansible_runner.types.validators import PortValidator
from ansible_runner.types.containers import IndexContainer
from ansible_runner.helpers import load_module


class Base(object):
    """The ``Base`` class provides attributes that commonly implemented

    All of the attributes in ``Base`` are implemented in all playbook
    instances.  This class should be treated as a mixin class to other
    more specific implementations of playbook components (Play, Task, Role).

    :param any_errors_fatal:
        Force any un-handled task errors on any host to propagate to all
        hosts and end the play.
    :type any_errors_fatal: bool

    :param become:
        Boolean that controls if privilege escalation is used or not
        on Task execution.
    :type become: bool

    :param become_exe:
        UNDOCUMENTED!!
    :type become_exec: str

    :param become_flags:
        A string of flag(s) to pass to the privilege escalation program when
        become is True.
    :type become_flags: str

    :param become_method:
        Which method of privilege escalation to use (such as sudo or su).
    :type become_flags:

    :param become_user:
        User that you ‘become’ after using privilege escalation. The
        remote/login user must have permissions to become this user.
    :type become_user: str

    :param check_mode:
        A boolean that controls if a task is executed in ‘check’ mode
    :type check_mmode: bool

    :param collections:
        UNDOCUMENTED!!
    :type collections: IndexContainer

    :param connection:
        Allows you to change the connection plugin used for tasks to
        execute on the target.
    :type connection: str

    :param debugger:
        Enable debugging tasks based on state of the task result.
    :type debugger: str

    :param diff:
        Toggle to make tasks return ‘diff’ information or not.
    :type diff: bool

    :param environment:
        A dictionary that gets converted into environment vars to be
        provided for the task upon execution. This cannot affect Ansible
        itself nor its configuration, it just sets the variables for the
        code responsible for executing the task.
    :type environment: dict

    :param ignore_errors:
        Boolean that allows you to ignore task failures and continue with
        play. It does not affect connection errors.
    :type ignore_errors: bool

    :param ignore_unreachable:
        Boolean that allows you to ignore unreachable hosts and continue
        with play. This does not affect other task errors (see ignore_errors)
        but is useful for groups of volatile/ephemeral hosts.
    :type ignore_unreachable: bool

    :param module_defaults:
        Specifies default parameter values for modules.
    :type module_defaults: dict

    :param name:
        Identifier. Can be used for documentation, in or tasks/handlers.
    :type name: str

    :param no_log:
        Boolean that controls information disclosure.
    :type no_log: bool

    :param port:
        Used to override the default port used in a connection.
    :type port: int

    :param remote_user:
        User used to log into the target via the connection plugin.
    :type remote_user: str

    :param run_once:
        Boolean that will bypass the host loop, forcing the task to
        attempt to execute on the first host available and afterwards
        apply any results and facts to all active hosts in the same batch.
    :type run_once: bool

    :param tags:
        Tags applied to the task or included tasks, this allows selecting
        subsets of tasks from the command line.
    :type tags: IndexContainer

    :param throttle:
        Limit number of concurrent task runs on task, block and playbook
        level. This is independent of the forks and serial settings, but
        cannot be set higher than those limits. For example, if forks is set
        to 10 and the throttle is set to 15, at most 10 hosts will be
        operated on in parallel.
    :type throttle: int

    :param vars:
        Dictionary/map of variables
    :type vars: dict
    """
    any_errors_fatal = make_attr('boolean')
    become = make_attr('boolean')
    become_exe = make_attr('string')
    become_flags = make_attr('string')
    become_method = make_attr('string')
    become_user = make_attr('string')
    check_mode = make_attr('boolean')
    collections = make_attr('index', cls=str, unique=True)
    connection = make_attr('string')
    debugger = make_attr('string')
    diff = make_attr('boolean')
    environment = make_attr('dict')
    ignore_errors = make_attr('boolean')
    ignore_unreachable = make_attr('boolean')
    module_defaults = make_attr('dict')
    name = make_attr('string')
    no_log = make_attr('boolean')
    port = make_attr('integer', validators=(PortValidator(),))
    remote_user = make_attr('string')
    run_once = make_attr('boolean')
    tags = make_attr('index', cls=str, unique=True)
    throttle = make_attr('integer')
    vars = make_attr('dict')


class Delegate(object):
    """The ``Delegate`` class provides attributes for delegation

    This class provides a consistent implementation of attributes that
    are only implemented for ``Task`` and ``Role`` but not ``Play``.  This
    class should be treated as a mixin class and does not provide a
    standalone implementation.

    :param delegate_facts:
        Boolean that allows you to apply facts to a delegated host
        instead of inventory_hostname.
    :type delegate_fats: bool

    :param delegate_to:
        Host to execute task instead of the target (inventory_hostname).
        Connection vars from the delegated host will also be used for
        the task.
    :type delegate_to: str
    """
    delegate_facts = make_attr('boolean')
    delegate_to = make_attr('string')


class Conditional(object):
    """ The ``Conditional`` class provides attributes for conditionals

    This class provides a consistent implementation for using conditionals
    with ``Task``, and ``Role`` classes.  This class is a mixin class and
    does not provide a standalone implementation.

    :param when:
        Conditional expression, determines if an iteration of a task
        is run or not.
    :type when: list
    """
    when = make_attr('list', coerce=True)


class Playbook(IndexContainer):
    """The ``Playbook`` class is the top most class for Ansible Playbooks

    This class provides the topmost implementation for organizing
    plays, tasks and roles.  It provides a complete Ansible Playbook
    implementation.

    To create a new Ansible playbook, start by creating an instance
    of ``Playbook`` and create a new ``Play``.

    >>> from ansible_runner.playbook import Playbook
    >>> pb = Playbook()
    >>> play = pb.new()

    Once the playbook has been fully configured, use the ``serialize()``
    instance method to generate a JSON representation of the Ansible
    playbook that can be used with the ``ansible-playbook`` command.
    """

    def __init__(self, *args, **kwargs):
        super(Playbook, self).__init__(
            load_module('ansible_runner.playbook.plays:Play')
        )
