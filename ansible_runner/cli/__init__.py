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
import sys
import glob
import argparse
import textwrap
import importlib

from ansible_runner.exceptions import AnsibleRunnerException
from ansible_runner.exceptions import AnsibleRunnerCliError

import pkg_resources
VERSION = pkg_resources.require("ansible_runner")[0].version


def print_common_usage():
    print(textwrap.dedent("""
        These are common Ansible Runner commands:

            playbook    Execute an Ansible playbook using Runner
            module      Execute an Ansible module using Runner
            role        Directly apply an Ansible role to a set of hosts

        `ansible-runner --help` list of optional command line arguments
    """))


def print_usage():
    print(textwrap.dedent("""
        usage: ansible-runner [--version] [--help]
                              <command> [<args>]
    """))


def main(args=None):
    """Main entry point for ansible-runner executable

    When the ```ansible-runner``` command is executed, this function
    is the main entry point that is called and executed.

    :param sys_args: List of arguments to be parsed by the parser
    :type sys_args: list

    :returns: an instance of SystemExit
    :rtype: SystemExit
    """
    parser = argparse.ArgumentParser(
        description="Use 'ansible-runner' (with no arguments) to see basic usage",
    )

    parser.add_argument(
        '--version',
        action='version',
        version="ansible-runner v{}".format(VERSION)
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    for item in glob.glob(os.path.join(os.path.dirname(__file__), "*.py")):
        name = os.path.basename(item).split('.')[0]
        mod = importlib.import_module('ansible_runner.cli.{}'.format(name))
        if hasattr(mod, 'init'):
            subparser = subparsers.add_parser(name)
            subparser.set_defaults(mod=mod)
            mod.init(subparser)

    rc = 128

    if len(sys.argv) == 1:
        parser.print_usage()
        print_common_usage()
        parser.exit(status=0)

    if args is None:
        args = sys.argv[1:]

    options = None

    for i, item in enumerate(args):
        if item == "--":
            options = args[i + 1:]
            args = args[:i]
            break

    try:
        args = parser.parse_args(args)
        setattr(args, '_options', options)

        rc = args.mod.run(args)

        if rc != 0:
            raise AnsibleRunnerCliError(args.subcommand)

    except AnsibleRunnerException as exc:
        print(exc)

    return rc
