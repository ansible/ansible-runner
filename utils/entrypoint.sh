#!/usr/bin/env bash

# We need to fix a number of problems here that manifest under different container runtimes, as well as tweak some
# things to simplify runner's containerized launch behavior. Since runner currently always expects to bind-mount its
# callback plugins under ~/.ansible, it must have prior knowledge of the user's homedir before the container is launched
# in order to know where to mount in the callback dir. In all cases, we must get a consistent answer from $HOME
# and anything that queries /etc/passwd for a homedir (eg, `~root`), or lots of things (including parts of Ansible
# core itself) will be broken.

# If we're running as a legit default user that has an entry in /etc/passwd and a valid homedir, we're all good.

# If the username/uid we're running under is not represented in /etc/passwd or the current user's homedir is something
# other than /home/runner (eg, the container was run with --user and some dynamic unmapped UID from the host with
# primary GID 0), we need to correct that in order for ansible-runner's callbacks to function properly. Some things
# (eg podman/cri-o today) already create an /etc/passwd entry on the fly in this case, but they set the homedir to
# WORKDIR, which causes potential collisions with mounted/mapped volumes. For consistency, we'll
# just always set the current user's homedir to `/home/runner`, which we've already configured in a way
# that should always work with known container runtimes (eg, ug+rwx and all dirs owned by the root group).

# If current user is not listed in /etc/passwd, add an entry with username==uid, primary gid 0, and homedir /home/runner

# If current user is in /etc/passwd but $HOME != `/home/runner`, rewrite that user's homedir in /etc/passwd to
# /home/runner and export HOME=/home/runner for this session only. All new sessions (eg podman exec) should
# automatically set HOME to the value in /etc/passwd going forward.

# Ideally in the future, we can come up with a better way for the outer runner to dynamically inject its callbacks, or
# rely on the inner runner's copy. This would allow us to restore the typical POSIX user homedir conventions.

# if any of this business fails, we probably want to fail fast
if [ -n "$EP_DEBUG" ]; then
  set -eux
  echo 'hello from entrypoint'
else
  set -e
fi

# current user might not exist in /etc/passwd at all
if ! $(whoami &> /dev/null) || ! getent passwd $(whoami || id -u) &> /dev/null ; then
  if [ -n "$EP_DEBUG" ]; then
    echo "adding missing uid $(id -u) into /etc/passwd"
  fi
  echo "$(id -u):x:$(id -u):0:container user $(id -u):/home/runner:/bin/bash" >> /etc/passwd
  export HOME=/home/runner
fi

MYHOME=`getent passwd $(whoami) | cut -d: -f6`

if [ "$MYHOME" != "$HOME" ] || [ "$MYHOME" != "/home/runner" ]; then
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
