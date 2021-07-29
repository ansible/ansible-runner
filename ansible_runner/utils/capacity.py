import multiprocessing
import resource


def get_cpu_capacity():
    # `multiprocessing` info: https://docs.python.org/3/library/multiprocessing.html
    forkcpu = 4
    cpu_capacity = multiprocessing.cpu_count() * forkcpu
    return cpu_capacity


def get_mem_capacity():
    # `resource` info: https://docs.python.org/3/library/resource.html
    byte_denom = 1024
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss 
    mem_capacity = mem / byte_denom
    return mem_capacity
