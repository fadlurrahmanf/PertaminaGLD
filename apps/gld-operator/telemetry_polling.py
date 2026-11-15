"""Serial request gate for optional bridge-owned telemetry polling.

A poll or operator command owns the wire until its matching response. A
missing response quarantines the gate rather than sending an unrelated command
into an unknown device state. The caller must explicitly reset after a new
serial connection. This module performs no serial I/O itself.
"""
from __future__ import annotations

import json
from collections import deque
import threading
import time

ACK_WITH_STATUS = frozenset({'SET_SESSION_MCP', 'SET_SENSOR_POWER', 'SET_ALARM_MODE',
                             'SET_MANUAL_ALARM', 'RETRY_NULLING', 'RETRY_FAILED_NULLING'})


def expected_response(command: str) -> str:
    parts = command.strip().split(maxsplit=1)
    if not parts:
        raise ValueError('empty serial command')
    name = parts[0].upper()
    known = {'GET_INFO': 'info', 'GET_STATUS': 'status',
             'GET_TELEMETRY': 'telemetry', 'GET_QC_STATUS': 'qc',
             'RUN_CURRENT_STATE_CHECK': 'current-state-done'}
    return known.get(name, 'ack:' + (name[:-5] if name.endswith('_JSON') else name))


def response_kind(line: str) -> str | None:
    text = line.strip()
    for prefix, kind in (('GLD_INFO_JSON ', 'info'), ('GLD_STATUS_JSON ', 'status'),
                         ('GLD_TELEMETRY_JSON ', 'telemetry'), ('GLD_QC_STATUS_JSON ', 'qc')):
        if text.startswith(prefix):
            try:
                payload = json.loads(text[len(prefix):])
            except (ValueError, TypeError):
                return None
            return kind if isinstance(payload, dict) else None
    if text.startswith('RUN_CURRENT_STATE_CHECK_DONE'):
        return 'current-state-done'
    prefix = 'GLD_CMD_ACK_JSON '
    if text.startswith(prefix):
        try:
            obj = json.loads(text[len(prefix):])
        except (ValueError, TypeError):
            return None
        if isinstance(obj, dict) and isinstance(obj.get('cmd'), str):
            return 'ack:' + obj['cmd'].upper()
    return None


class SerialPollGate:
    def __init__(self):
        self._condition = threading.Condition()
        self._pending = None
        self._quarantined = False
        self._next = 0
        self._epoch = 0
        self._completed = deque(maxlen=128)
        self._priority_waiters = 0

    def reset(self):
        with self._condition:
            self._epoch += 1
            self._next += 1
            self._pending = None
            self._quarantined = False
            self._completed.clear()
            self._condition.notify_all()

    def reserve(self, command: str, timeout: float = 0):
        """Reserve before writing. Return unique generation token or None."""
        expected = expected_response(command)
        deadline = time.monotonic() + max(0, timeout)
        with self._condition:
            epoch = self._epoch
            priority = timeout > 0
            if priority:
                self._priority_waiters += 1
            try:
                if not priority and self._priority_waiters:
                    return None
                while self._pending and not self._quarantined:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._condition.wait(remaining)
                    if self._epoch != epoch:
                        return None
                if self._quarantined or self._epoch != epoch:
                    return None
                self._next += 1
                token = self._next
                self._pending = (token, expected)
                return token
            finally:
                if priority:
                    self._priority_waiters -= 1

    def observe(self, line: str):
        kind = response_kind(line)
        with self._condition:
            if not self._pending:
                return False
            expected = self._pending[1]
            if expected.startswith('status-after:') and kind == 'status':
                self._completed.append(self._pending[0])
                self._pending = None
                self._condition.notify_all()
                return True
            if expected == kind:
                if kind and kind.startswith('ack:') and kind[4:] in ACK_WITH_STATUS:
                    try:
                        ack = json.loads(line.strip()[len('GLD_CMD_ACK_JSON '):])
                    except (ValueError, TypeError):
                        ack = {}
                    if ack.get('status') == 'ok':
                        token = self._pending[0]
                        marker = 'status-after:' + kind[4:]
                        self._pending = (token, marker)
                        # Older firmware may omit this unsolicited snapshot.
                        # A bounded quiet period keeps those versions usable.
                        timer = threading.Timer(2.0, self._finish_optional_status, args=(token, marker))
                        timer.daemon = True
                        timer.start()
                        return False
                self._completed.append(self._pending[0])
                self._pending = None
                self._condition.notify_all()
                return True
        return False

    def _finish_optional_status(self, token, marker):
        with self._condition:
            if self._pending == (token, marker):
                self._completed.append(token)
                self._pending = None
                self._condition.notify_all()

    def fail(self, token):
        """Unknown write or missing response: stop all future requests."""
        with self._condition:
            if self._pending and self._pending[0] == token:
                self._quarantined = True
                self._condition.notify_all()
                return True
        return False

    def cancel_unsent(self, token):
        with self._condition:
            if self._pending and self._pending[0] == token:
                self._pending = None
                self._condition.notify_all()
                return True
        return False

    def is_quarantined(self):
        with self._condition:
            return self._quarantined

    def is_idle(self):
        with self._condition:
            return self._pending is None and not self._quarantined

    def pending_response(self):
        with self._condition:
            return self._pending[1] if self._pending else None

    def epoch(self):
        with self._condition:
            return self._epoch

    def wait_response(self, token, timeout: float):
        deadline = time.monotonic() + max(0, timeout)
        with self._condition:
            while self._pending and self._pending[0] == token and not self._quarantined:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._quarantined = True
                    self._condition.notify_all()
                    return False
                self._condition.wait(remaining)
            if token in self._completed:
                self._completed.remove(token)
                return True
            return False

