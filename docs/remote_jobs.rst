.. _remote_jobs:

Remote job execution
====================

Ansible Runner supports the concept that a job run may be requested on one host but executed on another.
This capability is primarily intended to be used by `Receptor <http://www.github.com/project-receptor/receptor>`_.

Support for this in Runner involves a three phase process.

- **Transmit**: Convert the job to a binary format that can be sent to the worker node.
- **Worker**: Actually execute the job.
- **Process**: Receive job results and process them.

The following command illustrates how the three phases work together::

  $ ansible-runner transmit ./demo -p test.yml | ansible-runner worker | ansible-runner process ./demo

In this example, the ``ansible-runner transmit`` command is given a private data directory of ``./demo`` and told to select
the ``test.yml`` playbook from it.  Instead of executing the playbook as ``ansible-runner run`` would do, the data dir
and command line parameters are converted to a compressed binary stream that is emitted as stdout.  The ``transmit``
command generally takes the same command line parameters as the ``run`` command.

The ``ansible-runner worker`` command accepts this stream, runs the playbook, and generates a new compressed binary
stream of the resulting job events and artifacts.
This command optionally accepts the ``--private-data-dir`` option.
If provided, it will extract the contents sent from ``ansible-runner transmit`` into that directory.

The ``ansible-runner process`` command accepts the result stream from the worker, and fires all the normal callbacks
and does job event processing.  In the command above, this results in printing the playbook output and saving
artifacts to the data dir.  The ``process`` command takes a data dir as a parameter, to know where to save artifacts.

Cleanup of Resources Used by Jobs
---------------------------------

The transmit and process commands do not offer any automatic deletion of the
private data directory or artifacts, because these are how the user interacts with runner.

When running ``ansible-runner worker``, if no ``--private-data-dir`` is given,
it will extract the contents to a temporary directory which is deleted at the end of execution.
If the ``--private-data-dir`` option is given, then the directory will persist after the run finishes
unless the ``--delete`` flag is also set. In that case, the private data directory will be deleted before execution if it exists and also removed after execution.

The following command offers out-of-band cleanup ::

    $ ansible-runner worker cleanup --file-pattern=/tmp/foo_*

This would assure that old directories that fit the file glob ``/tmp/foo_*`` are deleted,
which would could be used to assure cleanup of paths created by commands like
``ansible-runner worker --private_data_dir=/tmp/foo_3``, for example.
NOTE: see the ``--grace-period`` option, which sets the time window.

This command also takes a ``--remove-images`` option to run the podman or docker ``rmi`` command.
There is otherwise no automatic cleanup of images used by a run,
even if ``container_auth_data`` is used to pull from a private container registry.
To be sure that layers are deleted as well, the ``--image-prune`` flag is necessary.

Artifact Directory Specification
--------------------------------

The ``worker`` command does not write artifacts, these are streamed instead, and
the ``process`` command is what ultimately writes the artifacts folder contents.

With the default behavior, ``ansible-runner process ./demo`` would write artifacts to ``./demo/artifacts``.
If you wish to better align with normal ansible-runner use, you can pass the
``--ident`` option to save to a subfolder, so ``ansible-runner process ./demo --ident=43``
would extract artifacts to the folder ``./demo/artifacts/43``.

Python API
----------

Python code importing Ansible Runner can make use of these facilities by setting the ``streamer`` parameter to
``ansible_runner.interface.run``.  This parameter can be set to ``transmit``, ``worker`` or ``process`` to invoke
each of the three stages.  Other parameters are as normal in the CLI.
