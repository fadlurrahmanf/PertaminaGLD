"""Deterministic additive direct-mode tests; no devices, sockets or services."""
import base64
import copy
import csv
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wireless_dataset_direct import WirelessDatasetDirectCollector
from wireless_dataset_replay import WirelessDatasetReplayCollector, FEATURE_ORDER
from test_wireless_dataset_replay import Clock, FakeRingDevice as ReplayFakeRingDevice
from test_wireless_dataset import Peer, eventually

PASSWORD = "private-fake-password"


class FakeRingDevice(ReplayFakeRingDevice):
    def command(self, wire, peer):
        # This fixture exercises successive sessions on one live firmware.
        # Reset the per-connection offer frontier just as real START does.
        if wire["cmd"] == "START_DATASET":
            peer.offered_next = 0
            peer.summary_sent = False
            self.outage_at = None
        return super().command(wire, peer)


class DirectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.device = FakeRingDevice(self.clock)
        self.events = []
        self.collector = WirelessDatasetDirectCollector(self.directory.name, self.events.append,
            websocket_factory=self.device.factory, clock=self.clock, fsync=self.sync,
            command_timeout=2, silence_timeout=3, autostart_worker=False)

    def sync(self, fd):
        os.fsync(fd)
        self.device.sync_events.append(("fsync", None))

    def tearDown(self):
        self.collector.disconnect()
        self.collector.disconnect()  # Pause if the first disconnect initiated cleanup.
        delegate = self.collector._delegate
        if delegate and getattr(delegate, "_sink_path", None):
            delegate._sink_path.unlink(missing_ok=True)
        self.directory.cleanup()

    def begin(self):
        self.collector.connect(PASSWORD)
        self.assertEqual(self.collector.start("direct_host")["state"], "recording")

    def pump(self, limit=10000):
        for _ in range(limit):
            peer = self.device.peer
            if not peer or peer.closed or not peer.messages:
                break
            self.collector._delegate._step()

    def capture(self, n):
        for _ in range(n):
            self.device.acquire(1)
            self.pump()

    def lose(self):
        self.device.peer.close()
        self.collector._delegate._step()
        self.assertTrue(self.collector.snapshot()["cleanup_pending"])

    def recover(self):
        self.clock.advance(8)
        self.collector._delegate._step()
        self.pump()

    def frozen(self):
        state = self.collector.snapshot()
        return {key: copy.deepcopy(state[key]) for key in ("path", "session_id", "count", "history")}, Path(state["path"]).read_bytes()

    def assert_frozen(self, checkpoint):
        state, raw = checkpoint
        self.assertEqual({key: self.collector.snapshot()[key] for key in state}, state)
        self.assertEqual(Path(state["path"]).read_bytes(), raw)
        self.assertFalse(self.collector.snapshot()["complete"])

    def test_protocol2_one_authenticated_socket_clean_stop_all_columns(self):
        self.begin()
        self.assertEqual(len(self.device.factory_calls), 1)
        self.capture(6)
        result = self.collector.stop()
        self.assertTrue(result["complete"])
        self.assertFalse(result["cleanup_pending"])
        self.assertEqual(result["count"], 6)
        rows = list(csv.DictReader(io.StringIO(self.collector.export_csv()["csv"])))
        for row, sample in zip(rows, self.device.originals):
            self.assertEqual(int(row["seq"]), sample["seq"])
            for channel, name in enumerate(FEATURE_ORDER):
                self.assertEqual(float(row["voltage_" + name]), sample["sensor_voltage"][channel])
                self.assertEqual(int(row["gain_" + name]), sample["sensor_gain"][channel])
                self.assertEqual(int(row["status_" + name]), sample["sensor_status"][channel])
        for i, event in enumerate(self.device.sync_events):
            if event[0] == "ack":
                self.assertEqual(self.device.sync_events[i - 1][0], "fsync")
        self.assertFalse(any(c["cmd"] == "RESUME_DATASET" for c in self.device.commands))

    def test_loss_freezes_original_and_private_cleanup_allows_next_direct_then_replay(self):
        self.begin()
        self.capture(3)
        frozen = self.frozen()
        sample_events = sum(event["type"] == "sample" for event in self.events)
        self.lose()
        self.device.acquire(15)
        self.recover()
        self.assert_frozen(frozen)
        result = self.collector.snapshot()
        self.assertTrue(result["cleanup_confirmed"])
        self.assertFalse(result["cleanup_pending"])
        self.assertFalse(result["connected"])
        self.assertEqual(result["cleanup_saved_count"], 15)
        self.assertFalse(self.device.sampling)
        self.assertFalse(self.device.records)
        self.assertEqual(sum(event["type"] == "sample" for event in self.events), sample_events)
        self.assertFalse(self.collector._delegate._sink_path.exists())
        self.collector.connect(PASSWORD)
        self.collector.start("next_direct")
        self.capture(2)
        self.assertTrue(self.collector.stop()["complete"])
        replay = WirelessDatasetReplayCollector(self.directory.name, websocket_factory=self.device.factory,
            clock=self.clock, fsync=self.sync, autostart_worker=False)
        try:
            replay.connect(PASSWORD)
            replay.start("next_replay")
            self.device.acquire(1)
            while self.device.peer.messages:
                replay._step()
            self.assertTrue(replay.stop()["complete"])
        finally:
            replay.disconnect()
        self.assertEqual(Path(frozen[0]["path"]).read_bytes(), frozen[1])

    def test_explicit_disconnect_starts_cleanup_second_pauses_manual_connect_resumes(self):
        self.begin()
        self.capture(2)
        frozen = self.frozen()
        self.assertTrue(self.collector.disconnect()["cleanup_active"])
        paused = self.collector.disconnect()
        self.assertTrue(paused["cleanup_pending"])
        self.assertTrue(paused["cleanup_paused"])
        calls = len(self.device.factory_calls)
        self.clock.advance(100)
        self.collector._delegate._step()
        self.assertEqual(len(self.device.factory_calls), calls)
        with self.assertRaises(RuntimeError):
            self.collector.start("forbidden")
        self.device.acquire(3)
        self.assertTrue(self.collector.connect(PASSWORD)["cleanup_pending"])
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assert_frozen(frozen)

    def test_ambiguous_start_ack_lost_cleans_exact_owned_session_without_start_retry(self):
        self.device.start_fault = "ack_lost"
        self.collector.connect(PASSWORD)
        with self.assertRaises(RuntimeError):
            self.collector.start("ambiguous")
        self.assertTrue(self.collector.snapshot()["cleanup_pending"])
        self.device.acquire(3)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(self.collector.snapshot()["count"], 0)
        self.assertEqual(sum(c["cmd"] == "START_DATASET" for c in self.device.commands), 1)

    def test_correlated_start_rejection_never_owns_or_stops_foreign_session(self):
        original = self.device.command
        def reject(command, peer):
            if command["cmd"] == "START_DATASET":
                self.device.commands.append(command)
                self.device.ack(command, peer, "error")
            else:
                original(command, peer)
        self.device.command = reject
        self.collector.connect(PASSWORD)
        with self.assertRaises(RuntimeError):
            self.collector.start("rejected")
        state = self.collector.snapshot()
        self.assertFalse(state["cleanup_pending"])
        self.assertEqual(state["error"], "device_rejected_start_dataset")
        self.assertEqual([c["cmd"] for c in self.device.commands], ["START_DATASET"])
        self.collector.connect(PASSWORD)
        self.device.command = original
        self.assertEqual(self.collector.start("valid")["state"], "recording")
        self.assertTrue(self.collector.stop()["complete"])

    def test_start_not_delivered_reconciles_idle_without_stop_resume_or_retry(self):
        self.device.start_fault = "not_delivered"
        self.collector.connect(PASSWORD)
        with self.assertRaises(RuntimeError):
            self.collector.start("not_delivered")
        self.recover()
        state = self.collector.snapshot()
        self.assertFalse(state["cleanup_pending"])
        self.assertEqual(state["cleanup_error"], "owned_session_absent_no_foreign_stop_sent")
        self.assertEqual([c["cmd"] for c in self.device.commands], ["START_DATASET"])
        self.device.start_fault = None
        self.collector.connect(PASSWORD)
        self.assertEqual(self.collector.start("next")["state"], "recording")
        self.assertTrue(self.collector.stop()["complete"])

    def test_lost_stop_ack_reuses_id_summary_before_ack_does_not_unlock_early(self):
        self.begin()
        self.capture(2)
        self.device.stop_fault = "ack_lost"
        result = self.collector.stop()
        self.assertTrue(result["cleanup_pending"])
        frozen = self.frozen()
        self.clock.advance(8)
        self.collector._delegate._step()
        # Resume ACK + status sends original Stop; already queued terminal summary is earlier than its ACK.
        self.collector._delegate._step()
        self.collector._delegate._step()
        self.collector._delegate._step()
        self.assertTrue(self.collector.snapshot()["cleanup_pending"])
        self.pump()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(len(self.device.stop_ids), 2)
        self.assertEqual(*self.device.stop_ids)
        self.assert_frozen(frozen)

    def test_ack_send_failure_after_fsync_keeps_original_row_and_resume_prefix(self):
        self.begin()
        command = self.device.command
        failed = [False]
        def fail_once(wire, peer):
            if wire["cmd"] == "ACK_SAMPLES" and not failed[0]:
                failed[0] = True
                peer.close()
                raise ConnectionError()
            command(wire, peer)
        self.device.command = fail_once
        self.capture(1)
        self.assertEqual(self.collector.snapshot()["count"], 1)
        frozen = self.frozen()
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual([c["next_seq"] for c in self.device.commands if c["cmd"] == "RESUME_DATASET"], [1])
        self.assert_frozen(frozen)

    def test_foreign_boot_device_session_label_and_profile_never_receive_stop(self):
        for field, value in (("boot", "b" * 32), ("device_id", "1003"), ("sid", "foreign"),
                             ("label", "foreign"), ("profile", 2)):
            with self.subTest(field=field):
                if self.collector._delegate:
                    self.tearDown()
                    self.setUp()
                self.begin()
                self.capture(1)
                self.lose()
                frozen = self.frozen()
                setattr(self.device, field, value)
                self.recover()
                self.assert_frozen(frozen)
                self.assertFalse(any(c["cmd"] in {"RESUME_DATASET", "STOP_DATASET"} for c in self.device.commands))
                if field == "boot":
                    self.assertFalse(self.collector.snapshot()["cleanup_pending"])
                else:
                    self.assertTrue(self.collector.snapshot()["cleanup_paused"])

    def test_failed_connect_preserves_prior_csv_history_and_redacts_exception(self):
        self.begin()
        self.capture(2)
        self.collector.stop()
        before = self.collector.snapshot()
        raw = Path(before["path"]).read_bytes()
        def fail(*args, **kwargs):
            raise RuntimeError("Authorization Basic " + PASSWORD)
        self.collector._factory = fail
        with self.assertRaisesRegex(RuntimeError, "compatible GLD"):
            self.collector.connect(PASSWORD)
        after = self.collector.snapshot()
        for key in ("count", "history", "session_id", "path", "complete"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(Path(before["path"]).read_bytes(), raw)
        self.assertNotIn(PASSWORD, json.dumps([after, self.events]))
        self.assertNotIn("Authorization", json.dumps([after, self.events]))

    def test_cleanup_sink_failure_no_ack_no_unlock_close_and_resume(self):
        self.begin()
        self.capture(2)
        frozen = self.frozen()
        self.lose()
        self.device.acquire(4)
        child = self.collector._delegate._cleanup
        def fail(_fd):
            raise OSError("private disk details")
        child._fsync = fail
        acks = sum(c["cmd"] == "ACK_SAMPLES" for c in self.device.commands)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_paused"])
        self.assertTrue(self.collector.snapshot()["cleanup_pending"])
        self.assertEqual(sum(c["cmd"] == "ACK_SAMPLES" for c in self.device.commands), acks)
        self.assertIsNone(child._file)
        self.assert_frozen(frozen)
        child._fsync = self.sync
        self.collector.connect(PASSWORD)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assert_frozen(frozen)

    def test_original_disk_failure_is_sticky_and_export_fails_closed(self):
        self.begin()
        self.capture(2)
        delegate = self.collector._delegate
        original = delegate._fsync
        def fail(_fd):
            raise OSError("private disk details")
        delegate._fsync = fail
        self.lose()
        self.assertEqual(self.collector.snapshot()["original_csv_error"], "original_csv_disk_failure")
        delegate._cleanup._fsync = original
        delegate._fsync = original
        self.collector.connect(PASSWORD)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(self.collector.snapshot()["cleanup_error"], "original_csv_disk_failure")
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            self.collector.export_csv()

    def test_partial_original_row_not_acknowledged_and_rollback_is_frozen(self):
        self.begin()
        delegate = self.collector._delegate
        original = delegate._fsync
        failed = [False]
        def fail_once(fd):
            if not failed[0]:
                failed[0] = True
                raise OSError("private filesystem failure")
            original(fd)
        delegate._fsync = fail_once
        self.capture(1)
        self.assertEqual(self.collector.snapshot()["count"], 0)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(self.collector.export_csv()["csv"])))), 0)
        self.assertFalse(any(c["cmd"] == "ACK_SAMPLES" for c in self.device.commands))
        frozen = self.frozen()
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(self.collector.snapshot()["cleanup_saved_count"], 1)
        self.assert_frozen(frozen)

    def test_sink_open_fsync_failure_closes_file_and_retry_rewrites_header(self):
        self.begin()
        self.capture(1)
        delegate = self.collector._delegate
        sync = delegate._fsync
        calls = [0]
        def fail_second(fd):
            calls[0] += 1
            if calls[0] == 2:  # original cutoff sync succeeds; new private header fails.
                raise OSError("private filesystem failure")
            sync(fd)
        delegate._fsync = fail_second
        self.lose()
        self.assertTrue(self.collector.snapshot()["cleanup_paused"])
        self.assertIsNone(delegate._cleanup._file)
        self.assertEqual(delegate._sink_durable_offset, 0)
        delegate._fsync = sync
        self.collector.connect(PASSWORD)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])

    def test_failed_private_close_cannot_confirm_cleanup(self):
        self.begin()
        self.capture(1)
        self.lose()
        child = self.collector._delegate._cleanup
        stream = child._file
        class BadClose:
            def __getattr__(self, name):
                return getattr(stream, name)
            def close(self):
                stream.close()
                raise OSError("private close error")
        child._file = BadClose()
        self.recover()
        state = self.collector.snapshot()
        self.assertTrue(state["cleanup_pending"])
        self.assertTrue(state["cleanup_paused"])
        self.assertFalse(state["cleanup_confirmed"])
        self.collector.connect(PASSWORD)
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])

    def test_cleanup_loss_after_durable_suffix_uses_combined_prefix_and_no_duplicate_rows(self):
        self.begin()
        self.capture(2)
        frozen = self.frozen()
        self.lose()
        self.device.acquire(12)
        self.device.ignore_acks = True
        delegate = self.collector._delegate
        delegate._step()  # reconnect and enqueue Resume ACK/status.
        for _ in range(6):  # two controls then four private rows.
            delegate._step()
        child = delegate._cleanup
        self.assertEqual(child.next_seq, 6)
        self.assertEqual(child.count, 6)
        self.device.peer.close()
        delegate._step()
        self.device.ignore_acks = False
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual([c["next_seq"] for c in self.device.commands if c["cmd"] == "RESUME_DATASET"], [2, 6])
        self.assertEqual(self.collector.snapshot()["cleanup_saved_count"], 12)
        self.assert_frozen(frozen)

    def test_603_private_retained_rows_drain_without_touching_original(self):
        self.begin()
        self.device.acquire(5)
        self.collector._delegate._step()  # one fsynced ACK at this clock, four still queued.
        self.assertEqual(self.collector.snapshot()["count"], 1)
        frozen = self.frozen()
        self.lose()
        self.device.acquire(599)  #299.5s since actual ACK progress,603retained.
        self.assertEqual(len(self.device.records), 603)
        self.collector._delegate._step()
        self.pump()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(self.collector.snapshot()["cleanup_saved_count"], 603)
        self.assertLessEqual(self.device.max_window_seen, 8)
        self.assert_frozen(frozen)

    def test_terminal_retention_ready_false_still_stops_drains_owned_ledger(self):
        self.begin()
        self.capture(1)
        self.lose()
        frozen = self.frozen()
        self.device.acquire(10)
        self.device.terminal("retention_limit")
        self.device.ready = False
        self.recover()
        state = self.collector.snapshot()
        self.assertTrue(state["cleanup_confirmed"])
        self.assertFalse(state["complete"])
        self.assertEqual(self.collector._delegate._cleanup.terminal_reason, "retention_limit")
        self.assert_frozen(frozen)

    def test_malformed_hello_new_boot_cannot_release_ownership(self):
        self.begin()
        self.lose()
        self.device.boot = "b" * 32
        hello = self.device.hello
        def malformed():
            return dict(hello(), capacity=999)
        self.device.hello = malformed
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_pending"])
        self.assertTrue(self.collector.snapshot()["cleanup_paused"])
        self.assertFalse(any(c["cmd"] in {"RESUME_DATASET", "STOP_DATASET"} for c in self.device.commands))

    def test_complete_csv_survives_later_transport_end(self):
        self.begin()
        self.capture(2)
        complete = self.collector.stop()
        raw = Path(complete["path"]).read_bytes()
        self.collector._delegate._loss("late_transport_end")
        state = self.collector.snapshot()
        self.assertTrue(state["complete"])
        self.assertFalse(state["cleanup_pending"])
        self.assertEqual(Path(complete["path"]).read_bytes(), raw)

    def test_cleanup_duplicate_sample_after_lost_ack_uses_original_durable_content(self):
        self.begin()
        self.capture(2)
        self.lose()
        self.device.acquire(3)
        delegate = self.collector._delegate
        delegate._step()
        delegate._step()
        delegate._step()
        delegate._step()  # one private sample is durable.
        child = delegate._cleanup
        self.device.peer.messages.appendleft(dict(self.device.originals[2]))
        self.pump()
        self.assertTrue(self.collector.snapshot()["cleanup_confirmed"])
        self.assertEqual(child.duplicate_count, 1)
        self.assertEqual(self.collector.snapshot()["count"], 2)
        self.assertEqual(self.collector.snapshot()["cleanup_saved_count"], 3)

    def test_real_worker_cleanup_backoff_cancel_is_bounded_and_keeps_owner(self):
        self.collector = WirelessDatasetDirectCollector(self.directory.name,
            websocket_factory=self.device.factory, clock=self.clock, fsync=self.sync,
            command_timeout=2, silence_timeout=3, autostart_worker=True)
        self.begin()
        self.device.unavailable = True
        self.device.peer.close()
        eventually(lambda: self.collector.snapshot()["cleanup_pending"])
        owner = self.collector.snapshot()["session_id"]
        started = time.monotonic()
        state = self.collector.disconnect()
        self.assertLess(time.monotonic() - started, .5)
        self.assertTrue(state["cleanup_pending"])
        self.assertTrue(state["cleanup_paused"])
        self.assertEqual(state["session_id"], owner)
        self.assertFalse(self.collector._delegate._cleanup._thread.is_alive())
        self.assertIsNone(self.collector._delegate._cleanup._password)

    def test_cleanup_retries_capped_and_auth_rejection_pauses_with_no_secret(self):
        self.begin()
        self.lose()
        self.device.unavailable = True
        child = self.collector._delegate._cleanup
        delays = []
        for _ in range(10):
            delay = child._next_retry_at - self.clock()
            delays.append(delay)
            self.clock.advance(delay)
            self.collector._delegate._step()
        self.assertEqual(delays[:4], [0, 2, 4, 8])
        self.assertTrue(all(delay == 8 for delay in delays[3:]))
        self.assertTrue(self.collector.snapshot()["cleanup_active"])
        class AuthError(Exception):
            status_code = 401
        def reject(*_args, **_kwargs):
            raise AuthError("Authorization " + PASSWORD)
        self.collector._delegate._cleanup_factory = reject
        self.recover()
        self.assertTrue(self.collector.snapshot()["cleanup_paused"])
        self.assertEqual(self.collector.snapshot()["cleanup_error"], "authentication_rejected")
        self.assertIsNone(child._password)
        self.assertNotIn(PASSWORD, json.dumps(self.collector.snapshot()))

    def test_legacy_protocol1_delegates_one_socket_and_clean_csv(self):
        self.collector.disconnect()
        peer, calls = Peer(), []
        def factory(url, **options):
            calls.append((url, options))
            return peer
        self.collector = WirelessDatasetDirectCollector(self.directory.name, websocket_factory=factory, command_timeout=.2)
        self.assertTrue(self.collector.connect(PASSWORD)["ready"])
        self.collector.start("legacy")
        peer.emit_sample(0)
        eventually(lambda: self.collector.snapshot()["count"] == 1)
        self.assertTrue(self.collector.stop()["complete"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["http_no_proxy"], ["*"])
        expected = base64.b64encode(("gld:" + PASSWORD).encode()).decode()
        self.assertEqual(calls[0][1]["header"], ["Authorization: Basic " + expected])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(self.collector.export_csv()["csv"])))), 1)


if __name__ == "__main__":
    unittest.main()
