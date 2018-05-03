#!/usr/bin/env python

# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

setup(
    name="ansible-runner",
    version="1.0.1",
    author='Red Hat Ansible',
    url="https://github.com/ansible/ansible-runner",
    packages=find_packages(),
    install_requires=[
        'psutil',
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
