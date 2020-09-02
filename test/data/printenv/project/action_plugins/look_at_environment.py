from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.action import ActionBase

import os


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars)
        result['changed'] = result['failed'] = False
        result['msg'] = ''
        env_dict = dict(os.environ)
        result['printenv'] = '\n'.join(
            '{0}={1}'.format(k, v) for k, v in env_dict.items()
        )
        result['environment'] = env_dict
        result['cwd'] = os.getcwd()
        return result
