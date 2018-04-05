FROM centos:7

ADD https://github.com/krallin/tini/releases/download/v0.14.0/tini /tini

# Install Ansible Runner
RUN yum -y install epel-release  && \
    yum -y install ansible python-psutil python-pip bubblewrap bzip2 python-crypto \
                   which gcc python-devel libxml2 libxml2-devel krb5 krb5-devel curl curl-devel \
                   openssh openssh-clients && \
    pip install --no-cache-dir -U setuptools && \
    pip install --no-cache-dir wheel pexpect psutil python-daemon pipenv PyYAML && \
    localedef -c -i en_US -f UTF-8 en_US.UTF-8 && \
    chmod +x /tini && \
    rm -rf /var/cache/yum

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

ENTRYPOINT ["/tini", "--"]
WORKDIR /
