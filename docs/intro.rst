.. _intro:

Introduction to Ansible Runner
==============================

**Runner** is intended to be most useful as part of automation and tooling that needs to invoke Ansible and consume its results.
Most of the parameterization of the **Ansible** command line is also available on the **Runner** command line but **Runner** also
can rely on an input interface that is mapped onto a directory structure, an example of which can be seen in `the source tree <https://github.com/ansible/ansible-runner/tree/devel/demo>`_.

Further sections in this document refer to the configuration and layout of that hierarchy. This isn't the only way to interface with **Runner**
itself. The Python module interface allows supplying these details as direct module parameters in many forms, and the command line interface allows
supplying them directly as arguments, mimicking the behavior of ``ansible-playbook``. Having the directory structure **does** allow gathering the inputs
from elsewhere and preparing them for consumption by **Runner**, then the tooling can come along and inspect the results after the run.

This is best seen in the way Ansible **AWX** uses **Runner** where most of the content comes from the database (and other content-management components) but
ultimately needs to be brought together in a single place when launching the **Ansible** task.

.. _inputdir:

Runner Input Directory Hierarchy
--------------------------------

This directory contains all necessary inputs. Here's a view of the `demo directory <https://github.com/ansible/ansible-runner/tree/devel/demo>`_ showing
an active configuration.

Note that not everything is required. Defaults will be used or values will be omitted if they are not provided.

.. code-block:: none

    .
    ├── env
    │   ├── envvars
    │   ├── extravars
    │   ├── passwords
    │   ├── cmdline
    │   ├── settings
    │   └── ssh_key
    ├── inventory
    │   └── hosts
    └── project
        ├── test.yml
        └── roles
            └── testrole
                ├── defaults
                ├── handlers
                ├── meta
                ├── README.md
                ├── tasks
                ├── tests
                └── vars

The ``env`` directory
---------------------

The **env** directory contains settings and sensitive files that inform certain aspects of the invocation of the **Ansible** process, an example of which can
be found in `the demo env directory <https://github.com/ansible/ansible-runner/tree/devel/demo/env>`_. Each of these files can also be represented by a named
pipe providing a bit of an extra layer of security. The formatting and expectation of these files differs slightly depending on what they are representing.

``env/envvars``
---------------

.. note::

   For an example see `the demo envvars <https://github.com/ansible/ansible-runner/blob/devel/demo/env/envvars>`_.

**Ansible Runner** will inherit the environment of the launching shell (or container, or system itself). This file (which can be in json or yaml format) represents
the environment variables that will be added to the environment at run-time::

  ---
  TESTVAR: exampleval

``env/extravars``
-----------------

.. note::

   For an example see `the demo extravars <https://github.com/ansible/ansible-runner/blob/devel/demo/env/extravars>`_.

**Ansible Runner** gathers the extra vars provided here and supplies them to the **Ansible Process** itself. This file can be in either json or yaml format::

  ---
  ansible_connection: local
  test: val

``env/passwords``
-----------------

.. note::

   For an example see `the demo passwords <https://github.com/ansible/ansible-runner/blob/devel/demo/env/passwords>`_.

.. warning::

   We expect this interface to change/simplify in the future but will guarantee backwards compatibility. The goal is for the user of **Runner** to not
   have to worry about the format of certain prompts emitted from **Ansible** itself. In particular, vault passwords need to become more flexible.

**Ansible** itself is set up to emit passwords to certain prompts, these prompts can be requested (``-k`` for example to prompt for the connection password).
Likewise, prompts can be emitted via `vars_prompt <https://docs.ansible.com/ansible/latest/user_guide/playbooks_prompts.html>`_ and also
`Ansible Vault <https://docs.ansible.com/ansible/2.5/user_guide/vault.html#vault-ids-and-multiple-vault-passwords>`_.

In order for **Runner** to respond with the correct password, it needs to be able to match the prompt and provide the correct password. This is currently supported
by providing a yaml or json formatted file with a regular expression and a value to emit, for example::

  ---
  "^SSH password:\\s*?$": "some_password"
  "^BECOME password.*:\\s*?$": "become_password"

