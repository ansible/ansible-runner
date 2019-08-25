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
import os
import json

from ansible_runner import interface
from ansible_runner.helpers import tempdir
from ansible_runner.cli.common import add_ansible_group


def init(parser):

    parser.add_argument(
        "name",
        help="the name of the role to directly invoke"
    )

    parser.add_argument(
        "hosts",
        help="the set of host to invoke the role against"
    )

    group = parser.add_argument_group(
        "Ansible Runner Role Options",
        "configuration options for directly executing Ansible roles"
    )

    group.add_argument(
        "--roles-path",
        help="path used to locate the role to be executed (default=None)"
    )

    group.add_argument(
        "--skip-facts",
        action="store_true",
        help="disable fact collection when the role is executed (default=False)"
    )

    add_ansible_group(parser)


def run(ns):
    with tempdir() as tmp:

        play = [{
            'hosts': ns.hosts or 'all',
            'gather_facts': ns.skip_facts,
            'roles': [{'name': ns.name}]
        }]

        os.makedirs(os.path.join(tmp, 'project'))
        with open(os.path.join(tmp, 'project/main.yml'), 'w') as f:
            f.write(json.dumps(play))

        os.makedirs(os.path.join(tmp, 'inventory'))
        with open(os.path.join(tmp, 'inventory/hosts'), 'w') as f:
            for item in ns.hosts.split(','):
                f.write(item)

        if ns.roles_path:
            os.makedirs(os.path.join(tmp, 'env'))
            with open(os.path.join(tmp, 'env/envvars'), 'w') as f:
                f.write(json.dumps({'ANSIBLE_ROLES_PATH': ns.roles_path}))

        runner = interface.run(**{
            'private_data_dir': tmp,
            'role': ns.name,
            'host_pattern': ns.hosts,
            'quiet': True,
            'connection': ns.connection
        })

        for line in runner.stdout:
            print(line.strip())

        print(runner.status)
        print(runner.stdout.read())

        return runner.rc
