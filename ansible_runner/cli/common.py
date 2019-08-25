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
import uuid

DEFAULT_RUNNER_BINARY = os.getenv('RUNNER_BINARY', None)
DEFAULT_UUID = uuid.uuid4()


def add_runner_group(parser):

    group = parser.add_argument_group(
        "Ansible Runner Options",
        "configuration options for controlling the ansible-runner "
        "runtime environment."
    )

    group.add_argument(
        "--debug",
        action="store_true",
        help="enable ansible-runner debug output logging (default=False)"
    )

    group.add_argument(
        "--logfile",
        help="log output messages to a file (default=None)"
    )

    group.add_argument(
        "-b", "--binary",
        default=DEFAULT_RUNNER_BINARY,
        help="specifies the full path pointing to the Ansible binaries "
              "(default={})".format(DEFAULT_RUNNER_BINARY)
    )

    group.add_argument(
        "-i", "--ident",
        default=DEFAULT_UUID,
        help="an identifier that will be used when generating the artifacts "
             "directory and can be used to uniquely identify a playbook run "
             "(default={})".format(DEFAULT_UUID)
    )

    group.add_argument(
        "--rotate-artifacts",
        default=0,
        type=int,
        help="automatically clean up old artifact directories after a given "
             "number have been created (default=0, disabled)"
    )

    group.add_argument(
        "--artifact-dir",
        help="optional path for the artifact root directory "
             "(default=<private_data_dir>/artifacts)"
    )

    group.add_argument(
        "--project-dir",
        help="optional path for the location of the playbook content directory "
             "(default=<private_data_dir/project)"
    )

    group.add_argument(
        "--inventory",
        help="optional path for the location of the inventory content directory "
             "(default=<private_data_dir>/inventory)"
    )

    group.add_argument(
        "--cmdline",
        help="command line options to pass to ansible-playbook at "
             "execution time (default=None)"
    )

    group.add_argument(
        "-j", "--json",
        action="store_true",
        help="output the JSON event structure to stdout instead of "
             "Ansible output (default=False)"
    )

    group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="disable all messages sent to stdout/stderr (default=False)"
    )



def add_ansible_group(parser):

    group = parser.add_argument_group(
        "Ansible Options",
        "control the ansible[-playbook] execution environment"
    )

    group.add_argument(
        "-v", "--verbose",
        action="count",
        help="matches Ansible's `-v` parameter to provide additonal "
             "output at runtime (default=None)"
    )

    group.add_argument(
        "--limit",
        help="matches Ansible's ```--limit``` parameter to further constrain "
             "the inventory to be used (default=None)"
    )

    group.add_argument(
        "--hosts",
        help="define the set of hosts to execute against (default=None) "
             "Note: this parameter only works with -m or -r"
    )

    group.add_argument(
        "--forks",
        help="matches Ansible's ```--forks``` parameter to set the number "
             "of conconurent processes (default=None)"
    )

    group.add_argument(
        "--connection",
        help="set the Ansible ```--connection``` argument when invoking "
             "the module (default=None)"
    )
