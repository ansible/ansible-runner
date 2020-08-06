FROM docker.io/centos:8

ADD https://github.com/krallin/tini/releases/download/v0.18.0/tini /bin/tini
ADD demo/project /runner/project
ADD demo/env /runner/env
ADD demo/inventory /runner/inventory

# Install Ansible and Runner
ADD https://releases.ansible.com/ansible-runner/ansible-runner.el8.repo /etc/yum.repos.d/ansible-runner.repo
RUN dnf install -y epel-release && \
    dnf install -y ansible-runner python3-pip sudo rsync openssh-clients sshpass glibc-langpack-en git && \
    alternatives --set python /usr/bin/python3 && \
    pip3 install ansible && \
    chmod +x /bin/tini && \
    rm -rf /var/cache/dnf

RUN useradd runner && usermod -aG root runner

ADD utils/entrypoint.sh /bin/entrypoint
RUN chmod +x /bin/entrypoint

# In OpenShift, container will run as a random uid number and gid 0. Make sure things
# are writeable by the root group.
RUN for dir in \
      /runner \
      /home/runner \
      /runner/env \
      /runner/inventory \
      /runner/project \
      /runner/artifacts ; \
    do mkdir -m 0775 -p $dir ; chmod g+rw $dir ; chgrp runner $dir ; done && \
    for file in \
      /etc/passwd ; \
    do touch $file ; chmod g+rw $file ; chgrp runner $file ; done

VOLUME /runner

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV RUNNER_BASE_COMMAND=ansible-playbook
ENV HOME=/home/runner

WORKDIR /runner

ENTRYPOINT ["entrypoint"]
CMD ["ansible-runner", "run", "/runner"]
