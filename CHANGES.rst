.. :changelog:

Changelog
---------

1.3.1 (2019-03-27)
++++++++++++++++++

- Fixes to make default file permissions much more secure (0600)
- Adding git to the reference container image to support galaxy requests

1.3.0 (2019-03-20)
++++++++++++++++++

- Add support for directory isolation
- Add Debian packaging support
- Add fact caching support
- Add process isolation configuration in the settings file
- Fix event and display issues related to alternative Ansible strategies
- Add Runner config reference to status handler callback
- Add some more direct access to various ansible command line arguments
- Adding playbook stats for "ignored" and "rescued"
- Fix loading of some ansible resources from outside of the private data
  directory (such as projects/playbooks)
- Fix handling of artifact dir when specified outside of the private data
  directory
- Fix an issue where the stdout handle wasn't closed and not all data
  would be flushed
- Fixed extravar loading behavior
- Added support for resolving parent events by associating their event uuid
  as parent_uuid
- Allow PYTHONPATH to be overridden
- Expand support for executing non-ansible tools

1.2.0 (2018-12-19)
++++++++++++++++++

- Add support for runner_on_start from Ansible 2.8
- Fix thread race condition issues in event gathering
- Add Code Of Conduct
- Fix an issue where the "running" status wouldn't be emitted to the
  status callback
- Add process isolation support via bubblewrap
- Fix an issue with orphaned file descriptors
- Add ability to suppress ansible output from the module interface

1.1.2 (2018-10-18)
++++++++++++++++++

- Fix an issue where ssh sock path could be too long
- Fix an issue passing extra vars as dictionaries via the interface
- Fix an issue where stdout was delayed on buffering which also caused
  stdout not to be available if the task was canceled or failed
- Fix role-path parameter not being honored when given on the command line
  Also fixed up unit tests to actually surface this error if it comes back
- Fully onboard Zuul-CI for unit and integration testing

1.1.1 (2018-09-13)
++++++++++++++++++

- Fix an issue when attaching PYTHONPATH environment variable
- Allow selecting a different ansible binary with the RUNNER_BINARY
- Fix --inventory command line arguments
- Fix some issues related to terminating ansible
- Add runner ident to to the event processing callback
- Adding integration tests and improving unit tests

1.1.0 (2018-08-16)
++++++++++++++++++

- Added a feature that supports sending ansible status and events to external systems via a plugin
  interface
- Added support for Runner module users to receive runtime status changes in the form of a callback
  that can be supplied to the run() methods (or passing it directly on Runner initialization)
- Fix an issue where timeout settings were far too short
- Add a new status and return code to indicate Runner timeout occurred.
- Add support for running ad-hoc commands (direct module invocation, ala ansible vs ansible-playbook)
- Fix an issue that caused missing data in events sent to the event handler(s)
- Adding support for supplying role_path in module interface
- Fix an issue where messages would still be emitted when --quiet was used
- Fix a bug where ansible processes could be orphaned after canceling a job
- Fix a bug where calling the Runner stats method would fail on python 3
- Fix a bug where direct execution of roles couldn't be daemonized
- Fix a bug where relative paths couldn't be used when calling start vs run


1.0.5 (2018-07-23)
++++++++++++++++++

- Fix a bug that could cause a hang if unicode environment variables are used
- Allow select() to be used instead of poll() when invoking pexpect
- Check for the presence of Ansible before executing
- Fix an issue where a missing project directory would cause Runner to fail silently
- Add support for automatic cleanup/rotation of artifact directories
- Adding support for Runner module users to receive events in the form of a callback
  that can be supplied to the run() methods (or passing it directly on Runner initialization)
- Adding support for Runner module users to provide a callback that will be invoked when the
  Runner Ansible process has finished. This can be supplied to the run() methods (or passing it
  directly on Runner initialization).


1.0.4 (2018-06-29)
++++++++++++++++++

- Adding support for pexpect 4.6 for performance and efficiency improvements
- Adding support for launching roles directly
- Adding support for changing the output mode to json instead of vanilla Ansible (-j)
- Adding arguments to increase ansible verbosity (-v[vvv]) and quiet mode (-q)
- Adding support for  overriding the artifact directory location
- Adding the ability to pass arbitrary arguments to the invocation of Ansible
- Improving debug and verbose output
- Various fixes for broken python 2/3 compatibility, including the event generator in the python module
- Fixing a bug when providing an ssh key via the private directory interface
- Fixing bugs that prevented Runner from working on MacOS
- Fixing a bug that caused issues when providing extra vars via the private dir interface
