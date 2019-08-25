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
from __future__ import print_function

import os

from pytest import raises

from ansible_runner.cli import main

from .helpers import ensure_removed


HERE = os.path.abspath(os.path.dirname(__file__))
ROLE_PATH = os.path.join(HERE, 'project/roles')
PROJECT_PATH = os.path.join(HERE, 'project')


def test_module_run():
    rc = main(['module', 'ping', 'localhost'])
    assert rc == 0


def test_module_raises_exception():
    with raises(SystemExit):
        main(['module'])


def test_role_run():
    rc = main(['role', 'benthomasson.hello_role', 'localhost',
               '--roles-path', ROLE_PATH,
               '--connection', 'local'])
    assert rc == 0


def test_role_raises_exception():
    with raises(SystemExit):
        main(['role'])


def test_playbook_run():
    try:
        rc = main(['playbook', 'start', '--private-data-dir', PROJECT_PATH])
        assert rc == 0
    finally:
        ensure_removed('test/integration/project/artifacts')
        ensure_removed('test/integration/project/daemon.log')


def test_playbook_raises_exception():
    with raises(SystemExit):
        main(['playbook'])
