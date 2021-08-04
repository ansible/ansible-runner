import multiprocessing
import re


def get_cpu_count():
    # `multiprocessing` info: https://docs.python.org/3/library/multiprocessing.html
    cpu_capacity = multiprocessing.cpu_count()
    return cpu_capacity


def get_mem_info():
    try:
        with open('/proc/meminfo') as f:
            mem = f.read()
        matched = re.search(r'^MemTotal:\s+(\d+)', mem)
        if matched:
            mem_capacity = int(matched.groups()[0])
        return mem_capacity
    except FileNotFoundError:
        error = "The /proc/meminfo file could not found, memory capacity undiscoverable."
        return error
