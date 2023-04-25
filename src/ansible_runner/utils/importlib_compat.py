import sys

if sys.version_info < (3, 10):
    import importlib_metadata  # noqa: F401
else:
    import importlib.metadata as importlib_metadata  # noqa: F401
