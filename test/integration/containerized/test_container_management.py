import os
import shutil
import time

import pytest

from ansible_runner.interface import run


def is_running(cli, container_runtime_installed, container_name):
    cmd = [container_runtime_installed, 'ps', '-aq', '--filter', 'name=ansible_runner_foo_bar']
    r = cli(cmd, bare=True)
    output = '{}{}'.format(r.stdout, r.stderr)
    print(' '.join(cmd))
    print(output)
    return output.strip()


class CancelStandIn:
    def __init__(self, runtime, cli, delay=0.2):
        self.runtime = runtime
        self.cli = cli
        self.delay = 0.2
        self.checked_running = False
        self.start_time = None

    def cancel(self):
        # Avoid checking for some initial delay to allow container startup
        if not self.start_time:
            self.start_time = time.time()
        if time.time() - self.start_time < self.delay:
            return False
        # guard against false passes by checking for running container
        if not self.checked_running:
            for i in range(5):
                if is_running(self.cli, self.runtime, 'ansible_runner_foo_bar'):
                    break
                time.sleep(0.2)
            else:
                print(self.cli([self.runtime, 'ps', '-a'], bare=True).stdout)
                raise Exception('Never spawned expected container')
            self.checked_running = True
        # Established that container was running, now we cancel job
        return True


@pytest.mark.serial
def test_cancel_will_remove_container(test_data_dir, container_runtime_installed, cli):
    private_data_dir = os.path.join(test_data_dir, 'sleep')

    env_dir = os.path.join(private_data_dir, 'env')
    if os.path.exists(env_dir):
        shutil.rmtree(env_dir)

    cancel_standin = CancelStandIn(container_runtime_installed, cli)

    res = run(
        private_data_dir=private_data_dir,
        playbook='sleep.yml',
        settings={
            'process_isolation_executable': container_runtime_installed,
            'process_isolation': True
        },
        cancel_callback=cancel_standin.cancel,
        ident='foo?bar'  # question mark invalid char, but should still work
    )
    assert res.rc == 254, res.stdout.read()
    assert res.status == 'canceled'

    assert not is_running(
        cli, container_runtime_installed, 'ansible_runner_foo_bar'
    ), 'Found a running container, they should have all been stopped'
