import time

from uuid import uuid4

from ansible_runner.interface import run


def is_running(cli, container_runtime_installed, container_name):
    cmd = [container_runtime_installed, 'ps', '-aq', '--filter', f'name={container_name}']
    r = cli(cmd, bare=True)
    output = '{}{}'.format(r.stdout, r.stderr)
    print(' '.join(cmd))
    print(output)
    return output.strip()


class CancelStandIn:
    def __init__(self, runtime, cli, container_name, delay=0.2):
        self.runtime = runtime
        self.cli = cli
        self.delay = 0.2
        self.container_name = container_name
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
                if is_running(self.cli, self.runtime, self.container_name):
                    break
                time.sleep(0.2)
            else:
                print(self.cli([self.runtime, 'ps', '-a'], bare=True).stdout)
                raise Exception('Never spawned expected container')
            self.checked_running = True
        # Established that container was running, now we cancel job
        return True


def test_cancel_will_remove_container(project_fixtures, container_runtime_installed, cli):
    private_data_dir = project_fixtures / 'sleep'
    ident = uuid4().hex[:12]
    container_name = f'ansible_runner_{ident}'

    cancel_standin = CancelStandIn(container_runtime_installed, cli, container_name)

    res = run(
        private_data_dir=private_data_dir,
        playbook='sleep.yml',
        settings={
            'process_isolation_executable': container_runtime_installed,
            'process_isolation': True
        },
        cancel_callback=cancel_standin.cancel,
        ident=ident
    )
    assert res.rc == 254, res.stdout.read()
    assert res.status == 'canceled'

    assert not is_running(
        cli, container_runtime_installed, container_name
    ), 'Found a running container, they should have all been stopped'
