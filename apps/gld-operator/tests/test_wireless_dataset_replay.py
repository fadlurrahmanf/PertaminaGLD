"""Deterministic protocol-2 faults; temp files/fake peers, no services/devices."""
import csv
import json
import sys
import tempfile
import time
import unittest
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wireless_dataset_replay as replay


class Clock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class FakePeer:
    def __init__(self, device):
        self.device = device
        self.messages = deque([device.hello()])
        self.closed = False
        self.offered_next = device.acked
        self.summary_sent = False
        self.offer_enabled = False
    def settimeout(self, _timeout):
        pass
    def recv(self):
        if self.closed:
            return ""
        if self.messages:
            return json.dumps(self.messages.popleft())
        self.device.clock.advance(0.25)
        raise TimeoutError()
    def send(self, payload):
        if self.closed:
            raise ConnectionError()
        self.device.command(json.loads(payload), self)
    def close(self):
        self.closed = True
        self.messages.clear()
        if self.device.sampling and self.device.outage_at is None:
            self.device.outage_at = self.device.clock()


class FakeRingDevice:
    """Independent acquisition ring + offered-prefix window, not a collector mock."""
    def __init__(self, clock):
        self.clock = clock
        self.boot = "a" * 32
        self.device_id, self.profile = "1002", 1
        self.sid = self.label = ""
        self.records = {}
        self.originals = []
        self.total = self.acked = 0
        self.sampling = self.incomplete = False
        self.ready = True
        self.reason = "stopped"
        self.outage_at = None
        self.peer = None
        self.commands = []
        self.factory_calls = []
        self.unavailable = False
        self.start_fault = self.stop_fault = None
        self.ignore_acks = False
        self.max_window_seen = 0
        self.stop_ids = []
        self.sync_events = []
    def terminal(self, reason):
        self.sampling = False
        self.incomplete, self.reason = True, reason
    def enforce_retention(self):
        if self.sampling and self.outage_at is not None and self.clock() - self.outage_at >= 300:
            self.terminal("retention_limit")
    def hello(self):
        self.enforce_retention()
        return dict(type="hello", protocol=replay.PROTOCOL, device_id=self.device_id,
            boot_id=self.boot, feature_order=replay.FEATURE_ORDER, interval_ms=500,
            ready=self.ready, nulling_profile_id=self.profile, retention_ms=300000,
            capacity=640, session_id=self.sid, label=self.label, total_samples=self.total,
            oldest_seq=min(self.records) if self.records else self.total,
            acked_next_seq=self.acked, sampling=self.sampling, incomplete=self.incomplete, reason=self.reason)
    def factory(self, url, **options):
        assert url == replay.ENDPOINT
        assert options["http_no_proxy"] == ["*"] and options["redirect_limit"] == 0
        self.factory_calls.append(self.clock())
        if self.unavailable:
            raise ConnectionError("fake peer unavailable")
        self.peer = FakePeer(self)
        return self.peer
    def ack(self, command, peer, result="ok"):
        peer.messages.append(dict(type="ack", cmd=command["cmd"], command_id=command["command_id"],
                                  session_id=command["session_id"], result=result))
    def status(self, peer):
        peer.messages.append(dict(type="status", session_id=self.sid, device_id=self.device_id,
            boot_id=self.boot, label=self.label, nulling_profile_id=self.profile,
            state="running" if self.sampling else "error" if self.incomplete else "stopped",
            sampling=self.sampling, incomplete=self.incomplete, reason=self.reason,
            total_samples=self.total, oldest_seq=min(self.records) if self.records else self.total,
            acked_next_seq=self.acked, buffered_samples=len(self.records)))
    def summary(self, peer):
        if not self.sampling and not self.records and not peer.summary_sent:
            peer.messages.append(dict(type="summary", session_id=self.sid, total_samples=self.total,
                incomplete=self.incomplete, reason=self.reason, overrun_count=0))
            peer.summary_sent = True
    def offer(self, peer):
        if peer.closed or not peer.offer_enabled:
            return
        while peer.offered_next < self.total and peer.offered_next - self.acked < 8:
            peer.messages.append(dict(self.records[peer.offered_next]))
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
            self.outage_at = self.clock() if self.records else None
    def command(self, command, peer):
        self.enforce_retention()
        self.commands.append(dict(command))
        kind = command["cmd"]
        if kind == "START_DATASET":
            if self.start_fault == "not_delivered":
                peer.close()
                raise ConnectionError()
            assert not self.sampling and not self.records
            self.sid, self.label = command["session_id"], command["label"]
            self.sampling, self.incomplete = True, False
            self.total = self.acked = 0
            self.reason = "stopped"
            self.originals.clear()
            if self.start_fault == "ack_lost":
                self.start_fault = None
                peer.close()
                return
            self.ack(command, peer)
            self.status(peer)
            peer.offer_enabled = True
        elif kind == "RESUME_DATASET":
            valid = (command["session_id"] == self.sid and command["boot_id"] == self.boot and
                     command["label"] == self.label and self.acked <= command["next_seq"] <= self.total and
                     (not self.records or command["next_seq"] >= min(self.records)))
            self.ack(command, peer, "ok" if valid else "error")
            if valid:
                self.confirm(command["next_seq"])
                peer.offered_next = command["next_seq"]
                self.status(peer)
                if not self.records:
                    self.outage_at = None
                peer.offer_enabled = True
                self.offer(peer)
        elif kind == "ACK_SAMPLES":
            assert command["session_id"] == self.sid and command["boot_id"] == self.boot
            assert command["next_seq"] <= peer.offered_next
            self.sync_events.append(("ack", command["next_seq"]))
            if not self.ignore_acks:
                self.confirm(command["next_seq"])
                self.offer(peer)
        elif kind == "STOP_DATASET":
            self.stop_ids.append(command["command_id"])
            assert command["session_id"] == self.sid
            self.sampling = False
            if self.stop_fault == "ack_lost":
                self.stop_fault = None
                peer.close()
                return
            self.ack(command, peer)
            self.status(peer)
            self.offer(peer)
        else:
            raise AssertionError(kind)
    def capture(self):
        if not self.sampling:
            return
        if len(self.records) >= 640:
            self.terminal("buffer_full")
            return
        seq = self.total
        if self.outage_at is None:
            self.outage_at = self.clock()  # Arm at first pending durable ACK.
        record = dict(type="sample", device_id=self.device_id, session_id=self.sid,
            seq=seq, timestamp_ms=(seq + 1) * 500, scan_end_ms=(seq + 1) * 500 + 230,
            mode="DATASET", label=self.label, nulling_profile_id=self.profile,
            sensor_voltage=[round(1 + seq * .001 + channel * .03, 7) for channel in range(8)],
            sensor_gain=[1] * 8, sensor_status=[0] * 8,
            feature_order=replay.FEATURE_ORDER, overrun_count=0)
        self.records[seq] = record
        self.originals.append(record)
        self.total += 1
        if self.peer:
            self.offer(self.peer)
    def acquire(self, count):
        for _ in range(count):
            self.clock.advance(.5)
            self.enforce_retention()
            self.capture()


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.device = FakeRingDevice(self.clock)
        self.collector = replay.WirelessDatasetReplayCollector(
            self.directory.name, websocket_factory=self.device.factory,
            clock=self.clock, fsync=self.sync, command_timeout=2,
            silence_timeout=3, autostart_worker=False)
    def sync(self, _fd):
        self.device.sync_events.append(("fsync", None))
    def tearDown(self):
        self.collector.disconnect()
        self.directory.cleanup()
    def begin(self):
        self.collector.connect("private-fake-password")
        result = self.collector.start("host_fixture")
        self.assertEqual(result["state"], "recording")
    def pump(self, limit=10000):
        for _ in range(limit):
            peer = self.device.peer
            if not peer or not peer.messages or peer.closed or not self.collector._want_link:
                break
            self.collector._step()
    def recover(self):
        self.clock.advance(8)
        self.collector._step()
        self.pump()
    def lose(self):
        self.device.peer.close()
        self.collector._step()
        self.assertTrue(self.collector.snapshot()["recovery_active"])
    def parsed(self):
        with open(self.collector.path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    def assert_original_rows(self):
        rows = self.parsed()
        self.assertEqual(len(rows), self.collector.count)
        for raw, original in zip(rows, self.device.originals):
            for key in replay.CSV_HEADERS[:9]:
                self.assertEqual(raw[key], str(original[key]))
            for index, name in enumerate(replay.FEATURE_ORDER):
                self.assertEqual(float(raw[f"voltage_{name}"]), original["sensor_voltage"][index])
                self.assertEqual(int(raw[f"gain_{name}"]), original["sensor_gain"][index])
                self.assertEqual(int(raw[f"status_{name}"]), original["sensor_status"][index])
            self.assertEqual(raw["feature_order"], "|".join(replay.FEATURE_ORDER))

    def test_normal_start_stop_durable_ack_order_and_all_csv_fields(self):
        self.begin()
        for _ in range(6):
            self.device.acquire(1)
            self.pump()
        result = self.collector.stop()
        self.assertTrue(result["complete"])
        self.assertEqual(result["count"], 6)
        self.assertIsNone(self.collector._password)
        self.assertFalse(result["connected"])
        for index, event in enumerate(self.device.sync_events):
            if event[0] == "ack":
                self.assertEqual(self.device.sync_events[index - 1][0], "fsync")
        self.assert_original_rows()

    def test_one_and_repeated_disconnect_keep_same_file_session_and_times(self):
        self.begin()
        path, sid = self.collector.path, self.collector.session_id
        for _ in range(3):
            self.device.acquire(2)
            self.pump()
            self.lose()
            self.device.acquire(4)
            self.recover()
        self.assertTrue(self.collector.stop()["complete"])
        self.assertEqual((self.collector.path, self.collector.session_id), (path, sid))
        self.assert_original_rows()

    def test_over_600_retained_records_replay_with_window_eight(self):
        self.begin()
        self.device.acquire(5)
        self.collector._step()  # Persist/ACK one prefix immediately before loss.
        self.assertEqual(self.collector.count, 1)
        self.assertEqual(self.device.outage_at, self.clock())
        self.lose()
        self.device.acquire(599)  # 299.5 s after genuine ACK progress: 603 retained.
        self.assertEqual(len(self.device.records), 603)
        self.device.unavailable = False
        self.collector._step()  # Time already exceeds the next retry deadline.
        self.pump()
        self.assertEqual(self.collector.count, 604)
        self.assertLessEqual(self.device.max_window_seen, 8)
        self.assertTrue(self.collector.stop()["complete"])
        self.assert_original_rows()

    def test_exact_300s_and_301s_terminal_records_drained_without_overwrite(self):
        for seconds in (300, 301):
            with self.subTest(seconds=seconds):
                self.tearDown()
                self.setUp()
                self.begin()
                self.lose()
                self.device.acquire(599)
                self.clock.advance(seconds - 299.5)
                originals = list(self.device.originals)
                self.collector._step()
                self.pump()
                result = self.collector.snapshot()
                self.assertEqual(result["state"], "incomplete")
                self.assertEqual(result["terminal_reason"], "retention_limit")
                self.assertFalse(result["complete"])
                self.assertEqual(result["count"], 599)
                self.assertEqual(self.device.originals, originals)
                self.assert_original_rows()

    def test_buffer_full_terminal_drains_640_and_never_replaces_first_record(self):
        self.begin()
        self.lose()
        # Capacity fault independently of acquisition cadence/retention timer.
        for _ in range(641):
            self.device.capture()
        self.assertEqual((len(self.device.records), self.device.total), (640, 640))
        self.assertEqual(min(self.device.records), 0)
        self.recover()
        result = self.collector.snapshot()
        self.assertEqual(result["terminal_reason"], "buffer_full")
        self.assertEqual(result["count"], 640)
        self.assertFalse(result["complete"])
        self.assert_original_rows()

    def test_ack_loss_duplicate_and_resume_prefix_do_not_duplicate_csv(self):
        self.begin()
        self.device.ignore_acks = True
        for _ in range(8):
            self.device.acquire(1)
            self.pump()
        self.device.peer.messages.append(dict(self.device.originals[-1]))
        self.pump()
        self.assertEqual((self.collector.count, self.collector.duplicate_count), (8, 1))
        self.lose()
        self.device.ignore_acks = False
        self.recover()
        resumes = [wire for wire in self.device.commands if wire["cmd"] == "RESUME_DATASET"]
        self.assertEqual(resumes[-1]["next_seq"], 8)
        self.assertTrue(self.collector.stop()["complete"])
        self.assert_original_rows()

    def test_disconnect_during_replay_resumes_only_persisted_prefix(self):
        self.begin()
        self.lose()
        self.device.acquire(30)
        self.clock.advance(1)
        self.collector._step()
        for _ in range(7):  # Resume ACK/status + five durable records.
            self.collector._step()
        prefix = self.collector.next_seq
        self.assertGreater(prefix, 0)
        self.assertLess(prefix, 30)
        self.lose()
        self.recover()
        self.assertEqual(self.collector.count, 30)
        self.assertTrue(self.collector.stop()["complete"])
        self.assert_original_rows()

    def test_ambiguous_start_reconciles_by_resume_never_resends_start(self):
        self.device.start_fault = "ack_lost"
        self.collector.connect("private-fake-password")
        self.assertEqual(self.collector.start("host_fixture")["state"], "recovering")
        self.recover()
        self.assertEqual(self.collector.state, "recording")
        self.assertEqual(sum(wire["cmd"] == "START_DATASET" for wire in self.device.commands), 1)
        self.assertEqual(sum(wire["cmd"] == "RESUME_DATASET" for wire in self.device.commands), 1)

    def test_start_not_delivered_fails_exact_session_without_fresh_start(self):
        self.device.start_fault = "not_delivered"
        self.collector.connect("private-fake-password")
        self.collector.start("host_fixture")
        self.recover()
        self.assertEqual(self.collector.state, "incomplete")
        self.assertEqual(sum(wire["cmd"] == "START_DATASET" for wire in self.device.commands), 1)

    def test_stop_offline_intent_is_pending_then_idempotent_after_recovery(self):
        self.begin()
        self.lose()
        result = self.collector.stop()
        self.assertEqual(result["state"], "stop_pending")
        self.assertFalse(result["stop_delivered"])
        self.device.acquire(5)
        self.recover()
        self.assertTrue(self.collector.complete)
        self.assertEqual(self.collector.count, 5)

    def test_lost_stop_ack_summary_before_duplicate_stop_ack(self):
        self.begin()
        self.device.acquire(2)
        self.pump()
        self.device.stop_fault = "ack_lost"
        self.assertFalse(self.collector.stop()["complete"])
        self.recover()
        self.assertTrue(self.collector.complete)
        self.assertEqual(len(self.device.stop_ids), 2)
        self.assertEqual(self.device.stop_ids[0], self.device.stop_ids[1])

    def test_wrong_boot_session_label_profile_or_prefix_never_appends(self):
        for mutation in ("boot", "sid", "label", "profile", "prefix"):
            with self.subTest(mutation=mutation):
                self.tearDown()
                self.setUp()
                self.begin()
                self.lose()
                if mutation == "boot": self.device.boot = "b" * 32
                elif mutation == "sid": self.device.sid = "other"
                elif mutation == "label": self.device.label = "other"
                elif mutation == "profile": self.device.profile = 2
                else: self.device.acked = self.device.total = 1
                self.recover()
                self.assertEqual(self.collector.state, "incomplete")
                self.assertEqual(self.collector.count, 0)
                self.assertIsNone(self.collector._password)

    def test_disk_failure_before_ack_marks_incomplete_without_confirmation(self):
        self.begin()
        def fail(_fd):
            raise OSError("private disk exception text")
        self.collector._fsync = fail
        self.device.acquire(1)
        self.pump()
        self.assertEqual(self.collector.terminal_reason, "disk_failure_before_ack")
        self.assertEqual(self.collector.count, 0)
        self.assertFalse(any(wire["cmd"] == "ACK_SAMPLES" for wire in self.device.commands))
        self.assertNotIn("private disk", json.dumps(self.collector.snapshot()))

    def test_gap_bad_array_changed_profile_and_optional_boot_are_fatal(self):
        for patch in (dict(seq=1), dict(sensor_voltage=[float("nan")] * 8),
                      dict(sensor_status=[1] * 8), dict(nulling_profile_id=2), dict(boot_id="b" * 32)):
            with self.subTest(patch=list(patch)):
                self.tearDown()
                self.setUp()
                self.begin()
                self.device.acquire(1)
                self.device.peer.messages[0].update(patch)
                self.pump()
                self.assertEqual(self.collector.state, "incomplete")
                self.assertEqual(self.collector.count, 0)

    def test_silence_backoff_indefinite_retry_and_explicit_cancel(self):
        self.begin()
        self.clock.advance(3)
        self.collector._step()
        self.assertEqual(self.collector.state, "recovering")
        self.device.unavailable = True
        delays = []
        for _ in range(85):
            delay = self.collector._next_retry_at - self.clock()
            delays.append(delay)
            self.clock.advance(delay)
            self.collector._step()
        self.assertEqual(delays[:4], [1, 2, 4, 8])
        self.assertTrue(all(delay == 8 for delay in delays[3:]))
        self.assertTrue(self.collector.snapshot()["recovery_active"])
        calls = len(self.device.factory_calls)
        self.collector.disconnect()
        self.clock.advance(10000)
        self.collector._step()
        self.assertEqual(len(self.device.factory_calls), calls)
        self.assertIsNone(self.collector._password)
        self.assertEqual(self.collector.state, "incomplete")

    def test_terminal_ready_false_drains_and_stop_cannot_clear_retention_reason(self):
        self.begin()
        self.lose()
        self.device.acquire(4)
        self.device.terminal("retention_limit")
        self.device.ready = False
        self.collector.stop()
        self.recover()
        self.assertEqual(self.collector.count, 4)
        self.assertFalse(self.collector.complete)
        self.assertEqual(self.collector.terminal_reason, "retention_limit")

    def test_clean_unsolicited_summary_cannot_certify_completion(self):
        self.begin()
        self.device.peer.messages.append(dict(type="summary", session_id=self.device.sid,
            total_samples=0, incomplete=False, reason="stopped", overrun_count=0))
        self.pump()
        self.assertFalse(self.collector.complete)
        self.assertEqual(self.collector.terminal_reason, "clean_summary_without_requested_stop")

    def test_no_credentials_in_events_snapshot_or_exception_text(self):
        events = []
        self.collector._callback = events.append
        self.begin()
        exported = json.dumps([self.collector.snapshot(), events])
        self.assertNotIn("private-fake-password", exported)
        self.assertNotIn("Authorization", exported)
        self.assertNotIn("header", exported)

    def test_duplicate_with_changed_original_timestamp_is_not_acknowledged(self):
        self.begin()
        self.device.acquire(1)
        self.pump()
        acks = sum(wire["cmd"] == "ACK_SAMPLES" for wire in self.device.commands)
        duplicate = dict(self.device.originals[0], timestamp_ms=999)
        self.device.peer.messages.append(duplicate)
        self.pump()
        self.assertEqual(self.collector.count, 1)
        self.assertEqual(self.collector.terminal_reason, "duplicate_sample_content_changed")
        self.assertEqual(sum(wire["cmd"] == "ACK_SAMPLES" for wire in self.device.commands), acks)

    def test_ack_socket_failure_after_fsync_keeps_row_and_resumes_durable_prefix(self):
        events = []
        self.collector._callback = events.append
        self.begin()
        original = self.device.command
        failed = [False]
        def fail_once(command, peer):
            if command["cmd"] == "ACK_SAMPLES" and not failed[0]:
                failed[0] = True
                peer.close()
                raise ConnectionError()
            original(command, peer)
        self.device.command = fail_once
        self.device.acquire(1)
        self.pump()
        self.assertEqual(self.collector.count, 1)
        self.assertEqual(self.collector.state, "recovering")
        self.assertTrue(any(event["type"] == "sample" and event["count"] == 1 for event in events))
        self.recover()
        self.assertEqual([wire["next_seq"] for wire in self.device.commands if wire["cmd"] == "RESUME_DATASET"], [1])
        self.assertTrue(self.collector.stop()["complete"])
        self.assert_original_rows()

    def test_real_worker_explicit_cancel_wakes_backoff_and_joins(self):
        self.collector.disconnect()
        self.collector = replay.WirelessDatasetReplayCollector(self.directory.name,
            websocket_factory=self.device.factory, clock=self.clock, fsync=self.sync,
            command_timeout=2, silence_timeout=3)
        self.begin()
        self.device.peer.close()
        deadline = time.monotonic() + 1
        while not self.collector.snapshot()["recovery_active"] and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(self.collector.snapshot()["recovery_active"])
        started = time.monotonic()
        self.collector.disconnect()
        self.assertLess(time.monotonic() - started, .5)
        self.assertFalse(self.collector._thread.is_alive())
        self.assertTrue(self.device.sampling)  # Offline cancellation sent no Stop.
        self.assertIsNone(self.collector._password)

    def test_reconnect_auth_rejection_is_fatal_and_clears_credential(self):
        self.begin()
        self.lose()
        class AuthenticationError(Exception):
            status_code = 401
        def rejected(*_args, **_kwargs):
            raise AuthenticationError("arbitrary secret transport details")
        self.collector._factory = rejected
        self.recover()
        self.assertEqual(self.collector.terminal_reason, "authentication_rejected")
        self.assertIsNone(self.collector._password)
        self.assertNotIn("secret", json.dumps(self.collector.snapshot()))


if __name__ == "__main__":
    unittest.main()
