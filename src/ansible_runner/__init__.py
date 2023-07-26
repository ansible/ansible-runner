from .utils.importlib_compat import importlib_metadata
from .interface import run, run_async, \
                        run_command, run_command_async, \
                        get_plugin_docs, get_plugin_docs_async, get_plugin_list, \
                        get_role_list, get_role_argspec, \
                        get_inventory, \
                        get_ansible_config     # noqa
from .exceptions import AnsibleRunnerException, ConfigurationError, CallbackError # noqa
from .runner_config import RunnerConfig # noqa
from .runner import Runner # noqa

plugins = {
    entry_point.name: entry_point.load()
    for entry_point
    in importlib_metadata.entry_points(group='ansible_runner.plugins')
}
