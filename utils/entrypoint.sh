#!/usr/bin/env bash

# We need to fix a number of problems here that manifest under different container runtimes. If we're running
# as a legit default user that has an entry in /etc/passwd and a valid homedir that's not `/`, we're all good.
# If the username/uid we're running under is not represented in /etc/passwd and/or doesn't have a homedir that's not
# `/` (eg, the container was run with --user and some dynamic unmapped UID from the host with primary GID 0), we need to
# correct that. Some things (eg podman/cri-o today) already create an /etc/passwd entry on the fly in this case, but
# they set the homedir to `/`, which causes potential collisions with mounted/mapped volumes. For consistency, we'll
# just always set every dynamically-created user's homedir to `/home/runner`, which we've already configured in a way
# that should always work (eg, ug+rwx and all dirs owned by the root group).

# if current user is not listed in /etc/passwd, add an entry with username==uid, primary gid 0, and homedir /home/runner

# if current user is in /etc/passwd but $HOME == `/`, rewrite that user's homedir in /etc/passwd to /home/runner and
# export HOME=/home/runner for this session only- all new sessions, eg created by exec, should set HOME to match the
# current value in /etc/passwd going forward.

# if any of this business fails, we probably want to fail fast
if [ -n "$EP_DEBUG" ]; then
  set -eux
  echo 'hello from entrypoint'
else
  set -e
fi

# FIXME junk output
if ! getent passwd $(whoami || id -u) ; then
  if [ -n "$EP_DEBUG" ]; then
    echo "hacking missing uid $(id -u) into /etc/passwd"
  fi
  echo "$(id -u):x:$(id -u):0:container user $(id -u):/home/runner:/bin/bash" >> /etc/passwd
  export HOME=/home/runner
fi

# FIXME junk output
MYHOME=`getent passwd $(whoami) | cut -d: -f6`

# FIXME: we also want to check the case of a generated user who podman set their homedir to WORKDIR; maybe anything with a high UID, or ?
if [ "$MYHOME" != "$HOME" ] || [ $(id -u) -ge 500 ] && [ "$MYHOME" != "/home/runner" ]; then
  if [ -n "$EP_DEBUG" ]; then
    echo "replacing homedir for user $(whoami)"
  fi
  # sed -i wants to create a tempfile next to the original, which won't work with /etc permissions in many cases,
  # so just do it in memory and overwrite the existing file if we succeeded
  NEWPW=$(sed -r "s/(^$(whoami):(.*:){4})(.*:)/\1\/home\/runner:/g" /etc/passwd)
  echo "$NEWPW" > /etc/passwd
  # ensure the envvar matches what we just set in /etc/passwd for this session; future sessions set automatically
  export HOME=/home/runner
fi

# FIXME: validate group entries?

if [[ -n "${LAUNCHED_BY_RUNNER}" ]]; then
    # Special actions to be compatible with old ansible-runner versions, 2.1.x specifically
    RUNNER_CALLBACKS=$(python3 -c "from ansible_runner.display_callback.callback import awx_display; print(awx_display.__file__)")
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
