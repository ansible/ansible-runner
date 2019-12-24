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
from six import iteritems

from ansible_runner.helpers import make_attr
from ansible_runner.types.attrs import Attribute
from ansible_runner.types.objects import Object
from ansible_runner.types.containers import IndexContainer
from ansible_runner.playbook import Base
from ansible_runner.playbook import Delegate
from ansible_runner.playbook import Conditional


def _injest_task(attrs, kwargs):
    newargs = {}

    if 'block' not in kwargs and \
       ('action' not in kwargs and 'local_action' not in kwargs) and kwargs:

        for key in attrs:
            value = kwargs.pop(key, None)
            if value is not None:
                newargs[key] = value

        assert len(kwargs) == 1

        for action, args in iteritems(kwargs):
            if isinstance(args, dict):
                newargs.update({'action': action, 'args': args})
            else:
                newargs.update({'action': action, 'freeform': args})

    return newargs or kwargs


class Task(Base, Delegate, Conditional, Object):
    """Model for dynamically creating Ansible Tasks

    The implementation of this class provides a model for
    creating Ansible play tasks.  A task can either be directly
    instantiated and added to a play or created from a Play
    object.

    >>> from ansible_runner.playbook.tasks import Task
    >>> t = Task(action='debug')
    >>> t.args['msg'] = 'Hello World'

    Once the task has been created, it can be added to a
    play as shown below.

    >>> from ansible_runner.playbook import Playbook
    >>> pb = Playbook()
    >>> play = pb.new()
    >>> play.tasks.append(t)

    Tasks can also be created from the play.

    >>> new_task = play.tasks.new(action='debug')

    :param action:
        The ‘action’ to execute for a task, it normally translates into
        a module or action plugin.  This attribute is mutually exclusive
        with :py:attr:`local_action`.  If both attributes are configured
        then :py:attr:`action` is preferred.
    :type: action: str

    :param args:
        A secondary way to add arguments into a task. Takes a dictionary
        in which keys map to options and values.  This attribute is mutually
        exclusive with :py:attr:`freeform`.  If both attributes are
        configured on an instance, then :py:attr:`args` is preferred.
    :type args: dict

    :param changed_when:
        Conditional expression that overrides the task’s normal
        ‘changed’ status.
    :type changed_when: str

    :param delay:
        Number of seconds to delay between retries. This setting is
        only used in combination with until.
    :type delay: int

    :param failed_when:
        Conditional expression that overrides the task’s normal
        ‘failed’ status.
    :type failed_when: str

    :param freeform:
        Single free form data value for this task.  This attribute
        is mutually exclusive with :py:attr:`args`.  If both attributes
        are provided, then :py:attr:`args` is preferred.

    :param local_action:
        Same as action but also implies delegate_to: localhost
    :type local_action: str

    :param loop:
        Takes a list for the task to iterate over, saving each list
        element into the item variable (configurable via loop_control)
    :type loop: str

    :param loop_control:
        Several keys here allow you to modify/set loop behaviour in a task.
    :type loop_control: dict

    :param notify:
        List of handlers to notify when the task returns a
        ‘changed=True’ status.
    :type notify: list

    :param poll:
        Sets the polling interval in seconds for async tasks (default 10s).
    :type poll: int

    :param register:
        Name of variable that will contain task status and module return data.
    :type register: str

    :param retries:
        Number of retries before giving up in a until loop. This setting
        is only used in combination with until.
    :type retries: int

    :param until:
        This keyword implies a ‘retries loop’ that will go on until the
        condition supplied here is met or we hit the retries limit.
    :type until: str
    """

    action = make_attr(
        'string',
        require_one_of=('action', 'local_action'),
        mutually_exclusive_group='action_group',
        mutually_exclusive_priority=1
    )
    args = make_attr(
        'dict',
        mutually_exclusive_group='arg_group',
        mutually_exclusive_priority=1

    )
    freeform = make_attr('string', mutually_exclusive_group='arg_group')
    changed_when = make_attr('string')
    delay = make_attr('integer')
    failed_when = make_attr('string')
    local_action = make_attr(
        'string',
        require_one_of=('action', 'local_action'),
        mutually_exclusive_group='action_group'
    )
    loop = make_attr('string')
    loop_control = make_attr('dict')
    notify = make_attr('list')
    poll = make_attr('integer')
    register = make_attr('string')
    retries = make_attr('integer')
    until = make_attr('string')

    def __init__(self, **kwargs):
        kwargs = _injest_task(self._attributes, kwargs)
        super(Task, self).__init__(**kwargs)

    def serialize(self):
        obj = super(Task, self).serialize()

        if 'action' in obj:
            action = obj.pop('action')

        elif 'local_action' in obj:
            action = obj.pop('local_action')

        if 'args' in obj:
            args = obj.pop('args')
        elif 'freeform' in obj:
            args = obj.pop('freeform')
        else:
            args = {}

        obj.update({action: args})

        return obj

    def deserialize(self, ds):
        super(Task, self).deserialize(_injest_task(self._attributes, ds))


