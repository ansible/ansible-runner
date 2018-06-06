.. _intro:

Introduction to Ansible Runner
==============================

**Runner** is intended to be most useful as part of automation and tooling that needs to invoke Ansible and consume its results.
Most of the parameterization of the **Ansible** command line is also available on the **Runner** command line but **Runner** also
can rely on an input interface that is mapped onto a directory structure an example of which can be seen in `the source tree <https://github.com/ansible/ansible-runner/tree/master/demo>`_

Further sections in this document refer to the configuration and layout of that hierarchy. This isn't the only way to interface with **Runner**
itself. The Python module interface allows supplying these details as direct module parameters in many forms, and the command line interface allows
supplying them directly as arguments mimicing the behavior of ``ansible-playbook``. Having the directory structure **does** allow gathering the inputs
from elsewhere and preparing them for consumption by **Runner**, then the tooling can come along and inspect the results after the run.

This is best seen in the way Ansible **AWX** uses **Runner** where most of the content comes from the database (and other content-management components) but
ultimately needs to be brought together in a single place when launching the **Ansible** task.

Runner Input Directory Hierarchy
--------------------------------

This directory will contain all necessary inputs, here's a view of the `demo directory <https://github.com/ansible/ansible-runner/tree/master/demo>`_ showing
an active configuration.

Note that not everything is required, if not provided defaults will be used or the values will just be omitted.

.. code-block:: none

    .
    ├── env
    │   ├── envvars
    │   ├── extravars
    │   ├── passwords
    │   ├── settings
    │   └── ssh_key
    ├── inventory
    │   └── hosts
    ├── project
    │   └── test.yml
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

Inventory
---------

Projects
--------

Roles
-----

Runner Artifact Directory Hierarchy
-----------------------------------

This directory will contain the results of **Runner** invocation grouped under an ``identifier`` directory.
