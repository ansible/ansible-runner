import os
import sys
import types
import pytest

# On Windows test runner environments, some Unix-only modules like fcntl and pwd
# are not available and ansible_runner imports them at module import time. Create
# lightweight stubs so the package can be imported for this focused unit test.
if 'fcntl' not in sys.modules:
    fcntl_stub = types.ModuleType('fcntl')
    def _lockf(fd, op, length=0):
        return None
    fcntl_stub.lockf = _lockf
    fcntl_stub.LOCK_EX = 1
    fcntl_stub.LOCK_UN = 2
    sys.modules['fcntl'] = fcntl_stub
if 'pwd' not in sys.modules:
    pwd_stub = types.ModuleType('pwd')
    def getpwuid(uid):
        return types.SimpleNamespace(pw_name='user')
    pwd_stub.getpwuid = getpwuid
    sys.modules['pwd'] = pwd_stub

from ansible_runner.config._base import BaseConfig, BaseExecutionMode


def test_wrap_args_for_containerization_adds_ssh_automount(tmp_path, monkeypatch):
    # Setup a minimal BaseConfig instance
    bc = BaseConfig(private_data_dir=str(tmp_path))
    # Ensure process_isolation_executable contains 'podman' so _handle_automounts path is exercised
    bc.process_isolation = True
    bc.process_isolation_executable = 'podman'
    # Set a dummy container image so prepare_env will not raise
    bc.container_image = 'quay.io/ansible/ansible-runner:latest'
    # Prepare env so attributes like runner_mode and env are initialized
    bc.prepare_env('pexpect')
    # Create a fake ssh auth sock and HOME/.ssh
    fake_sock = tmp_path / 'ssh-agent.sock'
    fake_sock.write_text('')
    monkeypatch.setenv('SSH_AUTH_SOCK', str(fake_sock))
    monkeypatch.setenv('HOME', str(tmp_path))
    # Ensure ~/.ssh exists
    ssh_dir = tmp_path / '.ssh'
    ssh_dir.mkdir()

    # Call wrap_args_for_containerization with ANSIBLE_COMMANDS
    args = ['ansible-playbook', 'playbook.yml']
    cmdline_args = ['playbook.yml']

    new_args = bc.wrap_args_for_containerization(args, BaseExecutionMode.ANSIBLE_COMMANDS, cmdline_args)

    # podman should be the first element (process isolation executable)
    assert new_args[0] == 'podman'

    # Find the SSH_AUTH_SOCK env mapping (-e, 'SSH_AUTH_SOCK=/home/runner/...')
    env_pairs = [x for x in new_args if x.startswith('SSH_AUTH_SOCK=')]
    assert env_pairs, f"SSH_AUTH_SOCK env entry missing in: {new_args}"

    # Find a -v mount entry that contains the host tmp_path (platform path formats differ)
    host_path_str = str(tmp_path)
    found_mount = any(
        (new_args[i] == '-v' and host_path_str in new_args[i + 1])
        for i in range(len(new_args) - 1)
    )
    assert found_mount, f"Host tmp_path not found in any -v mount in: {new_args}"


def test_wrap_args_allows_nonexistent_tmp_ssh_socket(tmp_path, monkeypatch):
    """Ensure that when SSH_AUTH_SOCK points to a /tmp/ssh-*/agent.* path that
    does not exist at prepare time, the wrapper will still include a -v mount
    for that socket (the conservative heuristic).
    """
    # This test exercises Unix /tmp/ssh-* socket heuristic. Skip on Windows
    # because path normalization yields platform-specific host paths and the
    # test assertions below are written for Unix-style sockets.
    if os.name == 'nt':
        pytest.skip('Skipping ssh socket mount heuristic test on Windows')

    bc = BaseConfig(private_data_dir=str(tmp_path))
    bc.process_isolation = True
    bc.process_isolation_executable = 'podman'
    bc.container_image = 'quay.io/ansible/ansible-runner:latest'
    bc.prepare_env('pexpect')

    # Use a socket path that does not exist but starts with /tmp/ssh-
    fake_sock_path = '/tmp/ssh-abcd/agent.9999'
    # ensure it does not exist on the test host
    try:
        if os.path.exists(fake_sock_path):
            # if it exists (unlikely on CI), skip this test as the premise is invalid
            pytest.skip(f"Unexpected existing path: {fake_sock_path}")
    except Exception:
        # be defensive on platforms where os.path.exists may raise
        pass

    monkeypatch.setenv('SSH_AUTH_SOCK', fake_sock_path)
    monkeypatch.setenv('HOME', str(tmp_path))

    args = ['ansible-playbook', 'playbook.yml']
    cmdline_args = ['playbook.yml']

    new_args = bc.wrap_args_for_containerization(args, BaseExecutionMode.ANSIBLE_COMMANDS, cmdline_args)

    # Ensure SSH_AUTH_SOCK env mapping is present
    env_pairs = [x for x in new_args if x.startswith('SSH_AUTH_SOCK=')]
    assert env_pairs, f"SSH_AUTH_SOCK env entry missing in: {new_args}"

    # Ensure there's a -v mount mentioning the ssh socket path. Normalize
    # path separators so this works on Windows CI too.
    found_socket_mount = False
    for i in range(len(new_args) - 1):
        if new_args[i] == '-v':
            mounted = new_args[i + 1]
            norm = mounted.replace('\\', '/')
            if 'ssh-' in norm or 'agent.' in norm:
                found_socket_mount = True
                break

    assert found_socket_mount, f"Expected -v mount for ssh socket in: {new_args}"
