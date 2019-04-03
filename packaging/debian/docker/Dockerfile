FROM ubuntu:xenial

RUN apt-get update
RUN apt-get install -y \
  make debhelper dh-python devscripts python-all python-setuptools python-pip

RUN pip install -IU pip setuptools
RUN pip install -IU pipenv ansible
