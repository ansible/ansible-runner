#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
import sys
import logging

DEBUG_ENABLED = False
TRACEBACK_ENABLED = True

_display_logger = logging.getLogger('ansible-runner.display')
_debug_logger = logging.getLogger('ansible-runner.debug')


def display(msg, log_only=False):
    if not log_only:
        _display_logger.log(70, msg)
    _debug_logger.log(10, msg)


def debug(msg):
    if DEBUG_ENABLED:
        if isinstance(msg, Exception):
            if TRACEBACK_ENABLED:
                _debug_logger.exception(msg)
        display(msg)


def set_logfile(filename):
    handlers = [h.get_name() for h in _debug_logger.handlers]
    if 'logfile' not in handlers:
        logfile_handler = logging.FileHandler(filename)
        logfile_handler.set_name('logfile')
        formatter = logging.Formatter('%(asctime)s: %(message)s')
        logfile_handler.setFormatter(formatter)
        _debug_logger.addHandler(logfile_handler)


def set_debug(value):
    global DEBUG_ENABLED
    if value.lower() not in ('enable', 'disable'):
        raise ValueError('value must be one of `enable` or `disable`, got %s' % value)
    DEBUG_ENABLED = value.lower() == 'enable'


def set_traceback(value):
    global TRACEBACK_ENABLED
    if value.lower() not in ('enable', 'disable'):
        raise ValueError('value must be one of `enable` or `disable`, got %s' % value)
    TRACEBACK_ENABLED = value.lower() == 'enable'


def configure():
    '''
    Configures the logging facility

    This function will setup an initial logging facility for handling display
    and debug outputs.  The default facility will send display messages to
    stdout and the default debug facility will do nothing.

    :returns: None
    '''
    root_logger = logging.getLogger()
    root_logger.addHandler(logging.NullHandler())
    root_logger.setLevel(99)

    _display_logger.setLevel(70)
    _debug_logger.setLevel(10)

    display_handlers = [h.get_name() for h in _display_logger.handlers]

    if 'stdout' not in display_handlers:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.set_name('stdout')
        formatter = logging.Formatter('%(message)s')
        stdout_handler.setFormatter(formatter)
        _display_logger.addHandler(stdout_handler)
