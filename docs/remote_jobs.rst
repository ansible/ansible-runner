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

In this example, the `ansible-runner transmit` command is given a private data directory of `./demo` and told to select
the `test.yml` playbook from it.  Instead of executing the playbook as `ansible-runner run` would do, the data dir
and command line parameters are converted to a compressed binary stream that is emitted as stdout.  The `transmit`
command generally takes the same command line parameters as the `run` command.

The `ansible-runner worker` command accepts this stream, runs the playbook, and generates a new compressed binary
stream of the resulting job events and artifacts.
This command optionally accepts the `--private-data-dir` option.
If provided, it will extract the contents sent from `ansible-runner transmit` into that directory.
If no `--private-data-dir` is given, then it will extract the contents to a temporary directory,
which will be deleted at the end of execution.

The `ansible-runner process` command accepts the result stream from the worker, and fires all the normal callbacks
and does job event processing.  In the command above, this results in printing the playbook output and saving
artifacts to the data dir.  The `process` command takes a data dir as a parameter, to know where to save artifacts.

Python API
----------

Python code importing Ansible Runner can make use of these facilities by setting the `streamer` parameter to
`ansible_runner.interface.run`.  This parameter can be set to `transmit`, `worker` or `process` to invoke
each of the three stages.  Other parameters are as normal in the CLI.
