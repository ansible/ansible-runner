.. _externalintf:

Sending Runner Status and Events to External Systems
====================================================

**Runner** can store event and status data locally for retrieval, it can also emit this information via callbacks provided to the module interface.

Alternatively **Runner** can be configured to send events to an external system via installable plugins. Currently, there are two example plugins are available.

* HTTP Status/Event Emitter Plugin - `ansible-runner-http GitHub repo <https://github.com/ansible/ansible-runner-http>`_
* ZeroMQ Status/Event Emitter Plugin - `ansible-runner-zeromq GitHub repo <https://github.com/ansible/ansible-runner-zeromq>`_

Please refer respective repos to configure these plugins.

.. _plugineventstructure:

Event Structure
---------------

There are two types of events that are emitted via plugins:

* status events:

  These are sent whenever Runner's status changes (see :ref:`runnerstatushandler`) for example::

    {"status": "running", "runner_ident": "XXXX" }

* ansible events:

  These are sent during playbook execution for every event received from **Ansible** (see :ref:`Playbook and Host Events<artifactevents>`) for example::

    {"runner_ident": "XXXX", <rest of event structure> }


Writing your own Plugin
-----------------------

In order to write your own plugin interface and have it be picked up and used by **Runner** there are a few things that you'll need to do.

* Declare the module as a Runner entrypoint in your setup file
  (`ansible-runner-http has a good example of this <https://github.com/ansible/ansible-runner-http/blob/master/setup.py>`_)::

    entry_points=('ansible_runner.plugins': 'modname = your_python_package_name'),

* Implement the ``status_handler()`` and ``event_handler()`` functions at the top of your package, for example see
  `ansible-runner-http events.py <https://github.com/ansible/ansible-runner-http/blob/master/ansible_runner_http/events.py>`_ and the ``__init__``
  import `at the top of the module package <https://github.com/ansible/ansible-runner-http/blob/master/ansible_runner_http/__init__.py>`_

After installing this, **Runner** will see the plugin and invoke the functions when status and events are sent. If there are any errors in your plugin
they will be raised immediately and **Runner** will fail.
