from StringIO import StringIO
import base64
import json
import sys
import re


class OutputEventFilter(object):
    '''
    File-like object that looks for encoded job events in stdout data.
    '''

    EVENT_DATA_RE = re.compile(r'\x1b\[K((?:[A-Za-z0-9+/=]+\x1b\[\d+D)+)\x1b\[K')

    def __init__(self, handle, event_callback):
        self._event_callback = event_callback
        self._event_ct = 0
        self._counter = 1
        self._start_line = 0
        self._handle = handle
        self._buffer = StringIO()
        self._last_chunk = ''
        self._current_event_data = None

    def flush(self):
        # pexpect wants to flush the file it writes to, but we're not
        # actually capturing stdout to a raw file; we're just
        # implementing a custom `write` method to discover and emit events from
        # the stdout stream
        pass

    def write(self, data):
        self._buffer.write(data)

        # keep a sliding window of the last chunk written so we can detect
        # event tokens and determine if we need to perform a search of the full
        # buffer
        should_search = '\x1b[K' in (self._last_chunk + data)
        self._last_chunk = data

        # Only bother searching the buffer if we recently saw a start/end
        # token (\x1b[K)
        while should_search:
            value = self._buffer.getvalue()
            match = self.EVENT_DATA_RE.search(value)
            if not match:
                break
            try:
                base64_data = re.sub(r'\x1b\[\d+D', '', match.group(1))
                event_data = json.loads(base64.b64decode(base64_data))
            except ValueError:
                event_data = {}
            self._emit_event(value[:match.start()], event_data)
            remainder = value[match.end():]
            self._buffer = StringIO()
            self._buffer.write(remainder)

            sys.stdout.write(remainder)
            self._handle.write(remainder)

            self._last_chunk = remainder

    def close(self):
        value = self._buffer.getvalue()
        if value:
            self._emit_event(value)
            self._buffer = StringIO()
        self._event_callback(dict(event='EOF'))

    def _emit_event(self, buffered_stdout, next_event_data=None):
        next_event_data = next_event_data or {}
        if self._current_event_data:
            event_data = self._current_event_data
            stdout_chunks = [buffered_stdout]
        elif buffered_stdout:
            event_data = dict(event='verbose')
            stdout_chunks = buffered_stdout.splitlines(True)
        else:
            stdout_chunks = []

        for stdout_chunk in stdout_chunks:
            event_data['counter'] = self._counter
            self._counter += 1
            event_data['stdout'] = stdout_chunk[:-2] if len(stdout_chunk) > 2 else ""
            n_lines = stdout_chunk.count('\n')
            event_data['start_line'] = self._start_line
            event_data['end_line'] = self._start_line + n_lines
            self._start_line += n_lines
            if self._event_callback:
                self._event_callback(event_data)
                self._event_ct += 1

        if next_event_data.get('uuid', None):
            self._current_event_data = next_event_data
        else:
            self._current_event_data = None
