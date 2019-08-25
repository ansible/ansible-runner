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
from ansible_runner import interface
from ansible_runner.helpers import tempdir
from ansible_runner.cli.common import add_ansible_group


def init(parser):

    parser.add_argument(
        "module",
        help="the name of the Ansible module to directly invoke"
    )

    parser.add_argument(
        "hosts",
        help="the host(s) to invoke the Ansible module against"
    )

    add_ansible_group(parser)


def run(ns):
    with tempdir() as tmp:

        runner = interface.run(**{
            'private_data_dir': tmp,
            'module': ns.module,
            'module_args': ' '.join(ns._options or []),
            'verbosity': ns.verbose,
            'host_pattern': ns.hosts,
            'quiet': True
        })

        for line in runner.stdout:
            print(line.strip())

        return runner.rc
