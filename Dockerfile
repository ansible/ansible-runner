FROM centos:7

ADD https://github.com/krallin/tini/releases/download/v0.14.0/tini /tini

# Install Ansible Runner
RUN yum -y install epel-release  && \
    yum -y install ansible python-psutil python-pip bubblewrap bzip2 python-crypto openssh openssh-clients && \
    localedef -c -i en_US -f UTF-8 en_US.UTF-8 && \
    chmod +x /tini && \
    pip install --no-cache-dir wheel pexpect psutil python-daemon && \
    rm -rf /var/cache/yum

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

VOLUME /runner/inventory
VOLUME /runner/project
VOLUME /runner/artifacts
ENTRYPOINT ["/tini", "--"]
WORKDIR /
ENV RUNNER_BASE_COMMAND=ansible-playbook
CMD ansible-runner run /runner

ADD demo/project /runner/project
ADD demo/env /runner/env
ADD demo/inventory /runner/inventory
ADD dist/ansible_runner-1.0.1-py2.py3-none-any.whl /ansible_runner-1.0.1-py2.py3-none-any.whl
RUN pip install --no-cache-dir /ansible_runner-1.0.1-py2.py3-none-any.whl
