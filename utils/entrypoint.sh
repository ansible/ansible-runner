#!/usr/bin/env bash

# In OpenShift, containers are run as a random high number uid
# that doesn't exist in /etc/passwd, but Ansible module utils
# require a named user. So if we're in OpenShift, we need to make
# one before Ansible runs.
if [ `id -u` -ge 500 ] || [ -z "${CURRENT_UID}" ]; then
cat << EOF > /etc/passwd
root:x:0:0:root:/root:/bin/bash
runner:x:`id -u`:`id -g`:,,,:/runner:/bin/bash
EOF
fi

exec tini -- "${@}"
