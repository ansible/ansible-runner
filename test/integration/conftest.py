import json
import os
import subprocess
import yaml
import pytest
import pexpect
import random
from string import ascii_lowercase

from ansible_runner.config.runner import RunnerConfig


@pytest.fixture(scope='function')
def rc(tmp_path):
    rc = RunnerConfig(str(tmp_path))
    rc.suppress_ansible_output = True
    rc.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    rc.cwd = str(tmp_path)
    rc.env = {}
    rc.job_timeout = 10
    rc.idle_timeout = 0
    rc.pexpect_timeout = 2.
    rc.pexpect_use_poll = True
    return rc


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


@pytest.fixture(scope='function')
def cli(request):
    def run(args, *a, **kw):
        if not kw.pop('bare', None):
            args = ['ansible-runner'] + args
        kw['encoding'] = 'utf-8'
        if 'check' not in kw:
            # By default we want to fail if a command fails to run. Tests that
            # want to skip this can pass check=False when calling this fixture
            kw['check'] = True
        if 'stdout' not in kw:
            kw['stdout'] = subprocess.PIPE
        if 'stderr' not in kw:
            kw['stderr'] = subprocess.PIPE

        kw.setdefault('env', os.environ.copy()).update({
            'LANG': 'en_US.UTF-8'
        })

        try:
            ret = CompletedProcessProxy(subprocess.run(' '.join(args), shell=True, *a, **kw))
        except subprocess.CalledProcessError as err:
            pytest.fail(
                f"Running {err.cmd} resulted in a non-zero return code: {err.returncode} - stdout: {err.stdout}, stderr: {err.stderr}"
            )

        return ret
    return run


@pytest.fixture
def container_image(request, cli, tmp_path):
    try:
        containerized = request.getfixturevalue('containerized')
        if not containerized:
            yield None
            return
    except Exception:
        # Test func doesn't use containerized
        pass

    cli(
        ['pyproject-build', '-w', '-o', str(tmp_path)],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        bare=True,
    )

    wheel = next(tmp_path.glob('*.whl'))

    runtime = request.getfixturevalue('runtime')
    dockerfile_path = tmp_path / 'Dockerfile'
    dockerfile_path.write_text('\n'.join([
        'FROM quay.io/centos/centos:stream9',
        f'COPY {wheel.name} /{wheel.name}',
        'RUN dnf install -y python3-pip',
        f'RUN python3 -m pip install /{wheel.name} ansible-core',
        'RUN mkdir -p /runner/{env,inventory,project,artifacts} /home/runner/.ansible/tmp',
        'RUN chmod -R 777 /runner /home/runner',
        'WORKDIR /runner',
        'ENV HOME=/home/runner',
        'CMD ["ansible-runner", "run", "/runner"]',
    ]))

    random_string = ''.join(random.choice(ascii_lowercase) for i in range(10))
    image_name = f'ansible-runner-{random_string}-event-test'

    cli(
        [runtime, 'build', '--rm=true', '-t', image_name, '-f', str(dockerfile_path), str(tmp_path)],
        bare=True,
    )
    yield image_name
    cli(
        [runtime, 'rmi', '-f', image_name],
        bare=True,
    )
