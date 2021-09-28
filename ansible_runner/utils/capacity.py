import glob
import multiprocessing
import os
import re
import stat
import tempfile
import uuid


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


def generate_or_get_uuid():
    uuid_directory = glob.glob('/tmp/node_uuid_*')  # Location TBD
    if uuid_directory:
        # Read the contents of the uuid.txt file if it already exists
        uuid_file_path = os.path.join(uuid_directory[0], 'uuid.txt')
        with open(uuid_file_path) as f:
            saved_uuid = f.read()
        return saved_uuid
    else:
        # Generate a new UUID if no uuid.txt file is found
        generated_uuid = str(uuid.uuid4())

        # Store the newly-generated UUID in a new dir/file
        path = tempfile.mkdtemp(prefix='node_uuid_')
        uuid_file = 'uuid.txt'
        uuid_file_path = os.path.join(path, uuid_file)
        with open(uuid_file_path, 'w') as uuid_file:
            os.chmod(uuid_file.name, stat.S_IRUSR | stat.S_IWUSR)
            uuid_file.write(generated_uuid)
            uuid_file.close()
        return generated_uuid
