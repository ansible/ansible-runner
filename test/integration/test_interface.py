
from ansible_runner.interface import run, run_async


def test_run():
    r = run(module='debug', host_pattern='localhost')
    assert r.status == 'successful'


def test_run_async():
    thread, r = run_async(module='debug', host_pattern='localhost')
    thread.join()
    assert r.status == 'successful'
