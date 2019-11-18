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
import pytest

from ansible_runner.playbook.tasks import Task
from ansible_runner.playbook.tasks import Block
from ansible_runner.playbook.tasks import Tasks
from ansible_runner.playbook.tasks import TasksContainer


def test_task_init_with_action():
    task = {'action': 'test', 'args': {'one': 1, 'two': 2}, 'name': 'test'}
    t = Task(**task)
    assert t.serialize() == {'test': {'one': 1, 'two': 2}, 'name': 'test'}


def test_task_init_without_action():
    task = {'test': {'one': 1, 'two': 2}, 'name': 'test'}
    t = Task(**task)
    serialized_task = {'test': {'one': 1, 'two': 2}, 'name': 'test'}
    assert t.serialize() == serialized_task


def test_task_action_mutually_exclusive():
    t = Task(action='test')
    assert t.action == 'test'
    assert t.local_action is None
    t.local_action = 'test'
    assert t.action is None
    assert t.local_action == 'test'


def test_task_action_is_required():
    with pytest.raises(ValueError):
        Task()


def test_task_serialization_deserialization():
    t = Task(action='test', args={'one': 1})
    data = t.serialize()
    assert data == {'test': {'one': 1}}
    t1 = Task(**data)
    assert t == t1
    t2 = Task(action='test')
    t2.deserialize(data)
    assert t == t2


def test_task_serialization_with_local_action():
    t = Task(local_action='test', args={'one': 1})
    data = t.serialize()
    assert data == {'test': {'one': 1}}


def test_task_invalid_type():
    c = TasksContainer(Task)
    with pytest.raises(TypeError):
        c.append(str)


def test_taskcontainer_returns_task():
    c = TasksContainer(Task)

    assert isinstance(c.new(action='test'), Task)
    assert isinstance(c.new(local_action='test'), Task)
    assert isinstance(c.new(), Block)


def test_tasks_attribute():
    a = Tasks()
    o = a([])
    assert isinstance(o, TasksContainer)
