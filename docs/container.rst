.. _container:

Using Runner as a container interface to Ansible
================================================

The design of **Ansible Runner** makes it especially suitable for controlling the execution of **Ansible** from within a container for single-purpose
automation workflows. A reference container image definition is `provided <https://github.com/ansible/ansible-runner/blob/master/Dockerfile>`_ and
is also published to `Quay.io <https://quay.io/repository/ansible/ansible-runner>`_.

.. code-block:: console

  $ podman run --rm -e RUNNER_PLAYBOOK=test.yml -v $PWD/demo:/runner quay.io/ansible/ansible-runner:latest
    PLAY [all] *********************************************************************

    TASK [Gathering Facts] *********************************************************
    ok: [localhost]

    TASK [debug] *******************************************************************
    ok: [localhost] => {
      "msg": "Test!"
    }

    PLAY RECAP *********************************************************************
    localhost                  : ok=2    changed=0    unreachable=0    failed=0


The reference container image is purposefully light-weight and only containing the dependencies necessary to run ``ansible-runner`` itself. It's
intended to be overridden.

Overriding the reference container image
----------------------------------------

**TODO**

Gathering output from the reference container image
---------------------------------------------------

**TODO**

Changing the console output to emit raw events
----------------------------------------------

This can be useful when directing task-level event data to an external system by means of the container's console output.

See :ref:`outputjson`

