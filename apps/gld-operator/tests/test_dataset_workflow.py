"""Deterministic workflow storage/control tests, no sockets or OS Wi-Fi."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataset_workflow import DatasetWorkflowService, csv_columns, project_record
from test_wireless_dataset_replay import Clock, FakePeer, FakeRingDevice

PASSWORD = "workflow-fixture-only"


class Device(FakeRingDevice):
    def __init__(self, clock):
        super().__init__(clock)
        self.paused = self.prediction_enabled = False
        self.transition_seq = 0
        self.last_transition = None
        self.prediction_ready = True
        self.transition_fault = None
        self.model = dict(profile_id="fixture-model1", scaler_profile_id="fixture-scaler1",
            runtime_version="fixture-runtime", production_approved=True, output_elements=2, class_map=[0, 3])

    def hello(self):
        return dict(super().hello(), protocol="gld-dataset-wifi/3", model=copy.deepcopy(self.model),
            paused=self.paused, transition_seq=self.transition_seq, prediction_enabled=self.prediction_enabled,
            prediction_ready=self.prediction_ready, capabilities=dict(pause=True, **{"continue": True},
                durable_replay=True, prediction=True, requires_protocol3_client=True))

    def ack(self, wire, peer, result="ok"):
        peer.messages.append(dict(type="ack", cmd=wire["cmd"], command_id=wire["command_id"],
            session_id=wire["session_id"], boot_id=self.boot, paused=self.paused,
            transition_seq=self.transition_seq, result=result))

    def status(self, peer):
        super().status(peer)
        peer.messages[-1].update(paused=self.paused, transition_seq=self.transition_seq,
            prediction_enabled=self.prediction_enabled,
            state="running" if self.sampling else "paused" if self.paused else "error" if self.incomplete else "stopped")

    def terminal(self, reason):
        super().terminal(reason)
        self.paused = False

    def command(self, wire, peer):
        kind = wire["cmd"]
        if kind == "START_DATASET":
            peer.offered_next, peer.summary_sent = 0, False
            self.outage_at = None
            self.paused, self.transition_seq, self.last_transition = False, 0, None
            self.prediction_enabled = wire.get("prediction_enabled", False)
        elif kind == "STOP_DATASET":
            self.paused = False
        elif kind in {"PAUSE_DATASET", "CONTINUE_DATASET"}:
            self.commands.append(copy.deepcopy(wire))
            valid = (wire["boot_id"] == self.boot and wire["session_id"] == self.sid and
                wire["label"] == self.label and wire["nulling_profile_id"] == self.profile)
            key = (wire["cmd"], wire["command_id"], wire["transition_seq"])
            if valid and key == self.last_transition:
                self.ack(wire, peer); self.status(peer)
                return
            pause = kind == "PAUSE_DATASET"
            valid = valid and wire["transition_seq"] == self.transition_seq + 1 and self.paused != pause and not self.incomplete
            if valid:
                self.paused, self.sampling = pause, not pause
                self.transition_seq, self.last_transition = wire["transition_seq"], key
            if self.transition_fault == "ack_lost":
                self.transition_fault = None
                peer.close()
                return
            self.ack(wire, peer, "ok" if valid else "error")
            self.status(peer)
            return
        super().command(wire, peer)

    def summary(self, peer):
        if not self.paused:
            super().summary(peer)

    def capture(self):
        peer, before = self.peer, self.total
        self.peer = None
        super().capture()
        self.peer = peer
        if self.total == before:
            return
        row = self.records[before]
        row["timestamp_ms"] = round(self.clock() * 1000)
        row["scan_end_ms"] = row["timestamp_ms"] + 230
        status = "disabled" if not self.prediction_enabled else ("warmup", "valid", "error", "not_ready")[before % 4]
        valid = status == "valid"
        row["prediction"] = dict(enabled=self.prediction_enabled, status=status, valid=valid,
            predicted_class=1 if valid else None, gas_class=3 if valid else None,
            confidence=.875 if valid else None, inference_duration_ms=7 if self.prediction_enabled else 0)
        row["sensor_gain"] = [1, 2, 4, 8, 16, 32, 64, 1]
        if peer is not None:
            self.offer(peer)

    def acquire(self, count):
        for _ in range(count):
            super().acquire(1)
            if self.paused and self.peer is not None and not self.peer.closed:
                self.status(self.peer)  # Firmware's paused heartbeat, no captured row.


class Platform:
    def __init__(self, directory):
        self.path = str(Path(directory) / "operator-picked.csv")
        self.joins = []
    def scan(self):
        return [dict(ssid="GLD-DATASET-1002", device_id="1002", name="GLD-1002"),
                dict(ssid="non-GLD", device_id="1003", name="forbidden")]
    def join(self, ssid, password=""):
        self.joins.append(ssid)
        assert ssid == "GLD-DATASET-1002"
    def choose_file(self):
        return self.path
    def validate_file(self, path):
        if path != self.path or Path(path).exists():
            raise ValueError("existing or unpicked file")
        return path


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.device = Device(self.clock)
        self.platform = Platform(self.temp.name)
        self.events = []
        self.service = DatasetWorkflowService(Path(self.temp.name) / "private", self.platform, self.events.append,
            self.device.factory, clock=self.clock, fsync=self.sync, autostart_worker=False,
            command_timeout=2, silence_timeout=3)
        self.durable = {}

    def sync(self, fd):
        os.fsync(fd)
        self.device.sync_events.append(("fsync", None))

    def tearDown(self):
        self.service.disconnect()
        self.service.disconnect()
        self.temp.cleanup()

    def configure(self, mode="replay", prediction=True, optional=True):
        self.service.scan(); self.service.select("1002")
        self.service.connect("1002", PASSWORD)
        self.service.choose_file()
        self.service.configure(dict(label="fixture_label", mode=mode,
            fields=dict(prediction=prediction, gain=optional, status=optional, timing=optional)))
        self.service.lock(True)

    def begin(self, **options):
        self.configure(**options)
        state = self.service.start()
        self.assertEqual(state["state"], "recording")

    def pump(self):
        for _ in range(10000):
            if not self.device.peer or self.device.peer.closed or not self.device.peer.messages:
                break
            self.service._engine._step()

    def capture(self, n):
        for _ in range(n):
            self.device.acquire(1)
            self.pump()

    def lose(self):
        self.device.peer.close()
        self.service._engine._step()

    def recover(self):
        self.clock.advance(8)
        self.service._engine._step()
        self.pump()

    def rows(self):
        return list(csv.DictReader(io.StringIO(self.service.export_csv()["csv"])))

    def assert_all_fields(self):
        rows = self.rows()
        records = [json.loads(line) for line in Path(self.service.ledger_path).read_text().splitlines()]
        self.assertEqual(len(rows), self.service.count)
        self.assertEqual(len(records), len(rows))
        for row, record in zip(rows, records):
            projected = project_record(record, self.service.fields)
            self.assertEqual(row, {k: "" if v is None else str(v) for k, v in projected.items()})
            for index, name in enumerate(FEATURE_ORDER):
                self.assertEqual(float(row[name + " (V)"]), record["sensor_voltage"][index])
        return records

    def test_seven_gates_scan_filter_and_no_arbitrary_file(self):
        with self.assertRaises(RuntimeError): self.service.start()
        with self.assertRaises(RuntimeError): self.service.lock(True)
        self.assertEqual(len(self.service.scan()["devices"]), 1)
        with self.assertRaises(ValueError): self.service.select("1003")
        self.service.select("1002")
        self.service.connect("1002", PASSWORD)
        self.assertEqual(self.platform.joins, ["GLD-DATASET-1002"])
        with self.assertRaises(ValueError): self.service.configure({"csv_path": "unpicked.csv"})
        self.service.choose_file()
        self.service.configure(dict(label="fixture", mode="direct", fields=dict(prediction=False,gain=False,status=False,timing=False)))
        self.assertTrue(self.service.lock(True)["configured"])
        with self.assertRaises(RuntimeError): self.service.configure({"label": "changed"})

    def test_readiness_is_cumulative_and_picker_waits_for_authenticated_device(self):
        def assert_prefix(snapshot, count):
            expected = [True] * count + [False] * (7 - count)
            self.assertEqual(list(snapshot["steps"].values()), expected)
            self.assertEqual(snapshot["configured"], count == 7)
        assert_prefix(self.service.snapshot(), 0)
        with patch.object(self.platform, "choose_file", wraps=self.platform.choose_file) as picker:
            with self.assertRaises(RuntimeError): self.service.choose_file()
            picker.assert_not_called()
        assert_prefix(self.service.scan(), 1)
        assert_prefix(self.service.select("1002"), 2)
        connected = self.service.connect("1002", PASSWORD)
        assert_prefix(connected, 3)
        self.assertEqual(connected["wizard_steps"], dict(connection=True, file=False, fields=False, mode=False, label=False))
        picked = self.service.choose_file()
        assert_prefix(picked, 7)
        self.assertTrue(all(picked["wizard_steps"].values()))
        self.service.configure({"label": ""})
        assert_prefix(self.service.snapshot(), 6)
        self.service.disconnect()
        assert_prefix(self.service.snapshot(), 2)

    def test_connect_without_password_uses_private_resolver_and_never_publishes_secret(self):
        self.service._credential_resolver = lambda: PASSWORD
        self.service.scan(); self.service.select("1002")
        with patch.object(self.platform, "join", wraps=self.platform.join) as join:
            state = self.service.connect("1002")
            join.assert_called_once_with("GLD-DATASET-1002", PASSWORD)
        self.assertTrue(state["connected"])
        self.assertNotIn(PASSWORD, json.dumps([state, self.events]))

    def test_missing_automatic_credentials_never_attempts_wifi_join(self):
        def unavailable():
            raise RuntimeError("Kredensial hotspot GLD belum tersedia.")
        self.service._credential_resolver = unavailable
        self.service.scan(); self.service.select("1002")
        with patch.object(self.platform, "join") as join:
            with self.assertRaisesRegex(RuntimeError, "Kredensial"):
                self.service.connect("1002")
            join.assert_not_called()
        self.assertFalse(self.service.snapshot()["steps"]["connection"])

    def test_label_timestamp_is_complete_stable_csv_metadata_without_changing_wire_label(self):
        self.service._wall_clock = lambda: datetime(2026, 11, 3, 7, 35)
        self.begin(prediction=False)
        expected = "07:35 Selasa 03/11/26"
        state = self.service.snapshot()
        self.assertEqual(state["label_timestamp"], expected)
        self.assertEqual(state["display_label"], expected + " fixture_label")
        self.assertEqual(self.device.label, "fixture_label")
        self.capture(2)
        self.service.pause(); self.service.resume()
        self.service.stop()
        self.service._wall_clock = lambda: datetime(2026, 11, 4, 18, 5)
        self.service.continue_recording(); self.capture(2)
        stopped = self.service.stop()
        self.assertTrue(stopped["verification"]["verified"])
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["Label pengujian"] == expected + " fixture_label" for row in rows))
        self.assertTrue(all("label_timestamp" not in row and "display_label" not in row and "label" not in row for row in rows))
        self.assert_all_fields()
        reset = self.service.reset()
        self.assertEqual(reset["label_timestamp"], "")
        self.assertEqual(reset["display_label"], "clear_air_test")
        self.service.scan(); self.service.select("1002"); self.service.connect("1002", PASSWORD)
        self.platform.path = str(Path(self.temp.name) / "new-picked.csv")
        self.assertEqual(self.service.choose_file()["label_timestamp"], "18:05 Rabu 04/11/26")

    def test_continue_rejects_changed_label_timestamp_before_appending(self):
        self.begin(prediction=False); self.capture(2)
        stopped = self.service.stop(); path = Path(stopped["csv_path"]); original = path.read_bytes()
        self.service.label_timestamp = "12:00 Rabu 04/11/26"
        with self.assertRaises(RuntimeError): self.service.continue_recording()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.service.snapshot()["can_continue"])

    def test_normal_prediction_all_fields_verified_and_revision_events(self):
        self.begin()
        self.capture(8)
        state = self.service.stop()
        self.assertTrue(state["verification"]["verified"])
        self.assertTrue(state["complete"])
        self.assertTrue(state["can_continue"])
        records = self.assert_all_fields()
        self.assertEqual({r["prediction"]["status"] for r in records}, {"warmup", "valid", "error", "not_ready"})
        self.assertEqual([event["revision"] for event in self.events], sorted(set(event["revision"] for event in self.events)))
        self.assertNotIn(PASSWORD, json.dumps([state, self.events]))

    def test_stop_unlock_unchanged_config_relock_continue_same_csv(self):
        self.begin()
        self.capture(2)
        stopped = self.service.stop()
        self.assertTrue(stopped["configuration_frozen"])
        self.service.lock(False)
        config = dict(label=stopped["label"], mode=stopped["mode"], fields=stopped["fields"])
        self.service.configure(config)
        self.service.lock(True)
        self.service.continue_recording()
        self.capture(3)
        continued = self.service.stop()
        self.assertEqual(continued["csv_path"], stopped["csv_path"])
        self.assertTrue(continued["verification"]["verified"])
        self.assertEqual(continued["count"], 5)
        self.assertEqual({row["segment_id"] for row in self.assert_all_fields()}, {1, 2})

    def test_stop_unlock_rejects_changed_schema_but_unchanged_form_can_relock(self):
        self.begin()
        self.capture(2)
        stopped = self.service.stop()
        self.service.lock(False)
        original = Path(stopped["csv_path"]).read_bytes()
        config = dict(label=stopped["label"], mode=stopped["mode"], fields=stopped["fields"])
        changed = copy.deepcopy(config)
        changed["fields"]["gain"] = not changed["fields"]["gain"]
        with self.assertRaisesRegex(RuntimeError, "Reset"):
            self.service.configure(changed)
        self.assertEqual(self.service.snapshot()["fields"], config["fields"])
        self.assertEqual(Path(stopped["csv_path"]).read_bytes(), original)
        self.service.configure(config)
        self.assertTrue(self.service.lock(True)["can_continue"])
        reset = self.service.reset()
        self.assertFalse(reset["configuration_frozen"])

    def test_pause_is_real_no_acquisition_until_continue_stop_from_paused(self):
        self.begin()
        self.capture(3)
        self.assertEqual(self.service.pause()["state"], "paused")
        self.assertFalse(self.device.sampling)
        before = self.service.count
        self.capture(30)
        self.assertEqual(self.service.count, before)
        self.service.resume()
        self.capture(2)
        self.service.pause()
        state = self.service.stop()
        self.assertTrue(state["complete"])
        rows = self.assert_all_fields()
        self.assertGreater(rows[3]["timestamp_ms"] - rows[2]["timestamp_ms"], 15000)

    def test_continue_new_sid_seq0_one_csv_global_row_and_segment_ids(self):
        self.begin()
        self.capture(3)
        first = self.service.stop()
        sid, path = first["session_id"], first["csv_path"]
        self.service.continue_recording()
        self.capture(2)
        state = self.service.stop()
        self.assertTrue(state["complete"])
        self.assertEqual(state["csv_path"], path)
        self.assertNotEqual(state["session_id"], sid)
        records = self.assert_all_fields()
        self.assertEqual([r["row_id"] for r in records], list(range(5)))
        self.assertEqual([r["segment_id"] for r in records], [1,1,1,2,2])
        self.assertEqual([r["seq"] for r in records], [0,1,2,0,1])

    def test_replay_transport_recovery_never_unpauses(self):
        self.begin()
        self.capture(2)
        self.service.pause()
        self.lose()
        self.device.acquire(8)
        self.recover()
        self.assertTrue(self.device.paused)
        self.assertEqual(self.service.snapshot()["state"], "paused")
        self.assertEqual(self.service.count, 2)
        self.assertEqual(sum(c["cmd"] == "CONTINUE_DATASET" for c in self.device.commands), 0)
        self.assertTrue(self.service.stop()["complete"])

    def test_replay_drop_appends_same_file_session_and_verifies_all_rows(self):
        self.begin()
        self.capture(2)
        before = self.service.snapshot()
        self.lose()
        self.device.acquire(12)
        self.recover()
        self.assertEqual(self.service.count, 14)
        state = self.service.stop()
        self.assertEqual((state["session_id"],state["csv_path"]), (before["session_id"],before["csv_path"]))
        self.assertTrue(state["complete"])
        self.assert_all_fields()

    def test_expected_replay_outage_and_failed_reconnect_have_no_false_control_error(self):
        self.begin(); self.capture(2)
        before = self.service.snapshot()
        self.lose()
        outage = self.service.snapshot()
        self.assertEqual(outage["state"], "recovering")
        self.assertTrue(outage["recovery_active"])
        self.assertEqual(outage["error"], "")
        self.device.unavailable = True
        self.recover()
        self.assertEqual(self.service._engine.error, "reconnect_failed")
        self.assertEqual(self.service.snapshot()["error"], "")
        self.device.acquire(4)
        self.device.unavailable = False
        self.recover()
        after = self.service.snapshot()
        self.assertEqual(after["error"], "")
        self.assertEqual(after["state"], "recording")
        self.assertFalse(after["recovery_active"])
        self.assertEqual((after["csv_path"], after["session_id"]), (before["csv_path"], before["session_id"]))
        self.assertEqual(after["count"], 6)
        self.assertTrue(self.service.stop()["verification"]["verified"])

    def test_sample_silence_recovery_is_not_an_unknown_control_result(self):
        self.begin(); self.capture(1)
        self.clock.advance(3.1)
        self.service._engine._step()
        self.assertEqual(self.service._engine.error, "sample_silence_resume_required")
        self.assertEqual(self.service.snapshot()["state"], "recovering")
        self.assertEqual(self.service.snapshot()["error"], "")
        self.recover()
        self.assertEqual(self.service.snapshot()["error"], "")
        self.assertTrue(self.service.stop()["complete"])

    def test_unknown_start_notice_survives_reconnect_failure_until_actual_confirmation(self):
        self.configure(); self.device.start_fault = "ack_lost"
        self.service.start()
        notice = self.service.snapshot()["error"]
        self.assertIn("belum mengonfirmasi", notice)
        self.assertFalse(self.service._engine._start_confirmed)
        self.device.unavailable = True; self.recover()
        self.assertEqual(self.service.snapshot()["error"], notice)
        self.device.unavailable = False
        self.clock.advance(8); self.service._engine._step()  # hello/RESUME sent; status not consumed.
        self.assertEqual(self.service.snapshot()["error"], notice)
        self.pump()
        self.assertTrue(self.service._engine._stream_confirmed)
        self.assertEqual(self.service.snapshot()["error"], "")
        self.assertTrue(self.service.stop()["complete"])

    def test_unknown_pause_and_stop_notices_remain_until_device_reconciles(self):
        self.begin(); self.capture(1)
        self.device.transition_fault = "ack_lost"
        self.service.pause()
        notice = self.service.snapshot()["error"]
        self.assertIn("belum mengonfirmasi", notice)
        self.assertIsNotNone(self.service._engine._transition_intent)
        self.recover()
        self.assertEqual(self.service.snapshot()["state"], "paused")
        self.assertEqual(self.service.snapshot()["error"], "")
        self.device.stop_fault = "ack_lost"
        state = self.service.stop()
        self.assertIn("belum mengonfirmasi", state["error"])
        self.assertFalse(state["verification"]["verified"])
        self.recover()
        state = self.service.snapshot()
        self.assertTrue(state["complete"])
        self.assertTrue(state["verification"]["verified"])
        self.assertEqual(state["error"], "")

    def test_recovery_never_clears_unrelated_service_error(self):
        self.begin(); self.capture(1)
        self.service.error = "Kesalahan penyimpanan yang perlu diperiksa."
        self.lose(); self.recover()
        self.assertEqual(self.service.snapshot()["error"], "Kesalahan penyimpanan yang perlu diperiksa.")
        self.service.stop()

    def test_genuine_engine_notice_does_not_auto_clear_as_transport_notice(self):
        self.begin(); engine = self.service._engine
        engine.error = "device_rejected_transition"; engine._emit()
        notice = self.service.snapshot()["error"]
        self.assertIn("belum mengonfirmasi", notice)
        engine.error = ""; engine._emit()
        self.assertEqual(self.service.snapshot()["error"], notice)
        self.service.stop()

    def test_direct_drop_freezes_public_private_cleanup_then_continue(self):
        self.begin(mode="direct")
        self.capture(3)
        before = self.service.snapshot()
        raw = Path(before["csv_path"]).read_bytes()
        history = before["history"]
        self.lose()
        self.device.acquire(20)
        self.recover()
        state = self.service.snapshot()
        self.assertFalse(state["cleanup_pending"])
        self.assertTrue(state["cleanup_confirmed"])
        self.assertTrue(state["verification"]["verified"])
        self.assertFalse(state["complete"])
        self.assertEqual(state["count"], 3)
        self.assertEqual(state["history"], history)
        self.assertEqual(Path(state["csv_path"]).read_bytes(), raw)
        private = [json.loads(line) for line in Path(state["cleanup_ledger_path"]).read_text().splitlines()]
        self.assertEqual(len(private), 20)
        self.service.continue_recording()
        self.capture(2)
        self.assertTrue(self.service.stop()["verification"]["verified"])
        self.assertEqual(self.service.count, 5)
        self.assert_all_fields()

    def test_external_file_tamper_or_model_change_rejects_continue_without_start(self):
        self.begin()
        self.capture(2)
        state = self.service.stop()
        starts = sum(c["cmd"] == "START_DATASET" for c in self.device.commands)
        with Path(state["csv_path"]).open("a") as stream:
            stream.write("external mutation\n")
        with self.assertRaises(RuntimeError): self.service.continue_recording()
        self.assertEqual(sum(c["cmd"] == "START_DATASET" for c in self.device.commands), starts)
        self.assertFalse(self.service.snapshot()["verification"]["verified"])

    def test_paused_reset_stops_verifies_preserves_files_and_clears_password(self):
        self.begin()
        self.capture(2)
        self.service.pause()
        path, ledger = self.service.csv_path, self.service.ledger_path
        state = self.service.reset()
        self.assertEqual(state["count"], 0)
        self.assertFalse(state["locked"])
        self.assertTrue(Path(path).is_file() and Path(ledger).is_file())
        self.assertIsNone(self.service._password)
        self.assertFalse(self.device.sampling or self.device.paused)

    def test_prediction_unavailable_allows_raw_and_omitted_columns_still_canonical(self):
        self.device.prediction_ready = False
        self.begin(prediction=False, optional=False)
        self.capture(3)
        self.assertTrue(self.service.stop()["complete"])
        records = self.assert_all_fields()
        self.assertEqual(len(self.rows()[0]), 12)
        self.assertTrue(all(row["Predicted Class"] == row["Confidence"] == "" for row in self.rows()))
        self.assertTrue(all(r["prediction"]["predicted_class"] is None for r in records))
        self.assertTrue(all(r["sensor_gain"] == [1,2,4,8,16,32,64,1] for r in records))

    def test_compact_export_exact_headers_optional_columns_and_internal_metadata(self):
        base = ["Waktu (ms)", "Label pengujian", "MQ8 (V)", "MQ135 (V)", "MQ3 (V)", "MQ5 (V)",
                "MQ4 (V)", "MQ7 (V)", "MQ6 (V)", "MQ2 (V)", "Predicted Class", "Confidence"]
        self.assertEqual(self.service.snapshot()["fields"], dict(prediction=False, gain=False, status=False, timing=False))
        for gain, status in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(gain=gain, status=status):
                self.platform.path = str(Path(self.temp.name) / f"compact-{gain}-{status}.csv")
                self.configure(prediction=True, optional=False)
                self.service.lock(False)
                # Even legacy timing=True remains internal; only gain/status extend CSV.
                self.service.configure({"fields": dict(prediction=True, gain=gain, status=status, timing=True)})
                self.service.lock(True); self.service.start(); self.capture(4)
                self.assertTrue(self.service.stop()["verification"]["verified"])
                rows = self.rows()
                expected = base + (["Gain " + n for n in FEATURE_ORDER] if gain else []) + (["Status " + n for n in FEATURE_ORDER] if status else [])
                self.assertEqual(list(rows[0]), expected)
                self.assertEqual(len(rows[0]), 12 + 8 * gain + 8 * status)
                records = self.assert_all_fields()
                for row, record in zip(rows, records):
                    self.assertEqual(int(row["Waktu (ms)"]), record["timestamp_ms"])
                    self.assertEqual(row["Label pengujian"], record["display_label"])
                    for i, name in enumerate(FEATURE_ORDER):
                        if gain: self.assertEqual(int(row["Gain " + name]), record["sensor_gain"][i])
                        if status: self.assertEqual(int(row["Status " + name]), record["sensor_status"][i])
                    for key in ("row_id", "segment_id", "session_id", "boot_id", "device_id", "seq", "model", "feature_order",
                                "nulling_profile_id", "scan_end_ms", "overrun_count", "prediction", "label_timestamp"):
                        self.assertIn(key, record)
                        self.assertNotIn(key, row)
                    if record["prediction"]["valid"]:
                        self.assertEqual(row["Predicted Class"], "1")
                        self.assertEqual(float(row["Confidence"]), .875)
                    else:
                        self.assertEqual(row["Predicted Class"], "")
                        self.assertEqual(row["Confidence"], "")
                self.service.reset()

    def test_compact_prediction_zero_is_valid_and_checkbox_off_keeps_empty_columns(self):
        record = dict(timestamp_ms=500, display_label="test", sensor_voltage=[.1] * 8,
                      prediction=dict(valid=True, predicted_class=0, confidence=0.0))
        for enabled in (False, True):
            fields = dict(prediction=enabled, gain=False, status=False, timing=False)
            result = project_record(record, fields)
            self.assertEqual(len(result), 12)
            self.assertEqual(result["Predicted Class"], 0 if enabled else None)
            self.assertEqual(result["Confidence"], 0.0 if enabled else None)

    def test_compact_csv_changed_cell_is_rejected_without_losing_canonical_record(self):
        self.begin(optional=False); self.capture(4)
        self.assertTrue(self.service.stop()["verification"]["verified"])
        path, ledger = Path(self.service.csv_path), Path(self.service.ledger_path)
        original_ledger = ledger.read_bytes()
        rows = self.rows(); rows[0]["MQ8 (V)"] = "999.0"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        with self.assertRaises(RuntimeError): self.service.continue_recording()
        self.assertEqual(ledger.read_bytes(), original_ledger)

    def test_partial_csv_failure_rolls_back_both_files_no_ack_then_owned_cleanup(self):
        self.begin()
        public_fd = self.service._public.fileno()
        sync = self.service._fsync
        failed = [False]
        def fail_public(fd):
            if fd == public_fd and not failed[0]:
                failed[0] = True
                raise OSError("private disk error must never escape")
            sync(fd)
        self.service._fsync = fail_public
        self.capture(1)
        state = self.service.snapshot()
        self.assertEqual(state["count"], 0)
        self.assertTrue(state["cleanup_paused"])
        self.assertFalse(any(c["cmd"] == "ACK_SAMPLES" for c in self.device.commands))
        self.assertEqual(Path(self.service.ledger_path).read_bytes(), b"")
        self.assertEqual(len(self.rows()), 0)
        self.service.connect("1002", PASSWORD)
        self.recover()
        state = self.service.snapshot()
        self.assertTrue(state["cleanup_confirmed"])
        self.assertTrue(state["verification"]["verified"])
        self.assertFalse(state["complete"])
        self.assertEqual(state["state"], "incomplete")
        self.assertNotIn("private disk", json.dumps(state))

    def test_owned_cleanup_pause_connect_resumes_never_starts_again(self):
        self.begin(mode="direct")
        self.capture(2)
        self.lose()
        self.device.acquire(4)
        self.service.disconnect()
        state = self.service.snapshot()
        self.assertTrue(state["cleanup_paused"])
        with self.assertRaises(RuntimeError): self.service.reset()
        with self.assertRaises(RuntimeError): self.service.lock(False)
        self.service.connect("1002", PASSWORD)
        self.recover()
        self.assertTrue(self.service.snapshot()["cleanup_confirmed"])
        self.assertEqual(sum(c["cmd"] == "START_DATASET" for c in self.device.commands), 1)
        self.assertEqual(self.service.count, 2)

    def test_ambiguous_pause_resume_uses_transition_seq_without_unpause(self):
        self.begin()
        self.capture(2)
        self.device.transition_fault = "ack_lost"
        state = self.service.pause()
        self.assertTrue(state["recovery_active"])
        self.assertTrue(self.device.paused)
        self.recover()
        self.assertEqual(self.service.snapshot()["state"], "paused")
        self.assertEqual(self.service.snapshot()["transition_seq"], 1)
        self.assertEqual(sum(c["cmd"] == "PAUSE_DATASET" for c in self.device.commands), 1)
        self.assertEqual(sum(c["cmd"] == "CONTINUE_DATASET" for c in self.device.commands), 0)
        self.assertTrue(self.service.stop()["verification"]["verified"])

    def test_ambiguous_pause_terminal_retention_supersedes_pause_and_drains(self):
        self.begin()
        self.device.acquire(4)  # Still queued when Pause control is sent.
        self.device.transition_fault = "ack_lost"
        self.service.pause()
        self.device.terminal("retention_limit")
        self.recover()
        state = self.service.snapshot()
        self.assertTrue(state["verification"]["verified"])
        self.assertFalse(state["complete"])
        self.assertEqual(state["reason"], "retention_limit")
        self.assertEqual(state["count"], 4)

    def test_ambiguous_start_direct_zero_public_rows_is_incomplete_not_complete(self):
        self.configure(mode="direct")
        self.device.start_fault = "ack_lost"
        self.service.start()
        self.device.acquire(3)
        self.recover()
        state = self.service.snapshot()
        self.assertEqual(state["count"], 0)
        self.assertEqual(state["state"], "incomplete")
        self.assertFalse(state["complete"])
        self.assertTrue(state["verification"]["verified"])
        self.assertTrue(state["cleanup_confirmed"])
        self.assertEqual(sum(c["cmd"] == "START_DATASET" for c in self.device.commands), 1)

    def test_model_change_continue_rejected_without_remote_start(self):
        self.begin()
        self.capture(2)
        self.service.stop()
        starts = sum(c["cmd"] == "START_DATASET" for c in self.device.commands)
        self.device.model["scaler_profile_id"] = "changed-scaler"
        with self.assertRaises(RuntimeError): self.service.continue_recording()
        self.assertEqual(sum(c["cmd"] == "START_DATASET" for c in self.device.commands), starts)

    def test_stop_unknown_ack_keeps_one_stop_id_and_verifies_after_resume(self):
        self.begin()
        self.capture(2)
        self.device.stop_fault = "ack_lost"
        state = self.service.stop()
        self.assertFalse(state["verification"]["verified"])
        self.recover()
        self.assertTrue(self.service.snapshot()["verification"]["verified"])
        self.assertEqual(len(set(self.device.stop_ids)), 1)
        self.assertEqual(len(self.device.stop_ids), 2)

    def test_all_rows_verified_beyond_ui_history_limit(self):
        self.begin(prediction=False, optional=False)
        # This case tests bounded history vs full-file verification, not disk
        # durability; other cases execute actual os.fsync on every transaction.
        self.service._fsync = lambda fd: None
        self.capture(7205)
        state = self.service.stop()
        self.assertEqual(len(state["history"]), 7200)
        self.assertEqual(state["count"], 7205)
        self.assertEqual(state["verification"]["count"], 7205)
        self.assertTrue(state["verification"]["verified"])

    def test_formula_or_control_metadata_hello_is_rejected_before_start(self):
        self.service.scan(); self.service.select("1002")
        for value in ("=malicious()", "\tformula", "line\nbreak", "@formula"):
            with self.subTest(value=value):
                self.device.model["profile_id"] = value
                with self.assertRaises(RuntimeError):
                    self.service.connect("1002", PASSWORD)
                self.assertFalse(any(c["cmd"] == "START_DATASET" for c in self.device.commands))

    def test_export_detects_post_verification_external_mutation(self):
        self.begin()
        self.capture(2)
        state = self.service.stop()
        revision = state["revision"]
        with Path(state["csv_path"]).open("a") as stream:
            stream.write("external mutation\n")
        with self.assertRaises(RuntimeError): self.service.export_csv()
        state = self.service.snapshot()
        self.assertFalse(state["verification"]["verified"])
        self.assertFalse(state["complete"])
        self.assertGreater(state["revision"], revision)

    def test_private_close_error_retains_cleanup_until_explicit_retry(self):
        self.begin(mode="direct")
        self.capture(2)
        self.lose()
        stream = self.service._private
        class BadClose:
            def __getattr__(self, name): return getattr(stream, name)
            def close(self):
                stream.close()
                raise OSError("private close failure")
        self.service._private = BadClose()
        self.device.acquire(3)
        self.recover()
        state = self.service.snapshot()
        self.assertTrue(state["cleanup_pending"])
        self.assertTrue(state["cleanup_paused"])
        self.assertFalse(state["cleanup_confirmed"])
        self.assertFalse(state["verification"]["verified"])
        self.service.disconnect()  # A no-op close cannot erase an earlier failed close.
        self.assertTrue(self.service.snapshot()["cleanup_pending"])
        self.service.connect("1002", PASSWORD)
        self.recover()
        state = self.service.snapshot()
        self.assertTrue(state["cleanup_confirmed"])
        self.assertTrue(state["verification"]["verified"])
        self.assertEqual(state["count"], 2)

    def test_public_close_error_never_certifies_csv_success(self):
        self.begin()
        self.capture(2)
        stream = self.service._public
        class BadClose:
            def __getattr__(self, name): return getattr(stream, name)
            def close(self):
                stream.close()
                raise OSError("private close failure")
        self.service._public = BadClose()
        state = self.service.stop()
        self.assertFalse(state["complete"])
        self.assertEqual(state["state"], "incomplete")
        self.assertFalse(state["verification"]["verified"])
        with self.assertRaises(RuntimeError): self.service.export_csv()


from wireless_dataset import FEATURE_ORDER

if __name__ == "__main__":
    unittest.main()
