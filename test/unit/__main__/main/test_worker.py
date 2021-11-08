import ansible_runner.__main__ as ansible_runner__main__
import pytest


def test_worker_delete(mocker):
    mock_output = mocker.patch.object(ansible_runner__main__, 'output')
    mock_output.configure.side_effect = AttributeError('Raised intentionally')

    mock_register_for_cleanup = mocker.patch.object(ansible_runner__main__, 'register_for_cleanup')
    mock_rmtree = mocker.patch.object(ansible_runner__main__.shutil, 'rmtree')
    mock_mkdtemp = mocker.patch.object(ansible_runner__main__.tempfile, 'mkdtemp', return_value='some_tmp_dir')

    sys_args = [
        'worker',
        '--delete',
    ]

    with pytest.raises(AttributeError, match='Raised intentionally'):
        ansible_runner__main__.main(sys_args)

    mock_rmtree.assert_not_called()
    mock_register_for_cleanup.assert_called_once_with('some_tmp_dir')
    mock_mkdtemp.assert_called_once()


def test_worker_delete_private_data_dir(mocker, tmp_path):
    mock_output = mocker.patch.object(ansible_runner__main__, 'output')
    mock_output.configure.side_effect = AttributeError('Raised intentionally')

    mock_register_for_cleanup = mocker.patch.object(ansible_runner__main__, 'register_for_cleanup')
    mock_rmtree = mocker.patch.object(ansible_runner__main__.shutil, 'rmtree')
    mock_mkdtemp = mocker.patch.object(ansible_runner__main__.tempfile, 'mkdtemp', return_value='some_tmp_dir')

    sys_args = [
        'worker',
        '--private-data-dir', str(tmp_path),
        '--delete',
    ]

    with pytest.raises(AttributeError, match='Raised intentionally'):
        ansible_runner__main__.main(sys_args)

    mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_register_for_cleanup.assert_called_once_with(str(tmp_path))
    mock_mkdtemp.assert_not_called()
