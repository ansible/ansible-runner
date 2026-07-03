.. _apple_container:

Apple Container Notes
=====================

This document gathers the ansible-runner specific behavior, requirements, and
trade-offs for using `apple/container <https://github.com/apple/container>`_
as the container runtime for execution environments.

What this document is for
-------------------------

Use this document when:

* ``process_isolation_executable=container`` is selected
* execution-environment behavior differs from Docker or Podman
* you need to understand runner-specific limits of the Apple Container path

Requirements
------------

Using Apple Container with ansible-runner currently assumes:

* Apple Container is installed and working on macOS
* the ``container`` CLI is on ``PATH``
* the execution-environment image is already available locally or can be pulled
* any required private-registry authentication has already been established with
  ``container registry login <registry>``

Authentication model
--------------------

Apple Container does not use the same per-run auth-file injection model that
ansible-runner uses for Docker and Podman.

For Docker and Podman, ansible-runner can prepare temporary registry-auth
material and pass it to the runtime command.

For Apple Container, ansible-runner does **not** log in or log out of registries
on the user's behalf. Instead:

* if a private registry is needed, authenticate first with
  ``container registry login <registry>``
* if ``container_auth_data`` is supplied while
  ``process_isolation_executable=container`` is selected, ansible-runner fails
  early with a message telling the user to authenticate first

This is intentional. It keeps ansible-runner from mutating persistent host
registry-login state for Apple Container.

Runtime behavior
----------------

The Apple Container execution-environment path currently uses:

* ``container run``
* ``container kill``
* ``container image list``
* ``container image delete``
* ``container image prune --all``

When launching an execution environment, ansible-runner currently:

* uses bind mounts and ``--env-file`` like the other runtimes
* uses ``--user=<uid>:<gid>`` for Apple Container
* does **not** emit Podman-only flags such as ``--quiet``, ``--group-add=root``,
  or ``--ipc=host``
* does **not** apply SELinux relabel mount suffixes like ``:Z`` or ``:z`` to
  Apple Container-managed mounts

Passing Apple Container-specific runtime options
------------------------------------------------

If you need Apple Container-specific runtime features, pass them through the
normal runner container-options interface rather than expecting runner to manage
them automatically.

CLI examples
^^^^^^^^^^^^

The standalone CLI accepts repeated ``--container-option`` arguments.

Forward the host SSH agent socket using Apple Container's native flag::

  $ ansible-runner run demo \
      --process-isolation \
      --process-isolation-executable container \
      --container-image ghcr.io/ansible/community-ansible-dev-tools:latest \
      --container-option=--ssh \
      -p playbook.yml

Enable nested virtualization for the container::

  $ ansible-runner run demo \
      --process-isolation \
      --process-isolation-executable container \
      --container-image ghcr.io/ansible/community-ansible-dev-tools:latest \
      --container-option=--virtualization \
      -p playbook.yml

Enable Rosetta support in the container::

  $ ansible-runner run demo \
      --process-isolation \
      --process-isolation-executable container \
      --container-image ghcr.io/ansible/community-ansible-dev-tools:latest \
      --container-option=--rosetta \
      -p playbook.yml

Python API example
^^^^^^^^^^^^^^^^^^

The Python interface passes these through ``container_options``::

  import ansible_runner

  ansible_runner.run(
      private_data_dir="demo",
      playbook="playbook.yml",
      process_isolation=True,
      process_isolation_executable="container",
      container_image="ghcr.io/ansible/community-ansible-dev-tools:latest",
      container_options=["--ssh", "--rosetta"],
  )

Notes on these options
^^^^^^^^^^^^^^^^^^^^^^

``--ssh``
  Usually the most useful Apple-specific option. It forwards the host SSH agent
  using Apple Container's native mechanism, instead of relying only on manual
  socket mount conventions.

``--virtualization``
  Exposes virtualization capabilities to the container. This depends on host
  support and guest support and should be used only for workloads that
  explicitly need nested virtualization.

``--rosetta``
  Enables Rosetta in the container, which can be useful when a workflow needs
  x86_64 binaries on Apple Silicon. This should be treated as a compatibility
  aid, not a default.

Advantages
----------

Using Apple Container has some practical benefits on macOS:

* native Apple tooling instead of depending on Docker Desktop or Podman
* runtime command support for the EE launch model used by ansible-runner
* native registry login workflow through ``container registry login``
* native image lifecycle commands for list, inspect, delete, and prune

Handicaps and trade-offs
------------------------

The Apple Container path is functional, but it is not identical to Docker or
Podman in all operational details.

Important trade-offs:

* no Docker/Podman-style auth-file injection for runtime pulls
* private-registry access depends on pre-existing Apple Container login state
* cleanup and image lifecycle use Apple-native commands, not Docker/Podman
  equivalents
* runtime-specific mount and label behavior differs from Podman and Docker

This means that scripts or operational habits built around Docker or Podman
flags should not be assumed to transfer unchanged to Apple Container.

FAQ
---

Why does ansible-runner reject ``container_auth_data`` for Apple Container?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Because Apple Container does not match the Docker/Podman auth-file model used by
runner. The supported model is to authenticate before the run with
``container registry login <registry>``.

Why not make ansible-runner perform ``container registry login`` automatically?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

That would require ansible-runner to mutate persistent host registry-login state.
The current design avoids that and keeps Apple Container authentication as an
explicit user or environment responsibility.

What should I do if a protected image pull fails?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Log in to the registry first with ``container registry login <registry>`` and
retry the run.

Is this intended to be a generic runtime abstraction?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

No. The current implementation is explicit and runtime-specific. That is
deliberate. A broader abstraction should only be introduced if the number of
runtime-specific branches grows enough to justify it.