``env/cmdline``
---------------

.. warning::

    Current **Ansible Runner** does not validate the command line arguments passed using this method so it is up to the playbook writer to provide a valid set of options.
    The command line options provided by this method are lower priority than the ones set by **Ansible Runner**.  For instance, this will not override ``inventory`` or ``limit`` values.

**Ansible Runner** gathers command line options provided here as a string and supplies them to the **Ansible Process** itself. This file should contain the arguments to be added, for example::

  --tags one,two --skip-tags three -u ansible --become

``env/ssh_key``
---------------

.. note::

   Currently only a single ssh key can be provided via this mechanism but this is set to `change soon <https://github.com/ansible/ansible-runner/issues/51>`_.

This file should contain the ssh private key used to connect to the host(s). **Runner** detects when a private key is provided and will wrap the call to
**Ansible** in ssh-agent.

.. _runnersettings:

``env/settings`` - Settings for Runner itself
---------------------------------------------

The **settings** file is a little different than the other files provided in this section in that its contents are meant to control **Runner** directly.

* ``idle_timeout``: ``600`` If no output is detected from ansible in this number of seconds the execution will be terminated.
* ``job_timeout``: ``3600`` The maximum amount of time to allow the job to run for, exceeding this and the execution will be terminated.
* ``pexpect_timeout``: ``10`` Number of seconds for the internal pexpect command to wait to block on input before continuing
* ``pexpect_use_poll``: ``True`` Use ``poll()`` function for communication with child processes instead of ``select()``. ``select()`` is used when the value is set to ``False``. ``select()`` has a known limitation of using only up to 1024 file descriptors.

* ``suppress_output_file``: ``False`` Allow output from ansible to not be streamed to the ``stdout`` or ``stderr`` files inside of the artifacts directory.
* ``suppress_ansible_output``: ``False`` Allow output from ansible to not be printed to the screen.
* ``fact_cache``: ``'fact_cache'`` The directory relative to ``artifacts`` where ``jsonfile`` fact caching will be stored.  Defaults to ``fact_cache``.  This is ignored if ``fact_cache_type`` is different than ``jsonfile``.
* ``fact_cache_type``: ``'jsonfile'`` The type of fact cache to use.  Defaults to ``jsonfile``.

Process Isolation Settings for Runner
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The process isolation settings are meant to control the process isolation feature of **Runner**.

* ``process_isolation``: ``False`` Enable limiting what directories on the filesystem the playbook run has access to.
* ``process_isolation_executable``: ``bwrap`` Path to the executable that will be used to provide filesystem isolation.
* ``process_isolation_path``: ``/tmp`` Path that an isolated playbook run will use for staging.
* ``process_isolation_hide_paths``: ``None`` Path or list of paths on the system that should be hidden from the playbook run.
* ``process_isolation_show_paths``: ``None`` Path or list of paths on the system that should be exposed to the playbook run.
* ``process_isolation_ro_paths``: ``None`` Path or list of paths on the system that should be exposed to the playbook run as read-only.

These settings instruct **Runner** to execute **Ansible** tasks inside a container environment.
A default execution environment is provided on Quay.io at `ansible/ansible-runner <https://quay.io/repository/ansible/ansible-runner>`_.

To execute **Runner** with an execution environment:

``ansible-runner run --container-image quay.io/ansible/ansible-runner:devel --process-isolation -p playbook.yml .``

See ``ansible-runner -h`` for other container-related options.

Inventory
---------

The **Runner** ``inventory`` location under the private data dir has the same expectations as inventory provided directly to ansible itself. It can
be either a single file or script or a directory containing static inventory files or scripts. This inventory is automatically loaded and provided to
**Ansible** when invoked and can be further overridden on the command line or via the ``ANSIBLE_INVENTORY`` environment variable to specify the hosts directly.
Giving an absolute path for the inventory location is best practice, because relative paths are interpreted relative to the ``current working directory``
which defaults to the ``project`` directory.

