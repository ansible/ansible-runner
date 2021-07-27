from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'other_callback'

    def v2_playbook_on_play_start(self, play):
        pass

    def v2_runner_on_ok(self, result):
        pass
