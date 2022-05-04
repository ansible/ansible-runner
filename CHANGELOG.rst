============================
ansible-runner Release Notes
============================

.. contents:: Topics


v1.0.2
======

Release Summary
---------------

This is patch release for ansible-runner.


Bugfixes
--------

- Add class reference to handle_termination
- Adding Openshift deployment support
- Adding dockerignore, updating ignore with artifacts dir
- Adding tox test runner and updated test dependencies
- Bumping release for 1.0.2
- Copying default os.environ to pass to pexpect
- Ensure environment variables are properly coerced to strings
- Set self.timed_out instead of self.canceled on idle_timeout event
- Setting fixed pexpect version. Change select() usage to poll()
- Support python 3
- adds loader module to handle file loads
- adds unit test cases for loader.py
- fix pep8 issues and update main interface for roles
- fix up unit test errors for py3 support
- implement Python logging
- merges envvars if one already exists for role execution
- moves entrypoint into bin/ansible-runner and adds role support
- remove unneeded imports exposed by pyflake
- return output when playbook errors
- update entrypoint for ansible-runner

v1.0.1
======

Release Summary
---------------

Initial release of ansible-runner


Bugfixes
--------

- Add base dev image make target
- Add host event interface method to Runner object
- Add stats property to runner object for easy run statistics
- Add stdout property to runner object
- Adding README
- Adding initial runner build and dependency tracking
- Adding license
- Adding module interface documentation
- Break env contexts out into separate files
- Break out env contents to make them more useful
- Bumping version to 1.0.1
- Disable host key checking and retry files
- Fix RPM filename
- Fix an issue truncating the playbook stats lines
- Fix intermittent issue where RELEASE variable was changing
- Fix nested bullets to be Github flavored markdown
- Fix run exit code always being 1
- Fix runner initialization of artifacts
- Fix up unwanted partial file writes and implement event interface
- Fixing python module invocation semantics
- Get the abspath of the private_data_dir
- Initial RPM spec file
- Major refactoring into module code
- Make target / Dockerfile for building RPM
- Misc Python 3 changes execfile(), file(), reduce(), StandardError
- Modernize Python 2 code to get ready for Python 3
- Optimization of Dockerfiles
- Pass through $RELEASE to rpm-builder containers
- Pass through env vars to rpm-builder containers
- Provide status for thread async mode
- Refactoring AWX isolated execution manager into Runner
- Refactoring start and entrypoints
- Remove currently unused memcached dependency
- Removing isolated manager which is unused by standalone runner
- Rename tower display plugins to awx display
- Set capacity to zero if the isolated node has an old version
- Support for executing job and adhoc commands on isolated Tower nodes (#6524)
- Support specifying a run identifier
- Syntax and consistency corrections
- Update isolated instance capacity calculaltion
- Update pexpect package name in RPM spec file
- Update version to 1.0.0
- Updates for python 2/3 support
- Updating dependencies and docker image build
- Updating launcher inputs and arguments
- Updating setup and README to point to public image locations
- Very basic Makefile
- adds feature to dump artifacts to disk
- adds new function to interface for passing playbooks directly
- adds support for inventory based objects
- adds unit test cases for interface changes
- change imports to reflect isolated->expect move
- change stdout composition to generate from job events on the fly
- check if dest file exists and changed
- clean up unused imports
- don't process artifacts from custom `set_stat` calls asynchronously
- fix missing parameter to update_capacity method
- fix up inventory kwarg description
- flake8 comply with new E722 rule
- flake8 comply with new E722 rule
- from six.moves import xrange for Python 3
- generalize stdout event processing to emit events for *all* job types
- initial commit to move folder isolated->expect
- move handling of ssh_keys to after command is built
- properly handle unicode for isolated job buffers
- properly handle unicode for isolated job buffers
- refactor functions into ansible_runner.utils
- replace yaml.load with yaml.safe_load
- stop hard-coding the awx version in the isolated development environment
- update gitignore to ignore pytest_cache/
- update kwarg documentation for inventory
- use absolute path for data dir
