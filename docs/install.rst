.. _install:

Installing Ansible Runner
=========================

Ansible Runner requires Python >= 3.8 and is provided from several different locations depending on how you want to use it.

Using pip
---------

To install the latest version from the Python Package Index::

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

Check out the source code from `github <https://github.com/ansible/ansible-runner>`_::

  $ git clone git://github.com/ansible/ansible-runner

Or download from the `releases page <https://github.com/ansible/ansible-runner/releases>`_

Create a virtual environment using Python and activate it::

  $ virtualenv env
  $ source env/bin/activate

Then install::

  $ cd ansible-runner
  $ pip install -e .

.. _builddist:

Build the distribution
----------------------

To produce both wheel and sdist::

  make dist

To produce an installable ``wheel``::

  make wheel

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

