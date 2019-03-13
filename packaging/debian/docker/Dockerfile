FROM debian:testing

RUN apt-get update
RUN apt-get install -y make python-pip debhelper devscripts dh-python python3-all python3-setuptools python3-all python3-setuptools git python3-pytest python3-pexpect python3-mock python3-psutil python3-yaml

RUN pip install -IU pip setuptools
RUN pip install -IU pipenv ansible
