"""SIMULATION: protocol3 acquisition over real authenticated RFC6455 loopback.

Only framing/socket infrastructure is reused; this peer owns protocol3 state.
Virtual acquisition time is explicit and is not ESP32 timing/hardware proof.
"""
from __future__ import annotations
import copy
import csv
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP = ROOT / 'apps/gld-operator'
OLD = ROOT / 'tmp/wireless-stage2/e2e/wire_peer.py'
import importlib.util
spec = importlib.util.spec_from_file_location('workflow_rfc6455_infrastructure', OLD)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)

PASSWORD = legacy.PASSWORD  # Dummy simulation credential; never a real config.
PROTOCOL = 'gld-dataset-wifi/3'
FEATURE_ORDER = list(legacy.reference.replay.FEATURE_ORDER)
PROTECTED_PORTS = legacy.PROTECTED_PORTS
Server = legacy.Server


class Device:
    def __init__(self, clock, engine):
        self.clock, self.engine = clock, engine
        self.boot, self.device_id, self.profile = 'b' * 32, '1002', 1
        self.sid = self.label = self.start_id = self.stop_id = ''
        self.records, self.originals, self.commands = {}, [], []
        self.total = self.acked = self.transition_seq = self.epoch = 0
        self.sampling = self.paused = self.incomplete = self.prediction_enabled = False
        self.ready = self.prediction_ready = True
        self.reason = 'ready'
        self.outage_at = self.ack_since = None
        self.last_transition = None
        self.next_due = 0
        self.prediction_frame = self.max_window_seen = 0
        self.peer = None
        self.model = dict(profile_id='SIMULATION-model1-v3', scaler_profile_id='SIMULATION-scaler-v3',
            runtime_version='SIMULATION-only', production_approved=True, output_elements=2, class_map=[0, 3])

    def terminal(self, reason, incomplete=True):
        if not self.incomplete:
            self.reason = reason
        self.incomplete = self.incomplete or incomplete
        self.sampling = self.paused = False
        self.epoch += 1

    def enforce_retention(self):
        if (self.sampling or self.paused and self.records) and self.ack_since is not None and self.clock() - self.ack_since >= 300:
            self.terminal('retention_limit')
        if self.sampling and len(self.records) >= 640:
            self.terminal('buffer_full')

    def fields(self):
        return dict(device_id=self.device_id, boot_id=self.boot, session_id=self.sid, label=self.label,
            nulling_profile_id=self.profile, sampling=self.sampling, paused=self.paused,
            transition_seq=self.transition_seq, prediction_enabled=self.prediction_enabled,
            incomplete=self.incomplete, reason=self.reason, total_samples=self.total,
            oldest_seq=min(self.records) if self.records else self.total,
            acked_next_seq=self.acked, buffered_samples=len(self.records), overrun_count=0)

    def hello(self):
        self.enforce_retention()
        return dict(type='hello', protocol=PROTOCOL, feature_order=FEATURE_ORDER, interval_ms=500,
            retention_ms=300000, capacity=640, ready=self.ready, prediction_ready=self.prediction_ready,
            capabilities=dict(pause=True, **{'continue': True}, durable_replay=True, prediction=True,
                              requires_protocol3_client=True), model=copy.deepcopy(self.model), **self.fields())

    def ack(self, command, peer, ok=True, detail='ok'):
        peer.messages.append(dict(type='ack', cmd=command['cmd'], command_id=command['command_id'],
            session_id=command['session_id'], boot_id=self.boot, transition_seq=self.transition_seq,
            paused=self.paused, result='ok' if ok else 'error', detail=detail))

    def status(self, peer):
        peer.messages.append(dict(type='status', state='running' if self.sampling else 'paused' if self.paused else 'error' if self.incomplete else 'stopped', **self.fields()))

    def summary(self, peer):
        if self.sid and not self.sampling and not self.paused and not self.records and self.acked == self.total and not peer.summary_sent:
            peer.messages.append(dict(type='summary', boot_id=self.boot, session_id=self.sid,
                total_samples=self.total, reason=self.reason, incomplete=self.incomplete, overrun_count=0))
            peer.summary_sent = True

    def offer(self, peer):
        if peer.closed or not peer.offer_enabled:
            return
        while peer.offered_next < self.total and peer.offered_next - self.acked < 8:
            peer.messages.append(copy.deepcopy(self.records[peer.offered_next]))
            peer.offered_next += 1
            self.max_window_seen = max(self.max_window_seen, peer.offered_next - self.acked)
        self.summary(peer)

    def confirm(self, next_seq):
        advanced = next_seq > self.acked
        for seq in list(self.records):
            if seq < next_seq:
                del self.records[seq]
        self.acked = max(self.acked, next_seq)
        if advanced:
            self.ack_since = self.clock() if self.records else None
            self.outage_at = self.clock() if self.records else None

    def summary_was_sent(self):
        session = self.engine.sessions.get(self.sid, {})
        return not self.sid or any(message.get('type') == 'summary' for message in session.get('emitted_messages', []))

    def command(self, command, peer):
        self.enforce_retention()
        self.commands.append(copy.deepcopy(command))
        kind = command['cmd']
        if kind == 'START_DATASET':
            prediction = command.get('prediction_enabled', False)
            if self.sid == command['session_id'] and self.start_id == command['command_id']:
                identical = self.label == command['label'] and command.get('sample_interval_ms') == 500 and prediction == self.prediction_enabled
                self.ack(command, peer, identical, 'already_registered' if identical else 'idempotency_mismatch')
                self.status(peer)
                return
            if self.sampling or self.paused or self.records or not self.summary_was_sent() or self.sid == command['session_id']:
                self.ack(command, peer, False, 'session_or_retained_data_pending')
                return
            if not self.ready or command.get('sample_interval_ms') != 500 or prediction and not self.prediction_ready:
                self.ack(command, peer, False, 'not_ready')
                return
            self.sid, self.label, self.start_id = command['session_id'], command['label'], command['command_id']
            self.stop_id, self.reason = '', 'started'
            self.sampling, self.paused, self.incomplete = True, False, False
            self.prediction_enabled = prediction
            self.records, self.originals = {}, []
            self.total = self.acked = self.transition_seq = self.prediction_frame = 0
            self.last_transition = self.ack_since = self.outage_at = None
            self.next_due = self.clock() + .5
            self.epoch += 1
            peer.offered_next, peer.summary_sent, peer.offer_enabled = 0, False, True
            self.ack(command, peer, detail='started')
            self.status(peer)
        elif kind == 'RESUME_DATASET':
            valid = (command.get('boot_id') == self.boot and command['session_id'] == self.sid and
                command.get('label') == self.label and self.acked <= command.get('next_seq', -1) <= self.total and
                (not self.records or command['next_seq'] >= min(self.records)))
            if valid:
                self.confirm(command['next_seq'])
                peer.offered_next, peer.offer_enabled = command['next_seq'], True
                peer.summary_sent = False
            self.ack(command, peer, valid, 'resumed' if valid else 'resume_identity_or_prefix_mismatch')
            if valid:
                self.status(peer)
                self.offer(peer)
        elif kind in ('PAUSE_DATASET', 'CONTINUE_DATASET'):
            identity = command.get('boot_id') == self.boot and command['session_id'] == self.sid and command.get('label') == self.label and command.get('nulling_profile_id') == self.profile
            key = (command.get('transition_seq'), command.get('command_id'), kind)
            pause = kind == 'PAUSE_DATASET'
            if not identity:
                self.ack(command, peer, False, 'transition_identity_mismatch')
            elif key == self.last_transition:
                self.ack(command, peer, detail='already_registered')
                self.status(peer)
            elif command.get('transition_seq') != self.transition_seq + 1:
                self.ack(command, peer, False, 'transition_sequence_mismatch')
            elif self.incomplete or not (self.sampling or self.paused) or self.stop_id:
                self.ack(command, peer, False, 'session_terminal')
            elif pause and not self.sampling or not pause and not self.paused:
                self.ack(command, peer, False, 'transition_state_mismatch')
            else:
                self.epoch += 1
                self.transition_seq, self.last_transition = command['transition_seq'], key
                self.paused, self.sampling = pause, not pause
                self.reason = 'operator_pause' if pause else 'operator_continue'
                if not pause:
                    self.next_due, self.prediction_frame = self.clock() + .5, 0
                self.ack(command, peer, detail='paused' if pause else 'continued')
                self.status(peer)
        elif kind == 'ACK_SAMPLES':
            assert command.get('boot_id') == self.boot and command['session_id'] == self.sid
            assert command['next_seq'] <= self.total and command['next_seq'] <= peer.offered_next
            self.confirm(command['next_seq'])
            self.offer(peer)
        elif kind == 'STOP_DATASET':
            if command['session_id'] != self.sid or self.stop_id and self.stop_id != command['command_id']:
                self.ack(command, peer, False, 'stop_identity_mismatch')
                return
            self.stop_id = command['command_id']
            if self.sampling or self.paused:
                self.terminal('operator_stop', False)
            self.ack(command, peer, detail='stopped')
            self.status(peer)
            self.offer(peer)
        else:
            self.ack(command, peer, False, 'unknown_command')

    def capture(self):
        self.enforce_retention()
        if not self.sampling or self.clock() < self.next_due:
            return
        if len(self.records) >= 640:
            self.terminal('buffer_full')
            return
        phase = self.prediction_frame
        status = 'disabled' if not self.prediction_enabled else 'warmup' if phase < 2 else 'error' if phase == 3 else 'not_ready' if phase == 5 else 'valid'
        valid = status == 'valid'
        prediction = dict(enabled=self.prediction_enabled, status=status, valid=valid,
            predicted_class=phase % 2 if valid else None, gas_class=self.model['class_map'][phase % 2] if valid else None,
            confidence=.875 if valid else None, inference_duration_ms=7 if self.prediction_enabled else 0)
        record = dict(type='sample', device_id=self.device_id, session_id=self.sid, seq=self.total,
            timestamp_ms=round(self.clock()*1000), scan_end_ms=round(self.clock()*1000)+230,
            mode='DATASET', label=self.label, nulling_profile_id=self.profile, overrun_count=0,
            feature_order=FEATURE_ORDER, sensor_voltage=[round(.2 + index*.03 + self.total*.001, 6) for index in range(8)],
            sensor_gain=[1,2,4,8,16,32,64,1], sensor_status=[0]*8, prediction=prediction)
        self.records[self.total] = record
        self.originals.append(copy.deepcopy(record))
        self.total += 1
        self.prediction_frame += 1
        self.next_due = self.clock() + .5
        if self.ack_since is None:
            self.ack_since = self.clock()
        if len(self.records) == 640:
            self.terminal('buffer_full')
        if self.peer and not self.peer.closed:
            self.offer(self.peer)


