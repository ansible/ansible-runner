FROM centos:7

# Install Ansible Runner
RUN yum -y update && yum -y install epel-release  && \
    yum -y install ansible python-psutil python-pip bubblewrap bzip2 python-crypto openssh \
    openssh-clients
RUN pip install python-memcached wheel pexpect psutil python-daemon

ADD dist/ansible_runner-1.0-py2.py3-none-any.whl /ansible_runner-1.0-py2.py3-none-any.whl
RUN pip install /ansible_runner-1.0-py2.py3-none-any.whl

RUN localedef -c -i en_US -f UTF-8 en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ADD https://github.com/krallin/tini/releases/download/v0.14.0/tini /tini
RUN chmod +x /tini

ADD demo/project /runner/project
ADD demo/env /runner/env
ADD demo/inventory /runner/inventory
VOLUME /runner/inventory
VOLUME /runner/project
VOLUME /runner/artifacts
ENTRYPOINT ["/tini", "--"]
WORKDIR /
ENV RUNNER_BASE_COMMAND=ansible-playbook
CMD ansible-runner run /runner
