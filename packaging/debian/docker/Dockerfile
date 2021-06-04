FROM debian:buster

RUN apt-get update
RUN apt-get install -y \
  make debhelper dh-python devscripts python-all python-setuptools python-pip \
  python-backports.functools-lru-cache pinentry-tty

RUN update-alternatives --config pinentry
RUN pip install -IU pip setuptools
RUN pip install -IU ansible
