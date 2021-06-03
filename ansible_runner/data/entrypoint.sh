#!/usr/bin/env bash

# In OpenShift, containers are run as a random high number uid
# that doesn't exist in /etc/passwd, but Ansible module utils
# require a named user. So if we're in OpenShift, we need to make
# one before Ansible runs.
if [[ (`id -u` -ge 500 || -z "${CURRENT_UID}") ]]; then

    # Only needed for RHEL 8. Try deleting this conditional (not the code)
    # sometime in the future. Seems to be fixed on Fedora 32
    # If we are running in rootless podman, this file cannot be overwritten
    ROOTLESS_MODE=$(cat /proc/self/uid_map | head -n1 | awk '{ print $2; }')
    if [[ "$ROOTLESS_MODE" -eq "0" ]]; then
cat << EOF > /etc/passwd
root:x:0:0:root:/root:/bin/bash
runner:x:`id -u`:`id -g`:,,,:/home/runner:/bin/bash
EOF
    fi

cat <<EOF > /etc/group
root:x:0:runner
runner:x:`id -g`:
EOF

fi

if [[ -n "${LAUNCHED_BY_RUNNER}" ]]; then
    RUNNER_CALLBACKS=$(python3 -c "import ansible_runner.callbacks; print(ansible_runner.callbacks.__file__)")

    # TODO: respect user callback settings via
    # env ANSIBLE_CALLBACK_PLUGINS or ansible.cfg
    export ANSIBLE_CALLBACK_PLUGINS="$(dirname $RUNNER_CALLBACKS)"
fi

if [[ -d ${AWX_ISOLATED_DATA_DIR} ]]; then
    if output=$(ansible-galaxy collection list --format json 2> /dev/null); then
        echo $output > ${AWX_ISOLATED_DATA_DIR}/collections.json
    fi
    ansible --version | head -n 1 > ${AWX_ISOLATED_DATA_DIR}/ansible_version.txt
fi

SCRIPT=/usr/local/bin/dumb-init
# NOTE(pabelanger): Downstream we install dumb-init from RPM.
if [ -f "/usr/bin/dumb-init" ]; then
    SCRIPT=/usr/bin/dumb-init
fi

exec $SCRIPT -- "${@}"
