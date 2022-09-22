.. _python_interface:

Using Runner as a Python Module Interface to Ansible
====================================================

**Ansible Runner** is intended to provide a directly importable and usable API for interfacing with **Ansible** itself and exposes a few helper interfaces.

The modules center around the :class:`Runner <ansible_runner.runner.Runner>` object. The helper methods will either return an instance of this object which provides an
interface to the results of executing the **Ansible** command or a tuple the actual output and error response based on the interface.

**Ansible Runner** itself is a wrapper around **Ansible** execution and so adds plugins and interfaces to the system in order to gather extra information and
process/store it for use later.

Helper Interfaces
-----------------

The helper :mod:`interfaces <ansible_runner.interface>` provides a quick way of supplying the recommended inputs in order to launch a **Runner** process. These interfaces also allow overriding and providing inputs beyond the scope of what the standalone or container interfaces
support. You can see a full list of the inputs in the linked module documentation.

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

``run_command()`` helper function
---------------------------------

:meth:`ansible_runner.interface.run_command`

When called, this function will take the inputs (either provided as direct inputs to the function or from the :ref:`inputdir`), and execute the command passed either
locally or within an container based on the parameters passed. It will run in the foreground and return a tuple of output and error response when finished. While running
the within container image command the current local working diretory will be volume mounted within the container, in addition to this for any of ansible command line
utilities the inventory, vault-password-file, private-key file path will be volume mounted if provided in the ``cmdline_args`` parameters.

``run_command_async()`` helper function
---------------------------------------

:meth:`ansible_runner.interface.run_command_async`

Takes the same arguments as :meth:`ansible_runner.interface.run_command` but will launch asynchronously and return a tuple containing
the ``thread`` object and a :class:`Runner <ansible_runner.runner.Runner>` object. The **Runner** object can be inspected during execution.

``get_plugin_docs()`` helper function
-------------------------------------

:meth:`ansible_runner.interface.get_plugin_docs`

When called, this function will take the inputs, and execute the ansible-doc command to return the either the plugin-docs or playbook snippet for the passed
list of plugin names. The plugin docs can be fetched either from locally installed plugins or from within an container image based on the parameters passed.
It will run in the foreground and return a tuple of output and error response when finished. While running the command within the container the current local
working diretory will be volume mounted within the container.

``get_plugin_docs_async()`` helper function
-------------------------------------------

:meth:`ansible_runner.interface.get_plugin_docs_async`

Takes the same arguments as :meth:`ansible_runner.interface.get_plugin_docs_async` but will launch asynchronously and return a tuple containing
the ``thread`` object and a :class:`Runner <ansible_runner.runner.Runner>` object. The **Runner** object can be inspected during execution.

``get_plugin_list()`` helper function
-------------------------------------

:meth:`ansible_runner.interface.get_plugin_list`

When called, this function will take the inputs, and execute the ansible-doc command to return the list of installed plugins. The installed plugin can be fetched
either from local environment or from within an container image based on the parameters passed. It will run in the foreground and return a tuple of output and error
response when finished. While running the command within the container the current local working diretory will be volume mounted within the container.

``get_inventory()`` helper function
-----------------------------------

:meth:`ansible_runner.interface.get_inventory`

When called, this function will take the inputs, and execute the ansible-inventory command to return the inventory releated information based on the action.
If ``action`` is ``list`` it will return all the applicable configuration options for ansible, for ``host`` action it will return information
of a single host andf for ``graph`` action it will return the inventory. The exectuin will be in the foreground and return a tuple of output and error
response when finished. While running the command within the container the current local working diretory will be volume mounted within the container.

``get_ansible_config()`` helper function
----------------------------------------

:meth:`ansible_runner.interface.get_ansible_config`

When called, this function will take the inputs, and execute the ansible-config command to return the Ansible configuration releated information based on the action.
If ``action`` is ``list`` it will return all the hosts related information including the host and group variables, for ``dump`` action it will return the enitre active configuration
and it can be customized to return only the changed configuration value by settingg the ``only_changed`` boolean parameter to ``True``. For ``view`` action it will return the
view of the active configuration file. The exectuin will be in the foreground and return a tuple of output and error response when finished.
While running the command within the container the current local working diretory will be volume mounted within the container.

``get_role_list()`` helper function
-----------------------------------

:meth:`ansible_runner.interface.get_role_list`

*Version added: 2.2*

This function will execute the ``ansible-doc`` command to return the list of installed roles
that have an argument specification defined. This data can be fetched from either the local
environment or from within a container image based on the parameters passed. It will run in
the foreground and return a tuple of output and error response when finished. Successful output
will be in JSON format as returned from ``ansible-doc``.

``get_role_argspec()`` helper function
--------------------------------------

:meth:`ansible_runner.interface.get_role_argspec`

*Version added: 2.2*

