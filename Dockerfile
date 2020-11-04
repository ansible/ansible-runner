ARG BASE_IMAGE=docker.io/fedora:32

FROM ${BASE_IMAGE}

# Install system packages for use in all images
RUN dnf install -y \
    python3-pip \
    gcc \
    rsync \
    openssh-clients \
    sshpass \
    glibc-langpack-en \
    git \
    https://github.com/krallin/tini/releases/download/v0.19.0/tini_0.19.0-amd64.rpm && \
    rm -rf /var/cache/dnf

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

# Install python packages for use in all images
RUN pip3 install --no-cache-dir bindep

# Prepare the /runner folder, seed the folder with demo data
ADD demo /runner

# In OpenShift, container will run as a random uid number and gid 0. Make sure things
# are writeable by the root group.
RUN for dir in \
      /home/runner \
      /home/runner/.ansible \
      /home/runner/.ansible/tmp \
      /runner \
      /home/runner \
      /runner/env \
      /runner/inventory \
      /runner/project \
      /runner/artifacts ; \
    do mkdir -m 0775 -p $dir ; chmod -R g+rwx $dir ; chgrp -R root $dir ; done && \
    for file in \
      /home/runner/.ansible/galaxy_token \
      /etc/passwd \
      /etc/group ; \
    do touch $file ; chmod g+rw $file ; chgrp root $file ; done

VOLUME /runner

WORKDIR /runner

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV HOME=/home/runner

ADD utils/entrypoint.sh /bin/entrypoint
RUN chmod +x /bin/entrypoint

ENTRYPOINT ["entrypoint"]
CMD ["ansible-runner", "run", "/runner"]


# Install ansible-runner
#TODO optionally install ansible-runner from rpm

ARG RUNNER_VERSION=2.0.0
COPY dist/ansible-runner-${RUNNER_VERSION}.tar.gz /tmp/
RUN pip3 install --no-cache-dir /tmp/ansible-runner-${RUNNER_VERSION}.tar.gz


# Install ansible
#TODO optionally install ansible from rpm
#ADD https://releases.ansible.com/ansible-runner/ansible-runner.el8.repo /etc/yum.repos.d/ansible-runner.repo

ARG ANSIBLE_BRANCH=devel
RUN pip3 install --no-cache-dir https://github.com/ansible/ansible/archive/${ANSIBLE_BRANCH}.tar.gz
