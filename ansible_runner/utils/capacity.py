import multiprocessing
import resource


def get_cpu_count():
    # `multiprocessing` info: https://docs.python.org/3/library/multiprocessing.html
    cpu_capacity = multiprocessing.cpu_count()
    return cpu_capacity


def get_mem_info():
    # `resource` info: https://docs.python.org/3/library/resource.html
    mem_capacity = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return mem_capacity
