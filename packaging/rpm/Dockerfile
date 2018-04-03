FROM centos:7

RUN yum install -y epel-release
RUN yum install -y make mock python-pip which git

# Newer version of setuptools needed for pipenv
RUN pip install -IU pip setuptools
RUN pip install -IU pipenv ansible

