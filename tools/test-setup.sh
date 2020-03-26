#!/bin/bash

# NOTE(pabelanger): Default to pip3, when possible this is becaue python2
# support is EOL.
PIP=$(command -v pip3) || PIP=$(command -v pip2)

# NOTE(pabelanger): Tox on centos-7 is old, so upgrade it across all distros
# to the latest version
# NOTE(pabelanger): Cap zipp<0.6.0 due to python2.7 issue with more-iterrtools
# https://github.com/jaraco/zipp/issues/14
sudo $PIP install -U tox "configparser<5" "zipp<0.6.0;python_version=='2.7'"
