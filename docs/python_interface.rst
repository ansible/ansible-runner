.. _python_interface:

Using Runner as a Python Module Interface to Ansible
====================================================

**Ansible Runner** is intended to provide a directly importable and usable API for interfacing with **Ansible** itself and exposes a few helper interfaces.

The modules center around the :class:`Runner <ansible_runner.runner.Runner>` object. The helper methods will return an instance of this object which provides an
interface to the results of executing the **Ansible** command.

**Ansible Runner** itself is a wrapper around **Ansible** execution and so adds plugins and interfaces to the system in order to gather extra information and
process/store it for use later.

Helper Interfaces
-----------------

The helper :mod:`interfaces <ansible_runner.interface>` provides a quick way of supplying the recommended inputs in order to launch a **Runner** process.

``run()`` helper function
-------------------------

:meth:`ansible_runner.interface.run`

When called, this function will take the inputs (either provided as direct inputs to the function or from the :ref:`inputdir`), and execute **Ansible**. It will run in the
foreground and return the :class:`Runner <ansible_runner.runner.Runner>` object when finished.

``run_async()`` helper function
-------------------------------

:meth:`ansible_runner.interface.run_async`

Takes the same arguments as :meth:`ansible_runner.interface.run` but will launch **Ansible** asynchronously and return a tuple containing
the ``thread`` object and a :class:`Runner <ansible_runner.runner.Runner>` object. The **Runner** object can be inspected during execution.

The ``Runner`` object
---------------------

The :class:`Runner <ansible_runner.runner.Runner>` object is returned as part of the execution of **Ansible** itself. Since it wraps both execution and output
it has some helper methods for inspecting the results. Other than the methods and indirect properties, the instance of the object itself contains two direct
properties:

* ``rc`` will represent the actual return code of the **Ansible** process
* ``status`` will represent the state and can be one of:
   * ``unstarted``: This is a very brief state where the Runner task has been created but hasn't actually started yet.
   * ``successfull``: The ``ansible`` process finished successfully.
   * ``failed``: The ``ansible`` process failed.

``Runner.stdout``
-----------------

The :class:`Runner <ansible_runner.runner.Runner>` object contains a property :attr:`ansible_runner.runner.Runner.stdout` which will return an open file
handle containing the ``stdout`` of the **Ansible** process.

``Runner.events``
-----------------

:attr:`ansible_runner.runner.Runner.events` is a ``generator`` that will return the :ref:`Playbook and Host Events<artifactevents>` as Python ``dict`` objects.

``Runner.stats``
----------------

:attr:`ansible_runner.runner.Runner.stats` is a property that will return the final ``playbook stats`` event from **Ansible** in the form of a Python ``dict``

``Runner.host_events``
:meth:`ansible_runner.runner.Runner.host_events` is a method that, given a hostname, will return a list of only **Ansible** event data executed on that Host.

Usage examples
--------------
.. code-block:: python

  import ansible_runner
  r = ansible_runner.run(private_data_dir='/tmp/demo', playbook='test.yml')
  print("{}: {}".format(r.status, r.rc))
  # successful: 0
  for each_host_event in r.events:
      print(each_host_event.event)
  print("Final status:")
  print(r.stats)


Providing custom behavior and inputs
------------------------------------

**TODO**

The helper methods are just one possible entrypoint, extending the classes used by these helper methods can allow a lot more custom behavior and functionality.

Show:

* How :class:`Runner Config <ansible_runner.runner_config.RunnerConfig>` is used and how overriding the methods and behavior can work
* Show how custom cancel and status callbacks can be supplied.
