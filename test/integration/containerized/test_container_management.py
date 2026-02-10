import os
import pty
import time
import json

from glob import glob
from uuid import uuid4

import pytest

from ansible_runner.interface import run, run_command


@pytest.mark.test_all_runtimes
def is_running(cli, runtime, container_name):
    cmd = [runtime, 'ps', '-aq', '--filter', f'name={container_name}']
    r = cli(cmd, bare=True)
    output = f'{r.stdout}{r.stderr}'
    print(' '.join(cmd))
    print(output)
    return output.strip()


class CancelStandIn:
    def __init__(self, runtime, cli, container_name, delay=0.2):
        self.runtime = runtime
        self.cli = cli
        self.delay = delay
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
            for _ in range(5):
                if is_running(self.cli, self.runtime, self.container_name):
                    break
                time.sleep(0.2)
            else:
                print(self.cli([self.runtime, 'ps', '-a'], bare=True).stdout)
                raise Exception('Never spawned expected container')
            self.checked_running = True
        # Established that container was running, now we cancel job
        return True


@pytest.mark.test_all_runtimes
def test_cancel_will_remove_container(project_fixtures, runtime, cli, container_image):
    private_data_dir = project_fixtures / 'sleep'
    ident = uuid4().hex[:12]
    container_name = f'ansible_runner_{ident}'

    cancel_standin = CancelStandIn(runtime, cli, container_name)

    res = run(
        private_data_dir=private_data_dir,
        playbook='sleep.yml',
        settings={
            'process_isolation_executable': runtime,
            'process_isolation': True,
            'container_image': container_image,
        },
        cancel_callback=cancel_standin.cancel,
        ident=ident
    )
    with res.stdout as f:
        assert res.rc == 254, f.read()
    assert res.status == 'canceled'

    assert not is_running(
        cli, runtime, container_name
    ), 'Found a running container, they should have all been stopped'


@pytest.mark.test_all_runtimes
def test_non_owner_install(mocker, project_fixtures, runtime, container_image):
    """Simulates a run on a conputer where ansible-runner install is not owned by current user"""
    mocker.patch('ansible_runner.utils.is_dir_owner', return_value=False)

    private_data_dir = project_fixtures / 'debug'
    res = run(
        private_data_dir=private_data_dir,
        playbook='debug.yml',
        settings={
            'process_isolation_executable': runtime,
            'process_isolation': True,
            'container_image': container_image,
        }
    )
    with res.stdout as f:
        stdout = f.read()
    assert res.rc == 0, stdout
    assert res.status == 'successful'


@pytest.mark.test_all_runtimes
def test_invalid_registry_host(tmp_path, runtime):
    pdd_path = tmp_path / 'private_data_dir'
    pdd_path.mkdir()
    private_data_dir = str(pdd_path)

    image_name = 'quay.io/kdelee/does-not-exist'

    res = run(
        private_data_dir=private_data_dir,
        playbook='ping.yml',
        settings={
            'process_isolation_executable': runtime,
            'process_isolation': True,
            'container_image': image_name,
            'container_options': ['--user=root', '--pull=always'],
        },
        container_auth_data={'host': 'somedomain.invalid', 'username': 'foouser', 'password': '349sk34', 'verify_ssl': False},
        ident='awx_123'
    )
    assert res.status == 'failed'
    assert res.rc > 0
    assert os.path.exists(res.config.registry_auth_path)

    with res.stdout as f:
        result_stdout = f.read()
    auth_file_path = os.path.join(res.config.registry_auth_path, 'config.json')
    registry_conf = os.path.join(res.config.registry_auth_path, 'registries.conf')
    error_msg = 'access to the requested resource is not authorized'
    if runtime == 'podman':
        assert image_name in result_stdout
        error_msg = 'unauthorized'
        auth_file_path = res.config.registry_auth_path
        registry_conf = os.path.join(os.path.dirname(res.config.registry_auth_path), 'registries.conf')
    assert error_msg in result_stdout

    with open(auth_file_path, 'r') as f:
        content = f.read()
        assert res.config.container_auth_data['host'] in content
        assert 'Zm9vdXNlcjozNDlzazM0' in content  # the b64 encoded of username and password

    assert os.path.exists(registry_conf)
    with open(registry_conf, 'r') as f:
        assert f.read() == '\n'.join([
            '[[registry]]',
            'location = "somedomain.invalid"',
            'insecure = true'
        ])


