import json
import os
import subprocess
import pathlib
import random

from string import ascii_lowercase

import pexpect
import pytest
import yaml

from ansible_runner.config.runner import RunnerConfig

here = pathlib.Path(__file__).parent


@pytest.fixture(scope='function')
def rc(tmp_path):
    conf = RunnerConfig(str(tmp_path))
    conf.suppress_ansible_output = True
    conf.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    conf.cwd = str(tmp_path)
    conf.env = {}
    conf.job_timeout = 10
    conf.idle_timeout = 0
    conf.pexpect_timeout = 2.
    conf.pexpect_use_poll = True
    return conf


class CompletedProcessProxy:

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
def cli():
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
            ret = CompletedProcessProxy(subprocess.run(' '.join(args), check=kw.pop('check'), shell=True, *a, **kw))
        except subprocess.CalledProcessError as err:
            pytest.fail(
                f"Running {err.cmd} resulted in a non-zero return code: {err.returncode} - stdout: {err.stdout}, stderr: {err.stderr}"
            )

        return ret
    return run


@pytest.fixture
def container_image(request, cli, tmp_path):  # pylint: disable=W0621
    try:
        containerized = request.getfixturevalue('containerized')
        if not containerized:
            yield None
            return
    except Exception:
        # Test func doesn't use containerized
        pass

    if (env_image_name := os.getenv('RUNNER_TEST_IMAGE_NAME')):
        yield env_image_name
        return

    cli(
        ['pyproject-build', '-w', '-o', str(tmp_path)],
        cwd=here.parent.parent,
        bare=True,
    )

    wheel = next(tmp_path.glob('*.whl'))  # pylint: disable=R1708

    runtime = request.getfixturevalue('runtime')
    dockerfile_path = tmp_path / 'Dockerfile'
    dockerfile_path.write_text(
        (here / 'Dockerfile').read_text()
    )
    random_string = ''.join(random.choice(ascii_lowercase) for i in range(10))
    image_name = f'ansible-runner-{random_string}-event-test'

    cli(
        [runtime, 'build', '--build-arg', f'WHEEL={wheel.name}', '--rm=true', '-t', image_name, '-f', str(dockerfile_path), str(tmp_path)],
        bare=True,
    )
    yield image_name
    cli(
        [runtime, 'rmi', '-f', image_name],
        bare=True,
    )


@pytest.fixture
def container_image_devel(request, cli, tmp_path):  # pylint: disable=W0621
    branch = request.getfixturevalue('branch')

    DOCKERFILE = f"""
FROM quay.io/centos/centos:stream9
ARG WHEEL
COPY $WHEEL /$WHEEL

# Need python 3.11 minimum for devel
RUN dnf install -y python3.11 python3.11-pip git
RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 0
RUN python3 -m pip install /$WHEEL git+https://github.com/ansible/ansible@{branch}

RUN mkdir -p /runner/{{env,inventory,project,artifacts}} /home/runner/.ansible/tmp
RUN chmod -R 777 /runner /home/runner
WORKDIR /runner
ENV HOME=/home/runner
CMD ["ansible-runner", "run", "/runner"]
"""

    try:
        containerized = request.getfixturevalue('containerized')
        if not containerized:
            yield None
            return
    except Exception:
        # Test func doesn't use containerized
        pass

    if (env_image_name := os.getenv('RUNNER_TEST_IMAGE_NAME')):
        yield env_image_name
        return

    cli(
        ['pyproject-build', '-w', '-o', str(tmp_path)],
        cwd=here.parent.parent,
        bare=True,
    )

    wheel = next(tmp_path.glob('*.whl'))  # pylint: disable=R1708

    runtime = request.getfixturevalue('runtime')
    dockerfile_path = tmp_path / 'Dockerfile'
    dockerfile_path.write_text(DOCKERFILE)
    random_string = ''.join(random.choice(ascii_lowercase) for i in range(10))
    image_name = f'ansible-runner-{random_string}-event-test'

    cli(
        [runtime, 'build', '--build-arg', f'WHEEL={wheel.name}', '--rm=true', '-t', image_name, '-f', str(dockerfile_path), str(tmp_path)],
        bare=True,
    )
    yield image_name
    cli(
        [runtime, 'rmi', '-f', image_name],
        bare=True,
    )
