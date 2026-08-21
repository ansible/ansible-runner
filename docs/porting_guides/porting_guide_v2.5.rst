********************************
Ansible Runner 2.5 Porting Guide
********************************

This section discusses the behavioral changes between Ansible Runner version 2.4 and version 2.5.

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
