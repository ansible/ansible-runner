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

Streamed directories are confined to their destination
------------------------------------------------------

Every member of a streamed directory is now required to stay inside the directory it is unpacked into.
This applies to ``ansible-runner worker`` receiving a ``private_data_dir``, and to
``ansible-runner process`` (and the ``Processor`` class) receiving an artifact directory. Previously a
member could be written, or have its permissions and modification time changed, outside of that
directory.

This changes the handling of symbolic links. A link whose target resolves outside the destination is
rejected, and the transfer is aborted:

* An absolute target, such as a link to ``/bin`` or to a file under ``/etc``, is always outside the
  destination and is therefore always rejected.
* A relative target is resolved against the directory holding the link, so one that climbs out with
  ``..`` is rejected as well.

Links whose targets stay within the directory being streamed continue to work unchanged, including
relative links that traverse subdirectories, and links whose target does not exist.

Where a link points is judged once the whole directory has been unpacked, not as each link is
created, so a pair of links that only escapes in combination is rejected as well. Links already
present in the destination are judged alongside the ones being unpacked. A ``private_data_dir``
that is reused without ``--delete`` and has been left holding a link out of the directory, by an
earlier job or otherwise, therefore causes later transfers into it to fail until it is cleared.

A ``private_data_dir`` containing such a link transmitted successfully before and now fails on the
worker, reported as ``Failed to extract private data directory on worker.``; the equivalent failure for
an artifact directory is reported as an error status by the processor. If a job depends on content
outside the ``private_data_dir``, copy that content into the directory instead of linking to it.

Members are also written to the path formed by the destination and the member name with any ``..``
segments resolved, rather than removed. Streams produced by ``ansible-runner`` never contain such
segments, so this only affects hand-crafted ones.

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