This function will execute the ``ansible-doc`` command to return a role argument specification.
This data can be fetched from either the local environment or from within a container image
based on the parameters passed. It will run in the foreground and return a tuple of output
and error response when finished. Successful output will be in JSON format as returned from
``ansible-doc``.


The ``Runner`` object
---------------------

The :class:`Runner <ansible_runner.runner.Runner>` object is returned as part of the execution of **Ansible** itself. Since it wraps both execution and output
it has some helper methods for inspecting the results. Other than the methods and indirect properties, the instance of the object itself contains two direct
properties:

* ``rc`` will represent the actual return code of the **Ansible** process
* ``status`` will represent the state and can be one of:
   * ``unstarted``: This is a very brief state where the Runner task has been created but hasn't actually started yet.
   * ``successful``: The ``ansible`` process finished successfully.
   * ``failed``: The ``ansible`` process failed.

``Runner.stdout``
-----------------

The :class:`Runner <ansible_runner.runner.Runner>` object contains a property :attr:`ansible_runner.runner.Runner.stdout` which will return an open file
handle containing the `stdout` of the **Ansible** process.

``Runner.stderr``
-----------------

When the ``runner_mode`` is set to ``subprocess`` the :class:`Runner <ansible_runner.runner.Runner>` object uses a property :attr:`ansible_runner.runner.Runner.stderr` which
will return an open file handle containing the ``stderr`` of the **Ansible** process.

``Runner.events``
-----------------

:attr:`ansible_runner.runner.Runner.events` is a ``generator`` that will return the :ref:`Playbook and Host Events<artifactevents>` as Python ``dict`` objects.

``Runner.stats``
----------------

:attr:`ansible_runner.runner.Runner.stats` is a property that will return the final ``playbook stats`` event from **Ansible** in the form of a Python ``dict``

``Runner.host_events``
----------------------
:meth:`ansible_runner.runner.Runner.host_events` is a method that, given a hostname, will return a list of only **Ansible** event data executed on that Host.

``Runner.get_fact_cache``
-------------------------

:meth:`ansible_runner.runner.Runner.get_fact_cache` is a method that, given a hostname, will return a dictionary containing the `Facts <https://docs.ansible.com/ansible/latest/user_guide/playbooks_variables.html#variables-discovered-from-systems-facts>`_ stored for that host during execution.

``Runner.event_handler``
------------------------

A function passed to ``__init__`` of :class:``Runner <ansible_runner.runner.Runner>``, this is invoked every time an Ansible event is received. You can use this to
inspect/process/handle events as they come out of Ansible. This function should return ``True`` to keep the event, otherwise it will be discarded.

``Runner.cancel_callback``
--------------------------

A function passed to ``__init__`` of :class:`Runner <ansible_runner.runner.Runner>`, and to the :meth:`ansible_runner.interface.run` interface functions.
This function will be called for every iteration of the :meth:`ansible_runner.interface.run` event loop and should return `True`
to inform **Runner** cancel and shutdown the **Ansible** process or `False` to allow it to continue.

``Runner.finished_callback``
----------------------------

A function passed to ``__init__`` of :class:`Runner <ansible_runner.runner.Runner>`, and to the :meth:`ansible_runner.interface.run` interface functions.
This function will be called immediately before the **Runner** event loop finishes once **Ansible** has been shut down.

.. _runnerstatushandler:

``Runner.status_handler``
-------------------------

A function passed to ``__init__`` of :class:`Runner <ansible_runner.runner.Runner>` and to the :meth:`ansible_runner.interface.run` interface functions.
This function will be called any time the ``status`` changes, expected values are:

* ``starting``: Preparing to start but hasn't started running yet
* ``running``: The **Ansible** task is running
* ``canceled``: The task was manually canceled either via callback or the cli
* ``timeout``: The timeout configured in Runner Settings was reached (see :ref:`runnersettings`)
* ``failed``: The **Ansible** process failed
* ``successful``: The **Ansible** process succeeded

Usage examples
--------------
.. code-block:: python

  import ansible_runner
  r = ansible_runner.run(private_data_dir='/tmp/demo', playbook='test.yml')
  print("{}: {}".format(r.status, r.rc))
  # successful: 0
  for each_host_event in r.events:
      print(each_host_event['event'])
  print("Final status:")
  print(r.stats)


.. code-block:: python

  import ansible_runner

  def my_artifacts_handler(artifacts_dir):
      # Do something here
      print(artifacts_dir)

  # Do something with artifact directory after the run is complete
  r = ansible_runner.run(private_data_dir='/tmp/demo', playbook='test.yml', artifacts_handler=my_artifacts_handler)


.. code-block:: python

  import ansible_runner

  def my_status_handler(data, runner_config):
      # Do something here
      print(data)

  r = ansible_runner.run(private_data_dir='/tmp/demo', playbook='test.yml', status_handler=my_status_handler)


