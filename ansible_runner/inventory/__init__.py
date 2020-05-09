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
from ansible_runner.helpers import make_attr
from ansible_runner.types.validators import PortValidator


class AnsibleVars(object):
    """Base class with Ansible inventory attributes

    This class provides a common implementation of Ansible
    inventory attributes.  This class is designed to be a mixin
    and should not need to be directly instantiated.

    :param ansible_connection:
        Connection type to the host. This can be the name of any of
        Ansible’s connection plugins.
    :type ansible_connection: str

    :param ansible_port:
        The connection port number, if not the default (22 for ssh)
    :type ansible_port: int

    :param ansible_user:
        The user name to use when connecting to the host
    :type ansible_user: str

    :param ansible_password:
        The password to use to authenticate to the host
    :type ansible_password: str

    :param ansible_ssh_private_key_file:
        Private key file used by ssh. Useful if using multiple keys and
        you don’t want to use SSH agent.
    :type ansible_ssh_private_key_file: str

    :param ansible_ssh_common_args:
        This setting is always appended to the default command line for
        sftp, scp, and ssh. Useful to configure a ProxyCommand for a
        certain host (or group).
    :type ansible_ssh_common_args: str

    :param ansible_sftp_extra_args:
        This setting is always appended to the default sftp command line.
    :type ansible_sftp_extra_args: str

    :param ansible_scp_extra_args:
        This setting is always appended to the default scp command line.
    :type ansible_scp_extra_args: str

    :param ansible_ssh_pipelining:
        Determines whether or not to use SSH pipelining. This can
        override the pipelining setting in ansible.cfg.
    :type ansible_ssh_pipelining: bool

    :param ansible_ssh_executable:
        This setting overrides the default behavior to use the system
        ssh. This can override the ssh_executable setting in ansible.cfg.
    :type ansible_ssh_executable: str

    :param ansible_become:
        Equivalent to ansible_sudo or ansible_su, allows to force
        privilege escalation
    :type ansible_become: bool

    :param ansible_become_method:
        Allows to set privilege escalation method
    :type ansible_become_method: str

    :param ansible_become_user:
        Equivalent to ansible_sudo_user or ansible_su_user, allows to
        set the user you become through privilege escalation
    :type ansible_become_user: str

    :param ansible_become_password:
        Equivalent to ansible_sudo_password or ansible_su_password, allows
        you to set the privilege escalation password
    :type ansible_become_password: str

    :param ansible_become_exe:
        Equivalent to ansible_sudo_exe or ansible_su_exe, allows you to
        set the executable for the escalation method selected
    :type ansible_become_exec: str

    :param ansible_become_flags:
        Equivalent to ansible_sudo_flags or ansible_su_flags, allows you
        to set the flags passed to the selected escalation method. This
        can be also set globally in ansible.cfg in the sudo_flags option
    :type ansible_become_flags: str

    :param ansible_shell_type:
        The shell type of the target system. You should not use this
        setting unless you have set the ansible_shell_executable to a
        non-Bourne (sh) compatible shell. By default commands are formatted
        using sh-style syntax. Setting this to csh or fish will cause
        commands executed on target systems to follow those shell’s
        syntax instead.
    :type ansible_shell_type: str

    :param ansible_python_interpreter:
        The target host python path. This is useful for systems with
        more than one Python or not located at /usr/bin/python such as
        *BSD, or where /usr/bin/python is not a 2.X series Python.
    :type ansible_python_interpreter: str

    :param ansible_shell_executable:
        This sets the shell the ansible controller will use on the target
        machine, overrides executable in ansible.cfg which defaults to
        /bin/sh. You should really only change it if is not possible to
        use /bin/sh (i.e. /bin/sh is not installed on the target machine
        or cannot be run from sudo.).
    :type ansible_shell_executable: str

    :param ansible_docker_extra_args:
        Could be a string with any additional arguments understood by
        Docker, which are not command specific. This parameter is mainly
        used to configure a remote Docker daemon to use.
    :type ansible_docker_extra_args: str

    :param ansible_network_os:
        Sets the target device network OS value which allows the
        connection plugin to load the current plugin for the network
        device.
    :type ansible_network_os: str
    """

    ansible_connection = make_attr('string')
    ansible_port = make_attr('integer', validators=(PortValidator(),))
    ansible_user = make_attr('string', aliases=('ansible_ssh_user',))
    ansible_password = make_attr('string', aliases=('ansible_ssh_pass',))
    ansible_ssh_private_key_file = make_attr('string')
    ansible_ssh_common_args = make_attr('string')
    ansible_sftp_extra_args = make_attr('string')
    ansible_scp_extra_args = make_attr('string')
    ansible_ssh_pipelining = make_attr('boolean')
    ansible_ssh_executable = make_attr('string')
    ansible_become = make_attr('boolean')
    ansible_become_method = make_attr('string')
    ansible_become_user = make_attr('string')
    ansible_become_password = make_attr('string')
    ansible_become_exe = make_attr('string')
    ansible_become_flags = make_attr('string')
    ansible_shell_type = make_attr('string')
    ansible_python_interpreter = make_attr('string')
    ansible_shell_executable = make_attr('string')
    ansible_docker_extra_args = make_attr('string')
    ansible_network_os = make_attr('string')


class Inventory(Object):
    """Provides an implementation of Ansible inventory

    This class provides a top level object for building an
    inventory that can be used by Ansible.  The inventory object
    provides attributes for creating hosts, groups (children) and
    host variables.

    This model provided by this class implements the Ansible
    YAML inventory plugin.  See the Ansible documentation for
    details on the final inventory structure.

    Use the inventory class to create a new inventory.

    >>> from ansible_runner.inventory import Inventory
    >>> inventory = Inventory()
    >>> host = inventory.hosts.new('localhost')
    >>> host.ansible_user = 'admin'
    >>> host['key'] = 'value'
    >>> child = inventory.children.new('all')
    >>> child['key'] = 'value'

    The inventory class also supports assiging variables directly
    to the object.

    >>> inv['key'] = 'value'

    :param hosts:
        List of hosts in the top level inventory
    :type hosts: ``MapContainer``

    :param children:
        List of children supported for this inventory
    :type children: ``MapContainer``

    :param vars:
        Arbitrary set of key/value pairs stored in inventory
    :type vars: dict
    """

    hosts = make_attr('map', cls='ansible_runner.inventory.hosts:Host')
    children = make_attr('map', cls='ansible_runner.inventory.children:Child')
    vars = make_attr('dict')

    def __init__(self, **kwargs):
        kwargs = kwargs.get('all', {})
        super(Inventory, self).__init__(**kwargs)

    def serialize(self):
        """Overrides the implementation from ``Object``

        This method overrides the base class implementation to handle
        the injection of the "all" top level key in the final object
        that is returned to the caller.
        """
        obj = super(Inventory, self).serialize()
        return {'all': obj}

    def deserialize(self, ds):
        """Overrides the implementation from ``Object``

        This method overrides the base class implementation to handle
        the removal of the "all" top levelkey in the provided data
        structure.
        """
        super(Inventory, self).deserialize(ds['all'])
