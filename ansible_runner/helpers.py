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
import re
import shlex
import importlib

from subprocess import Popen, PIPE

from six import binary_type
from six import string_types


PYTHON_RESERVED = frozenset([
    'and', 'assert', 'in', 'del', 'else', 'raise', 'from', 'if', 'continue',
    'not', 'pass', 'finally', 'while', 'yield', 'is', 'as', 'break', 'return',
    'elif', 'except', 'def', 'global', 'import', 'for', 'or', 'print',
    'lambda', 'with', 'class', 'try', 'exec'
])


def to_bytes(o):
    """Convert value to bytes

    :param o: the value to be converted:
    :type o: a string type

    :returns: a bytes encoded object
    :rtype: bytes
    """
    if isinstance(o, binary_type):
        return o
    return o.encode('utf-8')


def to_list(o):
    """Convert value to a list

    :param o: any valid object
    :type o: object

    :returns: a list object
    :rtype: list
    """
    if isinstance(o, (list, tuple, set)):
        return list(o)
    elif o is not None:
        return [o]
    else:
        return list()


def isvalidattrname(v):
    """Checks if value is a valid method name

    This function will check the name of the argument and
    return either True if the value can be used as an instance
    method or False if can cannot be used.

    :param v: the value to check
    :type v: str

    :returns: True or False
    :rtype: bool
    """
    if v in PYTHON_RESERVED:
        raise ValueError("value is a reserved word")
    if not v[0].isalpha():
        raise ValueError("name must start with an alpha character")
    return True


def get_ansible_version():
    """Returns the current version of Ansible

    This function will extract the version of Ansible based on
    the command `ansible --version` and return the version in
    x.y.z format

    :returns: string representation of the version
    :rtype: str
    """
    p = Popen(shlex.split("ansible --version"),
              stdin=PIPE, stdout=PIPE, stderr=PIPE)

    out, err = p.communicate()
    match = re.match(b"ansible (.+)", to_bytes(out))
    return match.group(1)


def get_ansible_role_paths():
    """Retrieves the Ansible Roles path

    This function will return the list of role paths to check for
    roles to be installed into.  This is done using the command
    `ansible-galaxy list`

    :returns: a list of paths
    :rtype: list
    """
    p = Popen(shlex.split("ansible-galaxy list"),
              stdin=PIPE, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    return re.findall(b"# (.+)", to_bytes(out))


def get_role_path(name):
    """Returns the full path to the role

    This function will attempt to find the role provided by
    name and return the full path.  If the role is not found
    this function will return None

    :param name: the name of the role to find
    :type name: sti

    :returns: the full path to the role
    :rtype: str
    """
    name = to_bytes(name)
    for item in get_ansible_role_paths():
        for parent, children, _ in os.walk(item):
            if name in children:
                return os.path.join(parent, name)


def load_module(name):
    """Loads the named module

    :param name: the fully qualified module name
    :type name: str

    :returns: the loaded class from the module
    :rtype: object
    """
    mod, cls = name.split(':') if ':' in name else (name, None)
    mod = importlib.import_module(mod)
    if cls is not None and cls in dir(mod):
        mod = getattr(mod, cls)
    return mod


def make_attr(attrtype, **kwargs):
    """Helper function to load attributes for Objects

    Loads the attribute class by name and sets the default
    value for `serialize_when` to `SERIALIZE_WHEN_PRESENT` if
    a more specific value is not specified.

    :param attrype: the attribute type to create
    :type attrtype: ``str``

    :param kwargs: keyword arguments passed to the attribute class

    :returns: an instance of the attribute class
    :rtype: ``ansible_runner.types.attrs.Attribute``
    """
    attrs = load_module('ansible_runner.types.attrs')

    if kwargs.pop('lazy', None) is True:
        kwargs['attrtype'] = attrtype
        attrtype = 'ansible_runner.types.attrs:LazyAttribute'

    if isinstance(attrtype, string_types):
        if ':' not in attrtype:
            attrsdir = dir(attrs)
            attributes = dict(zip([n.lower() for n in attrsdir], attrsdir))
            cls = getattr(attrs, attributes[attrtype])
        else:
            cls = load_module(attrtype)
    else:
        cls = attrtype

    if 'required' not in kwargs:
        kwargs['serialize_when'] = attrs.SERIALIZE_WHEN_PRESENT

    return cls(**kwargs)
