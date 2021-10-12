import pytest

from ansible_runner.interface import init_runner


def test_default_callback_set(mocker):
    mocker.patch('ansible_runner.interface.signal_handler', side_effect=AttributeError('Raised intentionally'))

    with pytest.raises(AttributeError, match='Raised intentionally'):
        init_runner(ignore_logging=True)


def test_set_cancel_callback(mocker):
    mock_runner = mocker.patch('ansible_runner.interface.Runner', side_effect=AttributeError('Raised intentionally'))
    mock_runner_config = mocker.patch('ansible_runner.interface.RunnerConfig')
    mock_runner_config.prepare.return_value = None

    def custom_cancel_callback():
        return 'custom'

    with pytest.raises(AttributeError, match='Raised intentionally'):
        init_runner(ignore_logging=True, cancel_callback=custom_cancel_callback)

    assert mock_runner.call_args.kwargs['cancel_callback'] is custom_cancel_callback
