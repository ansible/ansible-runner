from __future__ import (absolute_import, division, print_function)

# Python
import os  # noqa
import sys  # noqa

callback_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if callback_lib_path not in sys.path:
    sys.path.insert(0, callback_lib_path)


from display_callback import AWXMinimalCallbackModule # noqa


# In order to be recognized correctly, self.__class__.__name__ needs to
# match "CallbackModule"
class CallbackModule(AWXMinimalCallbackModule):
    pass
