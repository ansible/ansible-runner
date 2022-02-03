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
    # Special actions to be compatible with old ansible-runner versions, 2.1.x specifically
    RUNNER_CALLBACKS=$(python3 -c "import from ansible_runner.display_callback.callback import awx_display; print(awx_display.__file__)")
    export ANSIBLE_CALLBACK_PLUGINS="$(dirname $RUNNER_CALLBACKS)"

    # old versions split the callback name between awx_display and minimal, but new version just uses awx_display
    export ANSIBLE_STDOUT_CALLBACK=awx_display
fi

if [[ -d ${AWX_ISOLATED_DATA_DIR} ]]; then
    if output=$(ansible-galaxy collection list --format json 2> /dev/null); then
        echo $output > ${AWX_ISOLATED_DATA_DIR}/collections.json
    fi
    ansible --version 2> /dev/null | head -n 1 > ${AWX_ISOLATED_DATA_DIR}/ansible_version.txt
fi

SCRIPT=/usr/local/bin/dumb-init
# NOTE(pabelanger): Downstream we install dumb-init from RPM.
if [ -f "/usr/bin/dumb-init" ]; then
    SCRIPT=/usr/bin/dumb-init
fi

exec $SCRIPT -- "${@}"
