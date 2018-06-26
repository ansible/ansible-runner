.. _container:

Using Runner as a container interface to Ansible
================================================

The design of **Ansible Runner** makes it especially suitable for controlling the execution of **Ansible** from within a container for single-purpose
automation workflows. A reference container image definition is `provided <https://github.com/ansible/ansible-runner/blob/master/Dockerfile>`_ and
is also published to `DockerHub <https://hub.docker.com/r/ansible/ansible-runner/>`_ you can try it out for yourself

.. code-block:: console

  $ docker run --rm -e RUNNER_PLAYBOOK=test.yml ansible/ansible-runner:latest
    Unable to find image 'ansible/ansible-runner:latest' locally                                          
    latest: Pulling from ansible/ansible-runner
    [...]
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

