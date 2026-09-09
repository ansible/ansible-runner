********************************
Ansible Runner 2.5 Porting Guide
********************************

This section discusses the behavioral changes between Ansible Runner version 2.4 and version 2.5.

Behavior Changes
================

Removal of the ``python-daemon`` dependency
-------------------------------------------

The ``python-daemon`` package is no longer a dependency of Ansible Runner. It relied on the ``lockfile``
package, which has been unmaintained since 2015. The small amount of functionality that Ansible Runner
used from it is now implemented directly. Packagers should drop ``python-daemon`` from their
requirements.

This changes the behavior of the ``ansible-runner start`` command in the following ways:

* The file mode creation mask (``umask``) of the invoking process is now inherited by the background
  process. Previously it was reset to ``0``, which made every file and directory the background process
  created world writable.
* File descriptors inherited by the background process are no longer closed. In particular, this means
  that ``--logfile`` now works with the ``start`` command, where before it silently produced an empty
  file.
* The standard error of the background process is appended to ``<private_data_dir>/daemon.log`` instead
  of being discarded. Its standard output continues to be discarded.
* If a background process is already running for the given ``private_data_dir``, ``start`` now reports
  the running process ID and exits with a return code of ``1`` instead of raising an unhandled exception.
* A pid file left behind by a process that no longer exists is now discarded and reused, instead of
  preventing any further use of the ``start`` command for that ``private_data_dir``.
* ``start`` no longer returns until the pid file has been created.

Deprecations
============

The following features are being deprecated in this version of Ansible Runner. They will be removed
in a future version.

API Deprecations
----------------

The following methods of the :class:`Runner <ansible_runner.runner.Runner>` class are being deprecated:

* ``get_fact_cache()``
* ``set_fact_cache()``

These methods depended on the internal workings of how fact caching was stored. The storage details were
changed in ``ansible-core`` version ``2.19``, so these methods will not work correctly using that version
or above. Because of this, these methods are slotted for removal.

Bubblewrap
----------

Support of ``bubblewrap`` (or ``bwrap``) for process isolation is being deprecated.
This has been superseded by the use of Execution Environments.
