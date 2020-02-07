# Copyright (c) 2017 Ansible by Red Hat
#
# This file is part of Ansible Tower, but depends on code imported from Ansible.
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)


DOCUMENTATION = '''
    callback: minimal
    short_description: Ad hoc event dispatcher for ansible-runner
    version_added: "2.0"
    description:
        - This callback is necessary for ansible-runner to work
    type: stdout
    extends_documentation_fragment:
      - default_callback
    requirements:
      - Set as stdout in config
'''

# Tower Display Callback
from ansible_collections.runner.wrapper.plugins.module_utils.patched import AWXMinimalCallbackModule  # noqa


# In order to be recognized correctly, self.__class__.__name__ needs to
# match "CallbackModule"
class CallbackModule(AWXMinimalCallbackModule):
    pass
