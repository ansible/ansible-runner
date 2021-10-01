import multiprocessing
import os
import re
import stat
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


def get_uuid():
    uuid_file_path = Path('/etc/ansible/facts.d/uuid.txt')
    if uuid_file_path.exists():
        # Read the contents of the uuid.txt file if it already exists
        with open(uuid_file_path) as f:
            saved_uuid = f.read()
        return saved_uuid
    else:
        # Generate a new UUID if no uuid.txt file is found
        newly_generated_uuid = _generate_uuid()
        return newly_generated_uuid


def _generate_uuid():
    generated_uuid = str(uuid.uuid4())

    # Store the newly-generated UUID in a new dir/file
    uuid_dir = Path('/etc/ansible/facts.d')
    uuid_dir.mkdir(parents=True, exist_ok=True)
    uuid_file = 'uuid.txt'
    uuid_file_path = uuid_dir / uuid_file

    with uuid_file_path.open('w', encoding='utf-8') as uuid_file:
        os.chmod(uuid_file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        uuid_file.write(generated_uuid)
    return generated_uuid
