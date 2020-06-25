import json
import os
import sys
import subprocess
import yaml

from tempfile import NamedTemporaryFile

import pytest


@pytest.fixture
def tmp_file_maker():
    """Fixture to return temporary file maker."""
    def tmp_file(text):
        with NamedTemporaryFile(delete=False) as tempf:
            tempf.write(bytes(text, 'UTF-8'))
        return tempf.name
    return tmp_file


class CompletedProcessProxy(object):

    def __init__(self, result):
        self.result = result

    def __getattr__(self, attr):
        return getattr(self.result, attr)

    @property
    def json(self):
        try:
            response_json = json.loads(self.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                f"Unable to convert the response to a valid json - stdout: {self.stdout}, stderr: {self.stderr}"
            )
        return response_json

    @property
    def yaml(self):
        return yaml.safe_load(self.stdout)


@pytest.fixture(autouse=True, scope='session')
def ansible_runner_binary():
    if not os.environ.get('POETRY_ACTIVE', False):
        return 'ansible-runner'
    syspath = os.environ.get('PATH').split(':')
    venv_index = None
    for item in syspath:
        if 'pypoetry' in item:
            venv_index = syspath.index(item)
            break
    if venv_index is None:
        pytest.fail('poetry is active but cannot find its venv')

    venv_bin = syspath.pop(venv_index)
    return os.path.join(venv_bin, 'ansible-runner')


@pytest.fixture(scope='function')
def cli(request, ansible_runner_binary):
    def run(args, *a, **kw):
        args = [ansible_runner_binary,] + args
        kw['encoding'] = 'utf-8'
        if 'check' not in kw:
            # By default we want to fail if a command fails to run. Tests that
            # want to skip this can pass check=False when calling this fixture
            kw['check'] = True
        if 'stdout' not in kw:
            kw['stdout'] = subprocess.PIPE
        if 'stderr' not in kw:
            kw['stderr'] = subprocess.PIPE

            kw.setdefault('env', {}).update({
                'LANG': 'en_US.UTF-8'
            })

        try:
            ret = CompletedProcessProxy(subprocess.run(args, *a, **kw))
        except subprocess.CalledProcessError as err:
            pytest.fail(
                f"Running {err.cmd} resulted in a non-zero return code: {err.returncode} - stdout: {err.stdout}, stderr: {err.stderr}"
            )

        return ret
    return run