@pytest.mark.test_all_runtimes
def test_registry_auth_file_cleanup(tmp_path, cli, runtime):
    pdd_path = tmp_path / 'private_data_dir'
    pdd_path.mkdir()
    private_data_dir = str(pdd_path)

    auth_registry_glob = '/tmp/ansible_runner_registry_*'
    registry_files_before = set(glob(auth_registry_glob))

    settings_data = {
        'process_isolation_executable': runtime,
        'process_isolation': True,
        'container_image': 'quay.io/kdelee/does-not-exist',
        'container_options': ['--user=root', '--pull=always'],
        'container_auth_data': {'host': 'https://somedomain.invalid', 'username': 'foouser', 'password': '349sk34'},
    }

    env_path = pdd_path / 'env'
    env_path.mkdir()
    with env_path.joinpath('settings').open('w') as f:
        f.write(json.dumps(settings_data, indent=2))

    this_ident = str(uuid4())[:5]

    cli(['run', private_data_dir, '--ident', this_ident, '-p', 'ping.yml'], check=False)

    discovered_registry_files = set(glob(auth_registry_glob)) - registry_files_before
    for file_name in discovered_registry_files:
        assert this_ident not in file_name


@pytest.mark.test_all_runtimes
def test_containerized_run_command_no_tty_when_input_fd_is_not_a_terminal(tmp_path, runtime, container_image):
    """Verify --tty is not passed to the container when input_fd is not a real TTY.

    Regression test for ansible-runner PR#1306 (partial fix for
    ansible-navigator#1607).  When ansible-navigator runs in a CI/CD
    pipeline or cron job, sys.stdin is not a terminal, yet it is still
    forwarded to ansible-runner as input_fd.  Before the fix, any truthy
    input_fd caused --tty to be added, making the container allocate a
    pseudo-terminal and polluting output with ANSI escape sequences.

    This test uses a regular file as input_fd (isatty() == False) to
    simulate the non-TTY scenario and asserts that the containerized
    ``ansible-config init`` output is clean.

    NOTE: the original issue also manifests when stdin *is* a TTY but
    stdout is redirected (``> ansible.cfg``).  That scenario is not
    covered here because it requires a different fix (e.g. checking
    output_fd.isatty() or handling it on the navigator side).
    """
    input_path = tmp_path / 'stdin.txt'
    output_path = tmp_path / 'ansible.cfg'
    error_path = tmp_path / 'stderr.txt'
    input_path.write_text('')

    with input_path.open('r', encoding='utf-8') as input_fd, \
            output_path.open('w', encoding='utf-8') as output_fd, \
            error_path.open('w', encoding='utf-8') as error_fd:
        _, _, rc = run_command(
            executable_cmd='ansible-config',
            cmdline_args=['init'],
            input_fd=input_fd,
            output_fd=output_fd,
            error_fd=error_fd,
            private_data_dir=str(tmp_path),
            process_isolation=True,
            process_isolation_executable=runtime,
            container_image=container_image,
        )

    content = output_path.read_text(encoding='utf-8')
    assert rc == 0
    assert '[defaults]' in content
    assert '\x1b' not in content

    errors = error_path.read_text(encoding='utf-8')
    assert 'not a TTY' not in errors


@pytest.mark.test_all_runtimes
def test_containerized_run_command_no_ansi_when_stdout_redirected_but_stdin_is_tty(
    tmp_path, runtime, container_image,
):
    """Reproduce the exact ansible-navigator#1607 scenario.

    The user runs ``ansible-navigator config init -m stdout > ansible.cfg``
    from a real terminal.  ansible-navigator forwards sys.stdin (a TTY) as
    input_fd and sys.stdout (redirected to a file, not a TTY) as output_fd.

    The container must not receive --tty in this situation; otherwise
    ``ansible-config init`` detects a pseudo-terminal inside the container
    and emits ANSI escape sequences / launches a pager.

    This test uses pty.openpty() to obtain an input_fd where isatty()
    is True, while output_fd is a regular file (isatty() == False),
    matching the real-world trigger exactly.
    """
    output_path = tmp_path / 'ansible.cfg'
    error_path = tmp_path / 'stderr.txt'

    master_fd, slave_fd = pty.openpty()
    try:
        stdin_tty = os.fdopen(slave_fd, 'r')
        with output_path.open('w', encoding='utf-8') as output_fd, \
                error_path.open('w', encoding='utf-8') as error_fd:
            _, _, rc = run_command(
                executable_cmd='ansible-config',
                cmdline_args=['init'],
                input_fd=stdin_tty,
                output_fd=output_fd,
                error_fd=error_fd,
                private_data_dir=str(tmp_path),
                process_isolation=True,
                process_isolation_executable=runtime,
                container_image=container_image,
            )
        stdin_tty.close()
    finally:
        os.close(master_fd)

    content = output_path.read_text(encoding='utf-8')
    assert rc == 0
    assert '[defaults]' in content
    assert '\x1b' not in content
