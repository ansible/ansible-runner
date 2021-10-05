import multiprocessing
import re
import uuid

from pathlib import Path


def get_cpu_count():
    # `multiprocessing` info: https://docs.python.org/3/library/multiprocessing.html
    cpu_count = multiprocessing.cpu_count()
    return cpu_count


def get_mem_in_bytes():
    try:
        with open('/proc/meminfo') as f:
            mem = f.read()
        matched = re.search(r'^MemTotal:\s+(\d+)', mem)
        if matched:
            mem_capacity = int(matched.groups()[0])
        return mem_capacity * 1024
    except FileNotFoundError:
        error = "The /proc/meminfo file could not found, memory capacity undiscoverable."
        return error


def ensure_uuid(uuid_file_path=None, mode=0o0600):
    if uuid_file_path is None:
        uuid_file_path = Path.home().joinpath('.ansible_runner_uuid')

    if uuid_file_path.exists():
        uuid_file_path.chmod(mode)
        # Read the contents of file if it already exists
        saved_uuid = uuid_file_path.read_text()
        return saved_uuid.strip()
    else:
        # Generate a new UUID if file is not found
        newly_generated_uuid = _set_uuid(uuid_file_path, mode)
        return newly_generated_uuid


def _set_uuid(uuid_file_path=None, mode=0o0600):
    if uuid_file_path is None:
        uuid_file_path = Path.home().joinpath('.ansible_runner_uuid')

    generated_uuid = str(uuid.uuid4())

    if not uuid_file_path.exists():
        # Ensure the file starts with correct permissions
        uuid_file_path.touch(mode)

    # Ensure the correct permissions if the file exists
    uuid_file_path.chmod(mode)

    # Store the newly-generated UUID in a new file in home dir
    uuid_file_path.write_text(generated_uuid)

    return generated_uuid
