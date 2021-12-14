default_process_isolation_executable = 'podman'
default_container_image = 'quay.io/ansible/ansible-runner:devel'

# values passed to tempfile.mkdtemp to generate a private data dir
# when user did not provide one
AUTO_CREATE_NAMING = '.ansible-runner-'
AUTO_CREATE_DIR = None
