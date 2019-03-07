FROM debian:testing

RUN apt-get update
RUN apt-get install -y make python-pip debhelper devscripts dh-python python-all python-setuptools python3-all python3-setuptools git python-pytest python3-pytest python-pexpect python3-pexpect python-mock python3-mock python-psutil python3-psutil python3-yaml

RUN pip install -IU pip setuptools
RUN pip install -IU pipenv ansible
