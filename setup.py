#!/usr/bin/env python

# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name="ansible-runner",
    version="1.3.4",
    author='Red Hat Ansible',
    url="https://github.com/ansible/ansible-runner",
    license='Apache',
    packages=find_packages(),
    long_description=long_description,
    long_description_content_type='text/markdown',
    install_requires=[
        'psutil',
        'pexpect>=4.5',
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