.. code-block:: python

  import ansible_runner

  def my_event_handler(data):
      # Do something here
      print(data)

  r = ansible_runner.run(private_data_dir='/tmp/demo', playbook='test.yml', event_handler=my_event_handler)

.. code-block:: python

  import ansible_runner
  r = ansible_runner.run(private_data_dir='/tmp/demo', host_pattern='localhost', module='shell', module_args='whoami')
  print("{}: {}".format(r.status, r.rc))
  # successful: 0
  for each_host_event in r.events:
      print(each_host_event['event'])
  print("Final status:")
  print(r.stats)

.. code-block:: python

  from ansible_runner import Runner, RunnerConfig

  # Using tag using RunnerConfig
  rc = RunnerConfig(
      private_data_dir="project",
      playbook="main.yml",
      tags='my_tag',
  )

  rc.prepare()
  r = Runner(config=rc)
  r.run()

.. code-block:: python

  # run the role named 'myrole' contained in the '<private_data_dir>/project/roles' directory
  r = ansible_runner.run(private_data_dir='/tmp/demo', role='myrole')
  print("{}: {}".format(r.status, r.rc))
  print(r.stats)

.. code-block:: python

  # run ansible/generic commands in interactive mode within container
  out, err, rc = ansible_runner.run_command(
      executable_cmd='ansible-playbook',
      cmdline_args=['gather.yaml', '-i', 'inventory', '-vvvv', '-k'],
      input_fd=sys.stdin,
      output_fd=sys.stdout,
      error_fd=sys.stderr,
      host_cwd='/home/demo',
      process_isolation=True,
      container_image='network-ee'
  )
  print("rc: {}".format(rc))
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # run ansible/generic commands in interactive mode locally
  out, err, rc = ansible_runner.run_command(
      executable_cmd='ansible-playbook',
      cmdline_args=['gather.yaml', '-i', 'inventory', '-vvvv', '-k'],
      input_fd=sys.stdin,
      output_fd=sys.stdout,
      error_fd=sys.stderr,
  )
  print("rc: {}".format(rc))
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get plugin docs from within container
  out, err = ansible_runner.get_plugin_docs(
      plugin_names=['vyos.vyos.vyos_command'],
      plugin_type='module',
      response_format='json',
      process_isolation=True,
      container_image='network-ee'
  )
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get plugin docs from within container in async mode
  thread_obj, runner_obj = ansible_runner.get_plugin_docs_async(
      plugin_names=['ansible.netcommon.cli_config', 'ansible.netcommon.cli_command'],
      plugin_type='module',
      response_format='json',
      process_isolation=True,
      container_image='network-ee'
  )
  while runner_obj.status not in ['canceled', 'successful', 'timeout', 'failed']:
      time.sleep(0.01)
      continue

  print("out: {}".format(runner_obj.stdout.read()))
  print("err: {}".format(runner_obj.stderr.read()))

.. code-block:: python

  # get plugin list installed on local system
  out, err = ansible_runner.get_plugin_list()
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get plugins with file list from within container
  out, err = ansible_runner.get_plugin_list(list_files=True, process_isolation=True, container_image='network-ee')
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get list of changed ansible configuration values
  out, err = ansible_runner.get_ansible_config(action='dump',  config_file='/home/demo/ansible.cfg', only_changed=True)
  print("out: {}".format(out))
  print("err: {}".format(err))

  # get ansible inventory information
  out, err = ansible_runner.get_inventory(
      action='list',
      inventories=['/home/demo/inventory1', '/home/demo/inventory2'],
      response_format='json',
      process_isolation=True,
      container_image='network-ee'
  )
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get all roles with an arg spec installed locally
  out, err = ansible_runner.get_role_list()
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get roles with an arg spec from the `foo.bar` collection in a container
  out, err = ansible_runner.get_role_list(collection='foo.bar', process_isolation=True, container_image='network-ee')
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get the arg spec for role `baz` from the locally installed `foo.bar` collection
  out, err = ansible_runner.get_role_argspec('baz', collection='foo.bar')
  print("out: {}".format(out))
  print("err: {}".format(err))

.. code-block:: python

  # get the arg spec for role `baz` from the `foo.bar` collection installed in a container
  out, err = ansible_runner.get_role_argspec('baz', collection='foo.bar', process_isolation=True, container_image='network-ee')
  print("out: {}".format(out))
  print("err: {}".format(err))

Providing custom behavior and inputs
------------------------------------

**TODO**

The helper methods are just one possible entrypoint, extending the classes used by these helper methods can allow a lot more custom behavior and functionality.

Show:

* How :class:`Runner Config <ansible_runner.config.runner.RunnerConfig>` is used and how overriding the methods and behavior can work
* Show how custom cancel and status callbacks can be supplied.
