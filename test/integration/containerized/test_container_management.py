import os
import shutil
import time

import pytest

from ansible_runner.interface import run


@pytest.mark.serial
def test_cancel_will_remove_container(test_data_dir, container_runtime_installed, cli):
    private_data_dir = os.path.join(test_data_dir, 'sleep')

    env_dir = os.path.join(private_data_dir, 'env')
    if os.path.exists(env_dir):
        shutil.rmtree(env_dir)

    def is_running(container_name):
        cmd = [container_runtime_installed, 'ps', '-aq', '--filter', 'name=ansible_runner_foo_bar']
        r = cli(cmd, bare=True)
        output = '{}{}'.format(r.stdout, r.stderr)
        print(' '.join(cmd))
        print(output)
        return output.strip()

    def cancel():
        # guard against false passes by checking for running container
        for i in range(5):
            if is_running('ansible_runner_foo_bar'):
                break
            time.sleep(0.2)
        else:
            print(cli([container_runtime_installed, 'ps', '-a'], bare=True).stdout)
            raise Exception('Never spawned expected container')
        return True

    res = run(
        private_data_dir=private_data_dir,
        playbook='sleep.yml',
        settings={
            'process_isolation_executable': container_runtime_installed,
            'process_isolation': True
        },
        cancel_callback=cancel,
        ident='foo?bar'  # question mark invalid char, but should still work
    )
    assert res.rc == 254, res.stdout.read()
    assert res.status == 'canceled'

    assert not is_running('ansible_runner_foo_bar'), 'Found a running container, they should have all been stopped'
