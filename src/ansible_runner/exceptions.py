
class AnsibleRunnerException(Exception):
    """ Generic Runner Error """


class ConfigurationError(AnsibleRunnerException):
    """ Misconfiguration of Runner """


class CallbackError(AnsibleRunnerException):
    """ Exception occurred in Callback """
