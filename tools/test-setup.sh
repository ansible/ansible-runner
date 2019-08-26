#!/bin/bash

# NOTE(pabelanger): Tox on centos-7 is old, so upgrade it across all distros
# to the latest version
# NOTE(pabelanger): Cap zipp<0.6.0 due to python2.7 issue with more-iterrtools
# https://github.com/jaraco/zipp/issues/14
sudo pip install -U tox "zipp<0.6.0"
