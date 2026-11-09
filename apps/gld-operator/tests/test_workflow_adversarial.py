"""Independent protocol3 boundary faults; inert socket and durable-ledger fake.

No firmware build, server, network, native platform, dialog or hardware action.
This is not a Python implementation of the firmware state machine.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wireless_dataset import FEATURE_ORDER
from wireless_dataset_replay import ProtocolError
from wireless_dataset_workflow import WorkflowCollector
from dataset_workflow import DatasetWorkflowService


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now


class InertSocket:
    def __init__(self, events):
        self.events, self.closed = events, False
    def send(self, raw):
        self.events.append(("wire", json.loads(raw)))
    def recv(self):
        raise TimeoutError()
    def close(self):
        self.closed = True


def hello(**changes):
    value = dict(type="hello", protocol="gld-dataset-wifi/3", device_id="1002",
        boot_id="a" * 32, session_id="owned-session", label="ground_truth", ready=True,
        nulling_profile_id=1, interval_ms=500, retention_ms=300000, capacity=640,
        feature_order=list(FEATURE_ORDER), sampling=True, paused=False, incomplete=False,
        total_samples=0, oldest_seq=0, acked_next_seq=0, buffered_samples=0,
        transition_seq=0, prediction_enabled=False, prediction_ready=True,
        capabilities=dict(pause=True, **{"continue": True}, durable_replay=True,
            prediction=True, requires_protocol3_client=True),
        model=dict(profile_id="cnn-dualbranch-board-1-2class-v2",
            scaler_profile_id="cnn-dualbranch-board-1-2class-v2", runtime_version="0.8.36",
            production_approved=True, output_elements=2, class_map=[0, 1]))
    value.update(changes)
    return value


def status(**changes):
    value = {key: value for key, value in hello().items() if key in {
        "device_id", "boot_id", "session_id", "label", "nulling_profile_id", "sampling",
        "paused", "incomplete", "total_samples", "oldest_seq", "acked_next_seq",
        "buffered_samples", "transition_seq", "prediction_enabled"}}
    value.update(type="status", state="running", reason="started")
    value.update(changes)
    return value


def row(seq=0):
    return dict(type="sample", device_id="1002", session_id="owned-session", seq=seq,
        timestamp_ms=500 + seq * 500, scan_end_ms=725 + seq * 500, mode="DATASET",
        label="ground_truth", nulling_profile_id=1, overrun_count=0,
        sensor_voltage=[0.11 + index * 0.27 for index in range(8)],
        sensor_gain=[1, 2, 4, 8, 16, 32, 64, 1], sensor_status=[0] * 8,
        feature_order=list(FEATURE_ORDER), prediction=dict(enabled=False, status="disabled",
            valid=False, predicted_class=None, gas_class=None, confidence=None, inference_duration_ms=0))


class WorkflowAdversarial(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.events, self.ledger = [], []
        self.clock = Clock()
        def persist(record, _collector):
            self.ledger.append(copy.deepcopy(record))
            self.events.append(("durable", record["seq"]))
        def forbidden_factory(*_args, **_kwargs):
            raise AssertionError("A boundary test must never open a connection")
        self.collector = WorkflowCollector(self.directory.name, persist=persist,
            cutoff=lambda reason: self.events.append(("cutoff", reason)),
            expected_device_id="1002", mode="replay", clock=self.clock,
            websocket_factory=forbidden_factory, autostart_worker=False)
        self.collector._hello(hello(session_id="", label="", sampling=False), False)
        current = self.collector
        current.session_id, current.label = "owned-session", "ground_truth"
        current._active = current._want_link = current._start_confirmed = current._stream_confirmed = True
        current._password = "fixture-private-credential"
        current.sampling, current.state, current.ready = True, "recording", True
        current._ws = InertSocket(self.events)

    def tearDown(self):
        self.collector._want_link = False
        self.collector._close_socket()
        self.directory.cleanup()

    def test_all_eight_values_are_durable_before_prefix_ack(self):
        sample = row()
        self.collector._receive(sample)
        self.assertEqual(self.events[0], ("durable", 0))
        self.assertEqual(self.events[1][1], dict(cmd="ACK_SAMPLES", session_id="owned-session",
            boot_id="a" * 32, next_seq=1))
        for field in ("sensor_voltage", "sensor_gain", "sensor_status", "feature_order", "prediction"):
            self.assertEqual(self.ledger[0][field], sample[field])
        self.assertEqual(self.collector.next_seq, 1)

    def test_persist_failure_does_not_ack_or_advance_prefix(self):
        def failure(*_args):
            raise OSError("synthetic ledger fsync failure")
        self.collector._persist = failure
        self.collector._receive(row())
        self.assertEqual(self.collector.next_seq, 0)
        self.assertFalse(any(event[0] == "wire" for event in self.events))
        self.assertFalse(self.collector.complete)

    def test_changed_duplicate_prediction_cannot_advance_ack(self):
        self.collector._receive(row())
        prior = len(self.events)
        changed = row()
        changed["prediction"]["inference_duration_ms"] = 1
        with self.assertRaises(ProtocolError):
            self.collector._receive(changed)
        self.assertEqual(len(self.events), prior)
        self.assertEqual(len(self.ledger), 1)

    def test_running_status_without_samples_does_not_defeat_silence_deadline(self):
        for moment in (1.0, 2.0, 3.0):
            self.clock.now = moment
            self.collector._status(status())
        self.clock.now = 4.0
        self.collector._step()
        self.assertTrue(self.collector.recovery_active)
        self.assertIsNone(self.collector._ws)

    def test_paused_empty_status_is_valid_liveness_without_new_samples(self):
        for moment in (1.0, 2.0, 3.0):
            self.clock.now = moment
            self.collector._status(status(state="paused", sampling=False, paused=True))
        self.clock.now = 4.0
        self.collector._step()
        self.assertFalse(self.collector.recovery_active)
        self.assertIsNotNone(self.collector._ws)
        self.assertEqual(self.collector.count, 0)

    def test_recovery_rejoins_selected_wifi_before_socket_retry(self):
        order = []
        self.collector._rejoin_wifi = lambda password: order.append(("wifi", password))
        def failed_socket(*_args, **_kwargs):
            order.append(("socket", None))
            raise ConnectionError("inert transport failure")
        self.collector._factory = failed_socket
        self.collector._loss("transport_lost")
        self.clock.now = self.collector._next_retry_at
        self.collector._step()
        self.assertEqual(order, [("wifi", "fixture-private-credential"), ("socket", None)])
        self.assertTrue(self.collector.recovery_active)
        self.assertEqual(self.collector._password, "fixture-private-credential")

    def test_failed_wifi_rejoin_keeps_owned_session_and_backs_off(self):
        attempts = []
        def failed_rejoin(_password):
            attempts.append(self.clock.now)
            raise RuntimeError("inert WLAN unavailable")
        self.collector._rejoin_wifi = failed_rejoin
        self.collector._loss("transport_lost")
        self.clock.now = self.collector._next_retry_at
        self.collector._step()
        self.assertEqual(attempts, [self.clock.now])
        self.assertEqual(self.collector.error, "reconnect_failed")
        self.assertGreater(self.collector._next_retry_at, self.clock.now)
        self.assertTrue(self.collector._active)
        self.assertEqual(self.collector.next_seq, 0)

    def test_terminal_retention_supersedes_accepted_pause_with_lost_ack(self):
        current = self.collector
        current._transition_intent = dict(cmd="PAUSE_DATASET", seq=1, id="pause-id")
        current._hello(hello(sampling=False, paused=False, incomplete=True, reason="retention_limit",
            total_samples=1, buffered_samples=1, transition_seq=1), True)
        self.assertFalse(current.paused)
        self.assertTrue(current._terminal_incomplete)
        self.assertEqual(current.total_samples, 1)
        self.assertEqual(current.next_seq, 0)
        self.assertFalse(any(event[0] == "wire" for event in self.events))

    def test_start_ack_cannot_confirm_a_different_transition_frontier(self):
        current = self.collector
        current._send_control("START_DATASET", dict(label=current.label, sample_interval_ms=500, prediction_enabled=False), "start-id")
        with self.assertRaises(ProtocolError):
            current._receive(dict(type="ack", cmd="START_DATASET", command_id="start-id",
                session_id=current.session_id, boot_id=current.boot_id, result="ok", transition_seq=4, paused=False))

    def test_pause_ack_cannot_confirm_prior_transition_frontier(self):
        current = self.collector
        current._transition_intent = dict(cmd="PAUSE_DATASET", seq=1, id="pause-id")
        current._send_transition()
        with self.assertRaises(ProtocolError):
            current._receive(dict(type="ack", cmd="PAUSE_DATASET", command_id="pause-id",
                session_id=current.session_id, boot_id=current.boot_id, result="ok", transition_seq=0, paused=True))

    def test_prediction_class_must_match_exact_model_mapping(self):
        current = self.collector
        current.prediction_enabled = True
        sample = row()
        sample["prediction"] = dict(enabled=True, valid=True, status="valid", predicted_class=1,
            gas_class=0, confidence=.8, inference_duration_ms=23)
        with self.assertRaises(ProtocolError):
            current._receive(sample)
        self.assertEqual(current.next_seq, 0)
        self.assertFalse(self.ledger)

    def test_late_rejected_continue_cannot_orphan_already_requested_stop(self):
        current = self.collector
        current.paused, current.sampling, current.transition_seq = True, False, 1
        current._transition_intent = dict(cmd="CONTINUE_DATASET", seq=2, id="continue-id")
        current._send_transition()
        # The user Stop intent may be queued after an uncertain action timeout.
        current._stop_intent = dict(command_id="stable-stop-id", delivered=False)
        current._receive(dict(type="ack", cmd="CONTINUE_DATASET", command_id="continue-id",
            session_id=current.session_id, boot_id=current.boot_id, result="error",
            detail="requires_24v_and_saved_valid_profile", transition_seq=1, paused=True))
        current._status(status(state="paused", paused=True, sampling=False, transition_seq=1))
        stops = [message for kind, message in self.events if kind == "wire" and message["cmd"] == "STOP_DATASET"]
        self.assertTrue(stops, "Requested Stop must not wait forever behind a rejected transition")
        self.assertEqual(stops[0]["command_id"], "stable-stop-id")


class WorkflowLedgerAdversarial(unittest.TestCase):
    """Real temporary files and injected failures at the two-file commit boundary."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        directory = Path(self.directory.name)
        self.service = DatasetWorkflowService(directory / "backend", object(), autostart_worker=False)
        self.service.csv_path = str(directory / "operator.csv")
        self.service.label = "ground_truth"
        self.service._engine = SimpleNamespace(device_id="1002", nulling_profile_id=1,
            boot_id="a" * 32, model=hello()["model"], direct_cutoff=False)
        self.service._segment_id = 1
        self.service._open_first()
        self.original_header = Path(self.service.csv_path).read_bytes()

    def tearDown(self):
        self.service._close_public()
        if self.service._private is not None:
            self.service._private.close()
            self.service._private = None
        self.directory.cleanup()

    def persist(self, seq=0):
        sample = row(seq)
        sample.pop("type")
        self.service._persist(sample, self.service._engine)

    def test_public_fsync_failure_rolls_back_both_files_and_retry_has_one_row(self):
        service = self.service
        original_sync = service._fsync
        public_fd = service._public.fileno()
        failed = [False]
        def fail_once(fd):
            if fd == public_fd and not failed[0]:
                failed[0] = True
                raise OSError("synthetic public fsync failure")
            original_sync(fd)
        service._fsync = fail_once
        with self.assertRaises(OSError):
            self.persist()
        self.assertEqual(Path(service.csv_path).read_bytes(), self.original_header)
        self.assertEqual(Path(service.ledger_path).read_bytes(), b"")
        self.assertEqual(service.count, 0)
        service._fsync = original_sync
        self.persist()
        service._close_public()
        service._verify()
        self.assertEqual(service.verification["count"], 1)
        self.assertTrue(service.verification["verified"])

    def test_partial_public_write_does_not_leave_uncommitted_ledger_or_csv_tail(self):
        service = self.service
        stream = service._public
        class PartialWrite:
            def __getattr__(self, name):
                return getattr(stream, name)
            def write(self, value):
                stream.write(value[:11])
                raise OSError("synthetic partial write")
        service._public = PartialWrite()
        with self.assertRaises(OSError):
            self.persist()
        self.assertEqual(Path(service.csv_path).read_bytes(), self.original_header)
        self.assertEqual(Path(service.ledger_path).read_bytes(), b"")
        self.assertEqual(service.count, 0)

    def test_verification_uses_real_complete_files_without_ui_history(self):
        service = self.service
        for seq in range(5):
            self.persist(seq)
        service._history.clear()
        service._close_public()
        service._verify()
        self.assertTrue(service.verification["verified"])
        self.assertEqual(service.verification["count"], 5)
        self.assertEqual(service.count, 5)

    def test_external_csv_change_blocks_append_without_touching_existing_files(self):
        service = self.service
        self.persist()
        service._close_public()
        service._verify()
        path = Path(service.csv_path)
        path.write_bytes(path.read_bytes() + b"unrelated external tail\r\n")
        original = path.read_bytes()
        ledger = Path(service.ledger_path).read_bytes()
        with self.assertRaises(RuntimeError):
            service._open_append()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(Path(service.ledger_path).read_bytes(), ledger)
        self.assertFalse(service.verification["verified"])

    def test_zero_public_rows_remain_incomplete_after_private_cleanup_completed(self):
        service = self.service
        # Legitimate accepted Start/ACK-loss: no public rows; remote private
        # cleanup can finish cleanly while the logical recording is incomplete.
        service._logical_incomplete = True
        service._complete = False
        service._segment_closed = True
        service._engine_state = dict(state="complete", complete=True, connected=False)
        service._close_public()
        service._verify()
        state = service.snapshot()
        self.assertTrue(state["verification"]["verified"])
        self.assertEqual(state["count"], 0)
        self.assertEqual(state["state"], "incomplete")
        self.assertFalse(state["complete"])

    def test_private_ledger_creation_failure_can_retry_after_storage_repair(self):
        original_open = Path.open
        failed = [False]
        def fail_once(path, mode="r", *args, **kwargs):
            if path.name.startswith("cleanup_") and mode == "x+" and not failed[0]:
                failed[0] = True
                raise OSError("synthetic repaired permission failure")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", new=fail_once):
            with self.assertRaises(OSError):
                self.service._open_private()
            self.assertIsNone(self.service._private)
            self.service._open_private()
        self.assertTrue(Path(self.service._private_path).is_file())
        self.assertEqual(self.service._private_offset, 0)

    def test_missing_private_ledger_with_durable_prefix_is_never_recreated(self):
        service = self.service
        path = Path(self.directory.name) / "lost-private-ledger.jsonl"
        service._private_path, service._private_offset = str(path), 42
        with self.assertRaises(OSError):
            service._open_private()
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
