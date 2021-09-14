from tempfile import NamedTemporaryFile

import pytest


@pytest.fixture
def tmp_file_maker():
    """Fixture to return temporary file maker."""
    def tmp_file(text):
        with NamedTemporaryFile(delete=False) as tempf:
            tempf.write(bytes(text, 'UTF-8'))
        return tempf.name
    return tmp_file
