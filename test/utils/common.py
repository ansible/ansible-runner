import time
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)


def iterate_timeout(max_seconds, purpose, interval=2):
    start = time.time()
    count = 0
    while time.time() < start + max_seconds:
        count += 1
        yield count
        time.sleep(interval)
    raise Exception("Timeout waiting for %s" % purpose)


class RSAKey:
    """In-memory RSA key generation and management utils."""

    def __init__(self):
        _rsa_key_obj = generate_private_key(
            public_exponent=65537,
            key_size=1024,
            backend=default_backend(),
        )

        _private_rsa_key_repr = _rsa_key_obj.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,  # A.K.A. PKCS#1
            encryption_algorithm=NoEncryption(),
        )
        self._private_rsa_key_repr = _private_rsa_key_repr.decode()

    @property
    def private(self) -> str:
        return self._private_rsa_key_repr
