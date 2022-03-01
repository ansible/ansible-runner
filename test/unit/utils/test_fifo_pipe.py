from ansible_runner.utils import open_fifo_write
from os import remove


def test_fifo_write_bytes(tmp_path):
    path = tmp_path / "bytes_test"
    data = "bytes"
    try:
        open_fifo_write(path, data.encode())
        with open(path, 'r') as f:
            results = f.read()
        assert results == data
    finally:
        remove(path)


def test_fifo_write_string(tmp_path):
    path = tmp_path / "string_test"
    data = "string"
    try:
        open_fifo_write(path, data)
        with open(path, 'r') as f:
            results = f.read()
        assert results == data
    finally:
        remove(path)
