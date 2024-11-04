********************************
Ansible Runner 2.5 Porting Guide
********************************

This section discusses the behavioral changes between ``ansible-runner`` version 2.4 and version 2.5.

.. contents:: Topics

Changes to the Python Interface
===============================

:ref:`Remote job execution <remote_jobs>` could experience problems when transmitting job arguments
to a worker node with an older version of ``ansible-runner``. If the older worker received a job
argument that it did not understand, like a new API value, that worker would terminate abnormally.
To address this, a two-stage plan was devised:

#. Modify the streaming job arguments so that only job arguments that have non-default values are
   streamed to the worker node. A new API job argument will not be problematic for older workers
   unless that argument is actually used.
#. Have the worker node fail gracefully on unrecognized job arguments.

The first step of this process is implemented in this version of ``ansible-runner``. The second
step will be completed in a future version.

For this change, it was necessary to modify how the ``run()`` and ``run_async()`` functions
of the :ref:`Python API <python_interface>` are implemented. The API function arguments are now completely
defined in the ``RunnerConfig`` object where we can have better control of the job arguments, and both
functions now take an optional ``config`` parameter.

For backward compatibility, keyword arguments to the ``run()/run_async()`` API functions are passed
along to the ``RunnerConfig`` object initialization for you. Alternatively, you may choose to use
the more up-to-date signature of those API functions where you pass in a manually created ``RunnerConfig``
object. For example:

.. code-block:: python

    import ansible_runner
    config = ansible_runner.RunnerConfig('private_data_dir': '/tmp/demo', 'playbook': 'test.yml')
    r = ansible_runner.interface.run(config=config)

The above is identical to the more familiar usage of the API:

.. code-block:: python

    import ansible_runner
    r = ansible_runner.interface.run('private_data_dir': '/tmp/demo', 'playbook': 'test.yml')
