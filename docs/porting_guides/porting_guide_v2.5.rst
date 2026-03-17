********************************
Ansible Runner 2.5 Porting Guide
********************************

This section discusses the behavioral changes between Ansible Runner version 2.4 and version 2.5.

API Changes
===========

Fact Cache API Removal
-----------------------

Ansible Runner previously provided APIs for setting and reading values from the Ansible fact cache. However, this
functionality relied on internal implementation details of the fact cache that were never part of Ansible's public
API. With the release of ``ansible-core`` version 2.19, changes to the fact cache implementation broke this
functionality in Ansible Runner.

Since the fact cache APIs in Ansible Runner depended on undocumented behavior, they have been removed in version 2.5.
This change affects the following interface functions, where the ``fact_cache`` and ``fact_cache_type`` parameters
have been removed:

  - `interface.run()`
  - `interface.run_async()`
  - `interface.run_command()`
  - `interface.run_command_async()`
  - `interface.get_ansible_config()`
  - `interface.get_inventory()`
  - `interface.get_plugin_docs()`
  - `interface.get_plugin_docs_async()`
  - `interface.get_plugin_list()`
  - `interface.get_role_argspec()`
  - `interface.get_role_list()`

Additionally, the following methods have been removed from the ``runner.Runner`` class:

  - ``set_fact_cache()``
  - ``get_fact_cache()``
