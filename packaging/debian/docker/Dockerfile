FROM debian:testing

RUN apt-get update
RUN apt-get install -y make python-pip debhelper devscripts dh-python python-all python-setuptools python-setuptools git python-pytest python-pexpect python-mock python-psutil python-yaml

RUN pip install -IU pip setuptools
RUN pip install -IU pipenv ansible
