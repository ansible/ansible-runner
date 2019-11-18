FROM centos:7

ADD https://github.com/krallin/tini/releases/download/v0.18.0/tini /bin/tini
ADD utils/entrypoint.sh /bin/entrypoint
ADD demo/project /runner/project
ADD demo/env /runner/env
ADD demo/inventory /runner/inventory

# Install Ansible Runner
RUN yum-config-manager --add-repo https://releases.ansible.com/ansible-runner/ansible-runner.el7.repo && \
	yum install -y epel-release && \
	yum install -y python-pip ansible-runner bubblewrap sudo rsync openssh-clients sshpass && \
	pip install --no-cache-dir ansible && \
	localedef -c -i en_US -f UTF-8 en_US.UTF-8 && \
	chmod +x /bin/tini /bin/entrypoint && rm -rf /var/cache/yum

# In OpenShift, container will run as a random uid number and gid 0. Make sure things
# are writeable by the root group.
RUN mkdir -p /runner/inventory /runner/project /runner/artifacts /runner/.ansible/tmp && \
	chmod -R g+w /runner && chgrp -R root /runner && \
	chmod g+w /etc/passwd

VOLUME /runner/inventory
VOLUME /runner/project
VOLUME /runner/artifacts

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV RUNNER_BASE_COMMAND=ansible-playbook
ENV HOME=/runner

WORKDIR /runner

ENTRYPOINT ["entrypoint"]
CMD ["ansible-runner", "run", "/runner"]
