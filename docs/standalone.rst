.. _standalone:

Using Runner as a standalone command line tool
==============================================

The **Ansible Runner** command line tool can be used as a standard command line interface to **Ansible** itself but is primarily intended
to fit into automation and pipeline workflows. Because of this, it has a bit of a different workflow than **Ansible** itself because you can select between a few different modes to launch the command.

While you can launch **Runner** and provide it all of the inputs as arguments to the command line (as you do with **Ansible** itself),
there is another interface where inputs are gathered into a single location referred to in the command line parameters as ``private_data_dir``.
(see :ref:`inputdir`)

To view the parameters accepted by ``ansible-runner``::

  $ ansible-runner --help

An example invocation of the standalone ``ansible-runner`` utility::

  $ ansible-runner -p playbook.yml run /tmp/private

Where playbook.yml is the playbook from the ``/tmp/private/projects`` directory, and ``run`` is the command mode you want to invoke **Runner** with

The different **commands** that runner accepts are:

* ``run`` starts ``ansible-runner`` in the foreground and waits until the underlying **Ansible** process completes before returning
* ``start`` starts ``ansible-runner`` as a background daemon process and generates a pid file
* ``stop`` terminates an ``ansible-runner`` process that was launched in the background with ``start``
* ``is-alive`` checks the status of an ``ansible-runner`` process that was started in the background with ``start``

While **Runner** is running it creates an ``artifacts`` directory (see :ref:`artifactdir`) regardless of what mode it was started
in. The resulting output and status from **Ansible** will be located here. You can control the exact location underneath the ``artifacts`` directory
with the ``-i IDENT`` argument to ``ansible-runner``, otherwise a random UUID will be generated.

Executing **Runner** in the foreground
--------------------------------------

When launching **Runner** with the ``run`` command, as above, the program will stay in the foreground and you'll see output just as you expect from a normal
**Ansible** process. **Runner** will still populate the ``artifacts`` directory, as mentioned in the previous section, to preserve the output and allow processing
of the artifacts after exit.

Executing **Runner** in the background
--------------------------------------

When launching **Runner** with the ``start`` command, the program will generate a pid file and move to the background. You can check its status with the
``is-alive`` command, or terminate it with the ``stop`` command. You can find the stdout, status, and return code in the ``artifacts`` directory.

Running Playbooks
-----------------

An example invocation using ``demo`` as private directory::

  $ ansible-runner --playbook test.yml run demo

Running Roles Directly
----------------------

An example invocation using ``demo`` as private directory and ``localhost`` as target::

  $ ansible-runner --role testrole --hosts localhost run demo

Ansible roles directory can be provided with ``--roles-path`` option. Role variables can be passed with ``--role-vars`` at runtime.

.. _outputjson:

Outputting json (raw event data) to the console instead of normal output
------------------------------------------------------------------------

**Runner** supports outputting json event data structure directly to the console (and stdout file) instead of the standard **Ansible** output, thus
mimicing the behavior of the ``json`` output plugin. This is in addition to the event data that's already present in the artifact directory. All that is needed
is to supply the ``-j`` argument on the command line::

  $ ansible-runner ... -j ...