class BackgroundTelemetryPoller:
    """One owner per serial slot; never sends while a request owns the gate."""
    def __init__(self, gate, write_poll, on_error=lambda _message: None, response_timeout=5.0):
        self._gate = gate
        self._write_poll = write_poll
        self._on_error = on_error
        self._response_timeout = response_timeout
        self._lock = threading.Lock()
        self._owner = None
        self._stop = None
        self._thread = None

    def start(self, owner: str, interval_ms: int):
        if not isinstance(owner, str) or not 16 <= len(owner) <= 128:
            raise ValueError('invalid polling owner')
        if not isinstance(interval_ms, int) or not 200 <= interval_ms <= 60000:
            raise ValueError('invalid polling interval')
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._owner != owner:
                    raise RuntimeError('polling is owned by another session')
                if self._stop.is_set():
                    raise RuntimeError('polling is stopping')
                return False
            stop = threading.Event()
            self._owner, self._stop = owner, stop
            thread = threading.Thread(target=self._run, args=(stop, interval_ms / 1000),
                                      name='gld-telemetry-poll', daemon=True)
            self._thread = thread
            thread.start()
        return True

    def stop(self, owner: str):
        with self._lock:
            if self._owner is None:
                return False
            if self._owner != owner:
                raise RuntimeError('polling is owned by another session')
            self._stop.set()
            return True

    def join(self, timeout):
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        return thread is None or not thread.is_alive()

    def stop_for_disconnect(self):
        with self._lock:
            if self._stop is not None:
                self._stop.set()

    def _run(self, stop, interval):
        try:
            while not stop.is_set():
                started = time.monotonic()
                token = self._gate.reserve('GET_TELEMETRY')
                if token is None and self._gate.is_quarantined():
                    self._on_error('serial response unknown; polling stopped')
                    return
                if token is not None:
                    try:
                        with self._lock:
                            if stop.is_set():
                                self._gate.cancel_unsent(token)
                                return
                            self._write_poll('GET_TELEMETRY')
                    except Exception:
                        self._gate.fail(token)
                        self._on_error('poll write failed; polling stopped')
                        return
                    if not self._gate.wait_response(token, self._response_timeout):
                        if not stop.is_set():
                            self._on_error('poll response missing; polling stopped')
                        return
                if stop.wait(max(0, interval - (time.monotonic() - started))):
                    return
        finally:
            with self._lock:
                if self._stop is stop:
                    self._owner = self._stop = self._thread = None

class TelemetryReplayBuffer:
    """Bounded timestamped samples with explicit loss detection for a slot."""
    # 18,000 samples retain an hour even at the minimum 200 ms poll setting.
    # deque allocates as samples arrive; it does not preallocate this capacity.
    def __init__(self, max_items=18000):
        if max_items < 1:
            raise ValueError('max_items must be positive')
        self._items = deque(maxlen=max_items)
        self._sequence = 0
        self._lock = threading.Lock()

    def append(self, line: str, received_ms: int):
        if response_kind(line) != 'telemetry':
            raise ValueError('expected valid telemetry')
        if not isinstance(received_ms, int) or received_ms < 0:
            raise ValueError('invalid receive time')
        with self._lock:
            self._sequence += 1
            self._items.append({'sequence': self._sequence, 'receivedMs': received_ms, 'line': line})
            return self._sequence

    def after(self, cursor: int):
        if not isinstance(cursor, int) or cursor < 0:
            raise ValueError('invalid cursor')
        with self._lock:
            if cursor > self._sequence:
                raise ValueError('cursor is ahead of this stream')
            oldest = self._items[0]['sequence'] if self._items else self._sequence + 1
            return {'sequence': self._sequence, 'truncated': cursor < oldest - 1,
                    'samples': [dict(item) for item in self._items if item['sequence'] > cursor]}
