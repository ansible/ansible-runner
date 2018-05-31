#!/usr/bin/env python

# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

setup(
    name="ansible-runner",
    version="1.0.3",
    author='Red Hat Ansible',
    url="https://github.com/ansible/ansible-runner",
    packages=find_packages(),
    install_requires=[
        'psutil',
        'pexpect==4.5.0',
        'python-daemon',
        'PyYAML',
        'six',
    ],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'ansible-runner = ansible_runner.__main__:main'
        ]
    }
)
