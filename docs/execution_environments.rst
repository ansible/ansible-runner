.. _execution_environments:

Using Runner with Execution Environments
========================================

**Execution Environments** are meant to be a consistent, reproducible, portable,
and sharable method to run Ansible Automation jobs in the exact same way on
your laptop as they are executed in `Ansible AWX <https://github.com/ansible/awx/>`_.
This aids in the development of automation jobs and Ansible Content that is
meant to be run in **Ansible AWX**, `Ansible Tower <https://www.ansible.com/products/tower>`_,
or via `Red Hat Ansible Automation Platform <https://www.ansible.com/products/automation-platform>`_
in a predictable way.

More specifically, the term **Execution Environments** within the context of
**Ansible Runner** refers to the container runtime execution of **Ansible** via
**Ansible Runner** within an `OCI Compliant Container Runtime
<https://github.com/opencontainers/runtime-spec>`_ using an `OCI Compliant
Container Image <https://github.com/opencontainers/image-spec/>`_ that
appropriately bundles `Ansible Base <https://github.com/ansible/ansible>`_,
`Ansible Collection Content <https://github.com/ansible-collections/overview>`_,
and the runtime dependencies required to support these contents.
The build tooling provided by `Ansible Builder <https://github.com/ansible/ansible-builder>`_
aids in the creation of these images.

All aspects of running **Ansible Runner** in standalone mode (see: :ref:`standalone`)
are true here with the exception that the process isolation is inherently a
container runtime (`podman <https://podman.io/>`_ by default).

Using Execution Environments from Protected Registries
------------------------------------------------------

When a job is run that uses an execution environment container image from a private/protected registry,
you will first need to authenticate to the registry.

If you are running the job manually via ``ansible-runner run``, logging in on the command line via
``podman login`` first is a method of authentication. Alternatively, creating a ``container_auth_data``
dictionary with the keys ``host``, ``username``, and ``password`` and putting that in the job's ``env/settings``
file is another way to ensure a successful pull of a protected execution environment container image.
Note that this involves listing sensitive information in a file which will not automatically get cleaned
up after the job run is complete.

When running a job remotely via AWX or Ansible Tower, Ansible Runner can pick up the authentication
information from the Container Registry Credential that was provided by the user. The ``host``,
``username``, ``password``, and ``verify_ssl`` inputs from the credential are passed into Ansible Runner via the ``container_auth_data``
dictionary as key word arguments into a ``json`` file which gets deleted at the end of the job run (even if
the job was canceled/interrupted), enabling the bypassing of sensitive information from any potentially
persistent job-related files.

Notes and Considerations
------------------------

There are some differences between using Ansible Runner and running Ansible directly from the
command line that have to do with configuration, content locality, and secret data.

Secrets
^^^^^^^

Typically with Ansible you are able to provide secret data via a series of
mechanisms, many of which are pluggable and configurable. When using
Ansible Runner, however, certain considerations need to be made; these are analogous to
how Ansible AWX and Tower manage this information.

See :ref:`inputdir` for more information

Container Names
^^^^^^^^^^^^^^^

Like all ansible-runner jobs, each job has an identifier associated with it
which is also the name of the artifacts subfolder where results are saved to.
When a container for job isolation is launched, it will be given a name
of ``ansible_runner_<job identifier>``. Some characters from the job
identifier may be replaced with underscores for compatibility with
names that Podman and Docker allow.

This name is used internally if a command needs to be ran against the container
at a later time (e.g., to stop the container when the job is canceled).

~/.ssh/ symlinks
^^^^^^^^^^^^^^^^

In order to make the ``run`` container execution of Ansible
easier, Ansible Runner will automatically bind mount your local ssh agent
UNIX-domain socket (``SSH_AUTH_SOCK``) into the container runtime. However, this
does not work if files in your ``~/.ssh/`` directory happen to be symlinked to
another directory that is also not mounted into the container runtime. The Ansible
Runner ``run`` subcommand provides the ``--container-volume-mount``
option to address this, among other things.

Here is an example of an ssh config file that is a symlink:

::

        $ $ ls -l ~/.ssh/config
        lrwxrwxrwx. 1 myuser myuser 34 Jul 15 19:27 /home/myuser/.ssh/config -> /home/myuser/dotfiles/ssh_config

        $ ansible-runner run \
            --container-volume-mount /home/myuser/dotfiles/:/home/myuser/dotfiles/ \
            --process-isolation --process-isolation-executable podman \
            /tmp/private --playbook my_playbook.yml -i my_inventory.ini
