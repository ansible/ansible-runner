import pytest

from ansible_runner import RunnerConfig
from ansible_runner.interface import init_runner


def test_default_callback_set(mocker):
    mocker.patch('ansible_runner.interface.signal_handler', side_effect=AttributeError('Raised intentionally'))

    with pytest.raises(AttributeError, match='Raised intentionally'):
        init_runner(RunnerConfig(), "", False)


def test_set_cancel_callback(mocker):
    mock_runner = mocker.patch('ansible_runner.interface.Runner', side_effect=AttributeError('Raised intentionally'))
    mock_runner_config_prepare = mocker.patch('ansible_runner.interface.RunnerConfig.prepare')
    mock_runner_config_prepare.return_value = None

    def custom_cancel_callback():
        return True

    with pytest.raises(AttributeError, match='Raised intentionally'):
        rc = RunnerConfig(cancel_callback=custom_cancel_callback)
        init_runner(rc, "", False)

    assert mock_runner.call_args.kwargs['cancel_callback'] is custom_cancel_callback
