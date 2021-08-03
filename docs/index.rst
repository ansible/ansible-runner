.. ansible-runner documentation master file, created by
   sphinx-quickstart on Tue May  1 10:47:37 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Ansible Runner
==============

Ansible Runner is a tool and python library that helps when interfacing with Ansible directly or as part of another system
whether that be through a container image interface, as a standalone tool, or as a Python module that can be imported. The goal
is to provide a stable and consistent interface abstraction to Ansible. This allows **Ansible** to be embedded into other systems that don't
want to manage the complexities of the interface on their own (such as CI/CD platforms, Jenkins, or other automated tooling).

**Ansible Runner** represents the modularization of the part of `Ansible Tower/AWX <https://github.com/ansible/awx>`_ that is responsible
for running ``ansible`` and ``ansible-playbook`` tasks and gathers the output from it. It does this by presenting a common interface that doesn't
change, even as **Ansible** itself grows and evolves.

Part of what makes this tooling useful is that it can gather its inputs in a flexible way (See :ref:`intro`:). It also has a system for storing the
output (stdout) and artifacts (host-level event data, fact data, etc) of the playbook run.

There are 3 primary ways of interacting with **Runner**

* A standalone command line tool (``ansible-runner``) that can be started in the foreground or run in the background asynchronously
* A reference container image that can be used as a base for your own images and will work as a standalone container or running in
  Openshift or Kubernetes
* A python module - library interface

**Ansible Runner** can also be configured to send status and event data to other systems using a plugin interface, see :ref:`externalintf`.

Examples of this could include:

* Sending status to Ansible Tower/AWX
* Sending events to an external logging service


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   intro
   install
   external_interface
   standalone
   python_interface
   execution_environments
   container
   remote_jobs
   modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