Project
--------

The **Runner** ``project`` directory  is the playbook root containing playbooks and roles that those playbooks can consume directly. This is also the
directory that will be set as the ``current working directory`` when launching the **Ansible** process.


Modules
-------

**Runner** has the ability to execute modules directly using Ansible ad-hoc mode.

Roles
-----

**Runner** has the ability to execute `Roles <https://docs.ansible.com/ansible/latest/user_guide/playbooks_reuse_roles.html>`_ directly without first needing
a playbook to reference them. This directory holds roles used for that. Behind the scenes, **Runner** will generate a playbook and invoke the ``Role``.

.. _artifactdir:

Runner Artifacts Directory Hierarchy
------------------------------------

This directory will contain the results of **Runner** invocation grouped under an ``identifier`` directory. This identifier can be supplied to **Runner** directly
and if not given, an identifier will be generated as a `UUID <https://docs.python.org/3/library/uuid.html#uuid.uuid4>`_. This is how the directory structure looks
from the top level::

    .
    ├── artifacts
    │   └── identifier
    ├── env
    ├── inventory
    ├── profiling_data
    ├── project
    └── roles

The artifact directory itself contains a particular structure that provides a lot of extra detail from a running or previously-run invocation of Ansible/Runner::

    .
    ├── artifacts
    │   └── 37f639a3-1f4f-4acb-abee-ea1898013a25
    │       ├── fact_cache
    │       │   └── localhost
    │       ├── job_events
    │       │   ├── 1-34437b34-addd-45ae-819a-4d8c9711e191.json
    │       │   ├── 2-8c164553-8573-b1e0-76e1-000000000006.json
    │       │   ├── 3-8c164553-8573-b1e0-76e1-00000000000d.json
    │       │   ├── 4-f16be0cd-99e1-4568-a599-546ab80b2799.json
    │       │   ├── 5-8c164553-8573-b1e0-76e1-000000000008.json
    │       │   ├── 6-981fd563-ec25-45cb-84f6-e9dc4e6449cb.json
    │       │   └── 7-01c7090a-e202-4fb4-9ac7-079965729c86.json
    │       ├── rc
    │       ├── status
    │       └── stdout


The **rc** file contains the actual return code from the **Ansible** process.

The **status** file contains one of three statuses suitable for displaying:

* success: The **Ansible** process finished successfully
* failed: The **Ansible** process failed
* timeout: The **Runner** timeout (see :ref:`runnersettings`)

The **stdout** file contains the actual stdout as it appears at that moment.

.. _artifactevents:

Runner Artifact Job Events (Host and Playbook Events)
-----------------------------------------------------

**Runner** gathers the individual task and playbook events that are emitted as part of the **Ansible** run. This is extremely helpful if you don't want
to process or read the stdout returned from **Ansible** as it contains much more detail and status than just the plain stdout.
It does some of the heavy lifting of assigning order to the events and stores them in json format under the ``job_events`` artifact directory.
It also takes it a step further than normal **Ansible** callback plugins in that it will store the ``stdout`` associated with the event alongside the raw
event data (along with stdout line numbers). It also generates dummy events for stdout that didn't have corresponding host event data::

    {
      "uuid": "8c164553-8573-b1e0-76e1-000000000008",
      "parent_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "counter": 5,
      "stdout": "\r\nTASK [debug] *******************************************************************",
      "start_line": 5,
      "end_line": 7,
      "event": "playbook_on_task_start",
      "event_data": {
        "playbook": "test.yml",
        "playbook_uuid": "34437b34-addd-45ae-819a-4d8c9711e191",
        "play": "all",
        "play_uuid": "8c164553-8573-b1e0-76e1-000000000006",
        "play_pattern": "all",
        "task": "debug",
        "task_uuid": "8c164553-8573-b1e0-76e1-000000000008",
        "task_action": "debug",
        "task_path": "\/home\/mjones\/ansible\/ansible-runner\/demo\/project\/test.yml:3",
        "task_args": "msg=Test!",
        "name": "debug",
        "is_conditional": false,
        "pid": 10640
      },
      "pid": 10640,
      "created": "2018-06-07T14:54:58.410605"
    }