class Block(Base, Delegate, Conditional, Object):
    """Represents a Block entry in a Task list

    This class will create an instance of a ``Block`` object that
    can be inserted into an Ansible play task list.  This class
    can be directly instantiated or created from a ``Play`` object.

    >>> from ansible_runner.playbook.tasks import Block
    >>> b = Block()
    >>> block = b.block.new(action='debug')
    >>> block.args['msg'] = 'Hello World'
    >>> rescue = b.resuce.new(action='debug')
    >>> rescue.args['msg'] = 'Hello World'

    Block objects can also be created directly from the Ansible
    playook instance as well.

    >>> from ansible_runner.playbook import Playbook
    >>> pb = Playbook()
    >>> play = pb.new()
    >>> block_entry = play.tasks.new()
    >>> task_block = block_entry.block.new(action='debug')
    >>> task_block.args['msg'] = 'Hello World'
    >>> rescue_block = block_entry.rescue.new(action='debug')
    >>> rescue_block.args['msg'] = 'Hello World'

    :param block:
        List of tasks in a block.
    :type block: Task

    :param rescue:
        List of tasks in a block that run if there is a task error
        in the main block list.
    :type rescue: Task

    :param always:
        List of tasks, in a block, that execute no matter if there is
        an error in the block or not.
    :type rescue: Task
    """

    block = make_attr('ansible_runner.playbook.tasks:Tasks', lazy=True)
    always = make_attr('ansible_runner.playbook.tasks:Tasks', lazy=True)
    rescue = make_attr('ansible_runner.playbook.tasks:Tasks', lazy=True)


class TasksContainer(IndexContainer):
    """Implements a container to handle task items

    The implementation provides a conatiner that can handle more
    than one type.  Since a task list can contain either a ``Task``
    instance or a ``Block`` instance, a generalized ``IndexContainer``
    cannot be used.

    The ``new()`` method of this implementation will introspect the
    provided keyword arguments and return either a ``Task`` object
    or a ``Block`` object.
    """

    def __init__(self, cls, unique=False):
        self.types = (Block, Task)
        super(TasksContainer, self).__init__(cls, unique)

    def _type_check(self, value):
        if type(value) not in self.types:
            raise TypeError(
                "invalid type, expected one of {}, got {}".format(
                    "<Block>, <Task>", type(value)
                )
            )

    def new(self, **kwargs):
        """Overrides the base class method to control item creation

        The TaskContainer must support both Task and Block items
        this method will decide which type of object to created based
        on the provided keyword arguments.
        """
        kwargs = _injest_task(Task._attributes, kwargs)
        if 'action' in kwargs or 'local_action' in kwargs:
            obj = Task(**kwargs)
        else:
            obj = Block(**kwargs)
        self.append(obj)
        return obj


class Tasks(Attribute):
    """Implementation of ``Attribute`` to handle play tasks

    The ``Tasks`` object is an implementation of ``Attribute`` for
    describing the tasks property for plays.  It is basically an
    implementation of ``Index`` with a different item class
    """

    def __init__(self, **kwargs):
        self.cls = Task
        kwargs['default'] = TasksContainer(self.cls)
        super(Tasks, self).__init__(type=TasksContainer, **kwargs)

    def __call__(self, value):
        # because a Index is serialialized as a list object, the
        # deserialization process will attempt to pass a native list into the
        # this method.  this will attempt to recreate the Index object
        if isinstance(value, list):
            obj = TasksContainer(self.cls)
            obj.deserialize(value)
            value = obj
        return super(Tasks, self).__call__(value)