class Engine(legacy.Engine):
    def __init__(self):
        super().__init__()
        self.auto_capture = False
        self.device = Device(self.clock, self)
        self.durability_provider = None
        self.durability_audit = []
        self.factory_calls = 0

    def factory(self, url, **options):
        self.factory_calls += 1
        return super().factory(url, **options)

    def snapshot(self):
        result = super().snapshot()
        result.update(schema='gld-workflow-e2e/3', factory_calls=self.factory_calls,
                      durability_audit=copy.deepcopy(self.durability_audit))
        return result

    def command(self, command, peer):
        if command.get('cmd') == 'ACK_SAMPLES' and self.durability_provider:
            durable = self.durability_provider(command['session_id'])
            if not all(seq in durable for seq in range(command['next_seq'])):
                self.errors.append('ACK_exceeds_actual_fsynced_canonical_and_public_prefix')
                raise AssertionError('ACK precedes durable prefix')
            self.durability_audit.append(dict(session_id=command['session_id'], next_seq=command['next_seq'], host_monotonic_s=time.monotonic()))
        return super().command(command, peer)

    def control(self, action, payload=None):
        payload = payload or {}
        if action == 'manual':
            self.auto_capture = False
            return self.snapshot()
        if action == 'advance':
            with self.lock:
                seconds = float(payload.get('seconds', 0))
                if not 0 <= seconds <= 310:
                    raise ValueError('Invalid virtual interval')
                self.clock.advance(seconds)
                self.device.enforce_retention()
            return self.snapshot()
        if action == 'acquire':
            self.auto_capture = False
        return super().control(action, payload)


class FakeWindowsPlatform:
    """Inert injected platform: never calls Windows/network/dialog APIs."""
    def __init__(self, output):
        self.output = Path(output)
        self.joins = []
        self.picked = 0
    def scan(self):
        return [dict(ssid='GLD-DATASET-1002', device_id='1002', name='GLD-1002')]
    def join(self, ssid, password=''):
        assert ssid == 'GLD-DATASET-1002' and password == PASSWORD
        self.joins.append(dict(ssid=ssid, simulation=True))
        return dict(ssid=ssid, connected=True, simulation=True)
    def choose_file(self):
        self.picked += 1
        self.output.mkdir(parents=True, exist_ok=True)
        return str(self.output / f'simulation-recording-{self.picked}.csv')
    def validate_file(self, path):
        result = Path(path).resolve()
        assert result.parent == self.output.resolve() and not result.exists()
        return result
