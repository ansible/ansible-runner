#!/usr/bin/env python

# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

setup(
    name="ansible_runner",
    version="1.0",
    author='Red Hat Ansible',
    packages=find_packages(),
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'ansible-runner=ansible_runner.run:main',
        ],
    },
)
