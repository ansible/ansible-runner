from ansible_runner.__main__ import valid_inventory


def test_valid_inventory_file_in_inventory(tmp_path):
    """
    Test a relative file name within inventory subdir.
    """
    data_dir = tmp_path / "datadir"
    inv_dir = data_dir / "inventory"
    inv_dir.mkdir(parents=True)

    hosts = inv_dir / "hosts.xyz"
    hosts.touch()

    assert valid_inventory(str(data_dir), "hosts.xyz") == str(hosts.absolute())


def test_valid_inventory_absolute_path_to_file(tmp_path):
    """
    Test an absolute path to a file outside of data dir.
    """
    data_dir = tmp_path / "datadir"
    inv_dir = data_dir / "inventory"
    inv_dir.mkdir(parents=True)

    (tmp_path / "otherdir").mkdir()
    hosts = tmp_path / "otherdir" / "hosts.xyz"
    hosts.touch()

    assert valid_inventory(str(data_dir), str(hosts.absolute())) == str(hosts.absolute())


def test_valid_inventory_absolute_path_to_directory(tmp_path):
    """
    Test an absolute path to a directory outside of data dir.
    """
    data_dir = tmp_path / "datadir"
    inv_dir = data_dir / "inventory"
    inv_dir.mkdir(parents=True)

    (tmp_path / "otherdir").mkdir()
    hosts = tmp_path / "otherdir"
    hosts.touch()

    assert valid_inventory(str(data_dir), str(hosts.absolute())) == str(hosts.absolute())


def test_valid_inventory_doesnotexist(tmp_path):
    """
    Test that a bad inventory path returns False.
    """
    assert valid_inventory(str(tmp_path), "doesNotExist") is None
