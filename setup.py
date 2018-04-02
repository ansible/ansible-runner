#!/usr/bin/env python

# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

setup(
    name="ansible_runner",
    version="1.0",
    author='Red Hat Ansible',
    packages=find_packages(),
    install_requires=[
        'psutil',
        'python-memcached==1.58',
        'pexpect',
        'python-daemon',
        'PyYAML',
    ],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'ansible-runner=ansible_runner.interface:main',
        ],
    },
)