If the playbook runs to completion without getting killed, the last event will always be the ``stats`` event::

    {
      "uuid": "01c7090a-e202-4fb4-9ac7-079965729c86",
      "counter": 7,
      "stdout": "\r\nPLAY RECAP *********************************************************************\r\n\u001b[0;32mlocalhost,\u001b[0m                 : \u001b[0;32mok=2   \u001b[0m changed=0    unreachable=0    failed=0   \r\n",
      "start_line": 10,
      "end_line": 14,
      "event": "playbook_on_stats",
      "event_data": {
        "playbook": "test.yml",
        "playbook_uuid": "34437b34-addd-45ae-819a-4d8c9711e191",
        "changed": {

        },
        "dark": {

        },
        "failures": {

        },
        "ok": {
          "localhost,": 2
        },
        "processed": {
          "localhost,": 1
        },
        "skipped": {

        },
        "artifact_data": {

        },
        "pid": 10640
      },
      "pid": 10640,
      "created": "2018-06-07T14:54:58.424603"
    }

.. note::

   The **Runner module interface** presents a programmatic interface to these events that allow getting the final status and performing host filtering of task events.

Runner Profiling Data Directory
-------------------------------

If resource profiling is enabled for **Runner** the ``profiling_data`` directory will be populated with a set of files containing the profiling data::

    .
    ├── profiling_data
    │   ├── 0-34437b34-addd-45ae-819a-4d8c9711e191-cpu.json
    │   ├── 0-34437b34-addd-45ae-819a-4d8c9711e191-memory.json
    │   ├── 0-34437b34-addd-45ae-819a-4d8c9711e191-pids.json
    │   ├── 1-8c164553-8573-b1e0-76e1-000000000006-cpu.json
    │   ├── 1-8c164553-8573-b1e0-76e1-000000000006-memory.json
    │   └── 1-8c164553-8573-b1e0-76e1-000000000006-pids.json

Each file is in `JSON text format <https://tools.ietf.org/html/rfc7464#section-2.2>`_. Each line of the file will begin with a record separator (RS), continue with a JSON dictionary, and conclude with a line feed (LF) character. The following provides an example of what the resource files may look like. Note that that since the RS and LF are control characters, they are not actually printed below::

    ==> 0-525400c9-c704-29a6-4107-00000000000c-cpu.json <==
    {"timestamp": 1568977988.6844425, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 97.12799768097156}
    {"timestamp": 1568977988.9394386, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 94.17538298892688}
    {"timestamp": 1568977989.1901696, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 64.38272588006255}
    {"timestamp": 1568977989.4594045, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 83.77387744259856}

    ==> 0-525400c9-c704-29a6-4107-00000000000c-memory.json <==
    {"timestamp": 1568977988.4281094, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 36.21484375}
    {"timestamp": 1568977988.6842303, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 57.87109375}
    {"timestamp": 1568977988.939303, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 66.60546875}
    {"timestamp": 1568977989.1900482, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 71.4609375}
    {"timestamp": 1568977989.4592078, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 38.25390625}

    ==> 0-525400c9-c704-29a6-4107-00000000000c-pids.json <==
    {"timestamp": 1568977988.4284189, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 5}
    {"timestamp": 1568977988.6845856, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 6}
    {"timestamp": 1568977988.939547, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 8}
    {"timestamp": 1568977989.1902773, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 13}
    {"timestamp": 1568977989.4593227, "task_name": "Gathering Facts", "task_uuid": "525400c9-c704-29a6-4107-00000000000c", "value": 6}

* Resource profiling data is grouped by playbook task.
* For each task, there will be three files, corresponding to cpu, memory and pid count data.
* Each file contains a set of data points collected over the course of a playbook task.
* If a task executes quickly and the polling rate for a given metric is large enough, it is possible that no profiling data may be collected during the task's execution. If this is the case, no data file will be created.
