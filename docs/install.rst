.. _install:

Installing Ansible Runner
=========================

Ansible Runner is provided from several different locations depending on how you want to use it.

Using pip
---------

Python 2.7+ and 3.6+ are supported and installable via pip::

  $ pip install ansible-runner


Fedora
------

To install from the latest Fedora sources::

  $ dnf install python-ansible-runner

Debian
------

Add an ansible-runner repository::

  $ apt-get update
  $ echo 'deb https://releases.ansible.com/ansible-runner/deb/ <trusty|xenial|stretch> main' > /etc/apt/sources.list.d/ansible.list

Add a key::

  $ apt-key adv --keyserver keyserver.ubuntu.com --recv 3DD29021

Install the package::

  $ apt-get update
  $ apt-get install ansible-runner


From source
-----------

Ansible Runner uses `python-poetry <https://python-poetry.org/`_ for
development and dependency management, once that is installed performed the
following steps.

Check out the source code from `github <https://github.com/ansible/ansible-runner>`_::

  $ git clone git://github.com/ansible/ansible-runner

Or download from the `releases page <https://github.com/ansible/ansible-runner/releases>`_

Then install::

  $ poetry install

.. _builddist:

Build the distribution
----------------------

To produce an installable ``wheel`` file::

  make dist

To produce a distribution tarball::

  make sdist

.. _buildcontimg:

Building the base container image
---------------------------------

Make sure the ``wheel`` distribution is built (see :ref:`builddist`) and run::

  make image

Building the RPM
----------------

The RPM build uses a container image to bootstrap the environment in order to produce the RPM. Make sure you have docker
installed and proceed with::

  make rpm

.. include:: ../CHANGES.rst
