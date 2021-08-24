import multiprocessing
import re


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
    try:
        with open('/var/lib/dbus/machine-id') as f:
            uuid = f.read()
        return uuid.strip()
    except FileNotFoundError:
        try:
            with open('/etc/machine-id') as f:
                uuid = f.read()
                return uuid.strip()
        except FileNotFoundError:
            error = ("Could not find /var/lib/dbus/machine-id or "
                     "/etc/machine-id files, UUID undiscoverable.")
            return error
