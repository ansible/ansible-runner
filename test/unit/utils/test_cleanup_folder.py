from ansible_runner.utils import cleanup_folder


def test_cleanup_folder(tmp_path):
    folder_path = tmp_path / 'a_folder'
    folder_path.mkdir()
    assert folder_path.exists()  # sanity
    cleanup_folder(str(folder_path))
    assert not folder_path.exists()


def test_cleanup_folder_already_deleted(tmp_path):
    missing_dir = tmp_path / 'missing'
    assert not missing_dir.exists()  # sanity
    cleanup_folder(str(missing_dir))
    assert not missing_dir.exists()


def test_cleanup_folder_file_no_op(tmp_path):
    file_path = tmp_path / 'a_file'
    file_path.write_text('foobar')
    cleanup_folder(str(file_path))
    assert file_path.exists()
