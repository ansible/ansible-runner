default_process_isolation_executable = 'podman'
default_container_image = 'quay.io/ansible/ansible-runner:devel'
registry_auth_prefix = 'ansible_runner_registry_'

# for ansible-runner worker cleanup command
GRACE_PERIOD_DEFAULT = 60  # minutes

# values passed to tempfile.mkdtemp to generate a private data dir
# when user did not provide one
AUTO_CREATE_NAMING = '.ansible-runner-'
AUTO_CREATE_DIR = None
