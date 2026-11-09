"""Protocol 3 acquisition/control engine; persistence is owned by the service.

No OS Wi-Fi, COM or device discovery here. The unchanged protocol2 supervisor
supplies authenticated transport, bounded backoff and cumulative-prefix rules.
"""
from __future__ import annotations

import copy
import errno
import json
import math
import re
import threading
import uuid

from wireless_dataset import CSV_HEADERS, FEATURE_ORDER, VALID_GAINS
from wireless_dataset_replay import (PROTOCOL as PREVIOUS_PROTOCOL, ProtocolError,
    WirelessDatasetReplayCollector, _label, _uint)

PROTOCOL = "gld-dataset-wifi/3"


class WorkflowCollector(WirelessDatasetReplayCollector):
    def __init__(self, output_dir, event_callback=None, *, persist, cutoff,
                 expected_device_id, mode="replay", rejoin_wifi=None, **kwargs):
        super().__init__(output_dir, event_callback, **kwargs)
        self._persist, self._cutoff_callback = persist, cutoff
        self._expected_device_id = expected_device_id
        self._rejoin_wifi = rejoin_wifi
        self.mode = mode
        self.model = {}
        self.prediction_available = self.prediction_enabled = False
        self.paused = False
        self.transition_seq = 0
        self._transition_intent = None
        self._transition_event = threading.Event()
        self._start_attempted = False
        self.start_rejected = self.ownership_absent = self.direct_cutoff = False

    def _open(self, recovering):
        try:
            return super()._open(recovering)
        except Exception as exc:
            # Initial Connect needs a safe actionable diagnosis. Recovery must
            # keep the base supervisor's existing retry/fatal classification.
            if recovering or isinstance(exc, ProtocolError):
                raise
            codes = {getattr(exc, "errno", None), getattr(exc, "winerror", None)}
            if isinstance(exc, TimeoutError) or type(exc).__name__ == "WebSocketTimeoutException" or codes & {errno.ETIMEDOUT, 10060}:
                code = "connection_timeout"
            elif isinstance(exc, ConnectionRefusedError) or codes & {errno.ECONNREFUSED, 10061}:
                code = "connection_refused"
            elif codes & {errno.ENETUNREACH, errno.EHOSTUNREACH, 10051, 10065}:
                code = "network_unreachable"
            elif isinstance(exc, ConnectionResetError) or codes & {errno.ECONNRESET, 10054}:
                code = "connection_reset"
            else:
                raise
            raise ProtocolError(code) from None

    def _snapshot(self, history=True):
        value = super()._snapshot(history)
        value.update(protocol=PROTOCOL, model=copy.deepcopy(self.model),
            prediction_available=self.prediction_available, prediction_enabled=self.prediction_enabled,
            paused=self.paused, transition_seq=self.transition_seq,
            direct_cutoff=self.direct_cutoff, ownership_absent=self.ownership_absent,
            start_rejected=self.start_rejected,
            transition_pending=self._transition_intent is not None)
        return value

    def _hello(self, message, recovering):
        if not isinstance(message, dict) or message.get("protocol") != PROTOCOL:
            raise ProtocolError("incompatible_hello")
        caps, model = message.get("capabilities"), message.get("model")
        if (not isinstance(caps, dict) or any(caps.get(k) is not True for k in
                ("pause", "continue", "durable_replay", "requires_protocol3_client")) or
                type(caps.get("prediction")) is not bool or type(message.get("prediction_ready")) is not bool or
                type(message.get("prediction_enabled")) is not bool or type(message.get("paused")) is not bool or
                message.get("paused") and message.get("sampling")):
            raise ProtocolError("incompatible_capabilities")
        if (not isinstance(model, dict) or any(not isinstance(model.get(k), str) or
                model[k] != "" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/()+ -]{0,127}", model[k]) is None
                for k in ("profile_id", "scaler_profile_id", "runtime_version")) or
                type(model.get("production_approved")) is not bool or
                type(model.get("output_elements")) is not int or not 0 <= model["output_elements"] <= 255 or
                not isinstance(model.get("class_map"), list) or len(model["class_map"]) != model["output_elements"] or
                any(type(x) is not int or not 0 <= x <= 255 for x in model["class_map"])):
            raise ProtocolError("invalid_model_metadata")
        transition = _uint(message.get("transition_seq"))
        translated = dict(message, protocol=PREVIOUS_PROTOCOL)
        # Validate full hello before using a changed boot/empty session to release ownership.
        probe = WirelessDatasetReplayCollector(self.output_dir, autostart_worker=False)
        probe._hello(translated, False)
        if probe.device_id != self._expected_device_id:
            raise ProtocolError("selected_device_identity_mismatch")
        if recovering:
            if (probe.boot_id != self.boot_id or
                    message["session_id"] != self.session_id and not message["sampling"] and
                    not message["paused"] and message["acked_next_seq"] == message["oldest_seq"] == message["total_samples"]):
                self.ownership_absent = True
                raise ProtocolError("owned_session_no_longer_present")
            if model != self.model or message["prediction_enabled"] != self.prediction_enabled:
                raise ProtocolError("model_or_prediction_changed")
            intent = self._transition_intent
            if intent:
                allowed = (intent["seq"] - 1, intent["seq"])
                terminal = message["incomplete"] and not message["sampling"] and not message["paused"]
                if transition not in allowed or (transition == intent["seq"] and
                        message["paused"] != (intent["cmd"] == "PAUSE_DATASET") and not terminal):
                    raise ProtocolError("transition_identity_changed")
            elif transition != self.transition_seq:
                raise ProtocolError("transition_identity_changed")
        super()._hello(translated, recovering)
        self.model = copy.deepcopy(model)
        self.prediction_available = (caps["prediction"] and message["prediction_ready"] and
            model["production_approved"] and model["output_elements"] > 0)
        self.paused, self.transition_seq = message["paused"], transition
        if not recovering:
            self.prediction_enabled = message["prediction_enabled"]
            if self.paused:
                self.ready, self.state, self.error = False, "not_ready", "retained_session_requires_original_backend"

    def _close_file(self):
        # Service closes/verifies its two streams after terminal reconciliation.
        pass

    def _begin_cutoff(self, reason):
        if self.direct_cutoff:
            return
        self.direct_cutoff = True
        self._stop_intent = self._stop_intent or dict(command_id=uuid.uuid4().hex, delivered=False)
        self._cutoff_callback(reason)

    def _loss(self, reason):
        if self._active and self._start_attempted and self.mode == "direct":
            try:
                self._begin_cutoff(reason)
            except OSError:
                return self._fatal("cutoff_disk_failure")
        super()._loss(reason)
        self._transition_event.set()  # The action returns uncertainty, never false confirmation.

    def _fatal(self, reason):
        if reason == "device_rejected_start_dataset":
            self.start_rejected = True
        elif self._active and self._start_attempted and not self.direct_cutoff:
            try:
                self._begin_cutoff(reason)
            except OSError:
                reason = "cutoff_disk_failure"
        super()._fatal(reason)
        self._transition_event.set()

    def _step(self):
        # A WebSocket retry alone cannot recover when Windows has dropped the
        # GLD association. Rejoin the selected SSID before the bounded protocol
        # retry, without holding the collector lock during Windows DHCP.
        with self._lock:
            rejoin = (self._rejoin_wifi is not None and self._active and self._want_link and
                      self._ws is None and self._password is not None and
                      self._clock() >= self._next_retry_at)
            password = self._password if rejoin else None
        if rejoin:
            try:
                self._rejoin_wifi(password)
            except Exception:
                with self._lock:
                    if self._active and self._want_link and self._ws is None:
                        self._loss("reconnect_failed")
                return
        super()._step()

    def start(self, label, interval_ms=500, *, prediction_enabled=False):
        _label(label)
        if type(interval_ms) is not int or interval_ms != 500 or type(prediction_enabled) is not bool:
            raise ValueError("Interval Dataset harus 500 ms dan pilihan prediksi berupa boolean.")
        with self._operation:
            with self._lock:
                if not self.connected or not self.ready or self._active or self._password is None:
                    raise RuntimeError("Hubungkan GLD yang siap sebelum Mulai.")
                if prediction_enabled and not self.prediction_available:
                    raise RuntimeError("Prediksi model belum tersedia; rekaman sensor mentah tetap tersedia.")
                self.session_id, self.label = uuid.uuid4().hex, label
                self.count = self.next_seq = self.gap_count = self.duplicate_count = self.replayed_count = 0
                self.total_samples = self.oldest_seq = self.acked_next_seq = self.buffered_samples = 0
                self.replay_target_seq = self.reconnect_attempt = self.retry_count = 0
                self._history.clear()
                self._summary = self._stop_intent = self._transition_intent = None
                self._stop_acked = self._terminal_incomplete = self.complete = False
                self._start_confirmed = self._stream_confirmed = False
                self._start_event.clear(); self._stop_event.clear()
                self._active, self.sampling, self.paused = True, True, False
                self.prediction_enabled, self.transition_seq = prediction_enabled, 0
                self._outage_started = None
                self.error = self.terminal_reason = ""
                self.state = "starting"
                self._emit()
                self._start_attempted = True
                try:
                    self._send_control("START_DATASET", dict(label=label, sample_interval_ms=500,
                        prediction_enabled=prediction_enabled))
                except Exception:
                    self._loss("start_result_unknown_resume_required")
            self._wait(self._start_event)
            with self._lock:
                if self._active and not self._start_confirmed and self._ws is not None:
                    self._loss("start_result_unknown_resume_required")
                if self.start_rejected:
                    raise RuntimeError("Perangkat menolak Mulai; tidak ada START yang dikirim ulang.")
                return self.snapshot()

    def _send_transition(self):
        intent = self._transition_intent
        self._send_control(intent["cmd"], dict(boot_id=self.boot_id, label=self.label,
            nulling_profile_id=self.nulling_profile_id, transition_seq=intent["seq"]), intent["id"])
        self.state = "pausing" if intent["cmd"] == "PAUSE_DATASET" else "continuing"

    def transition(self, pause):
        with self._operation:
            with self._lock:
                if (not self._active or not self.connected or not self._stream_confirmed or
                        self._control or self._stop_intent or self._transition_intent or self.paused == pause):
                    raise RuntimeError("Tunggu status perangkat sebelum mengubah Jeda/Lanjut.")
                self._transition_intent = dict(cmd="PAUSE_DATASET" if pause else "CONTINUE_DATASET",
                    seq=self.transition_seq + 1, id=uuid.uuid4().hex)
                self._transition_event.clear()
                try:
                    self._send_transition()
                except Exception:
                    self._loss("transition_result_unknown_resume_required")
                self._emit()
            self._wait(self._transition_event)
            return self.snapshot()

    def _status(self, message):
        self._metadata(message)
        paused = message.get("paused")
        transition = _uint(message.get("transition_seq"))
        if (type(paused) is not bool or type(message.get("sampling")) is not bool or
                paused and message["sampling"] or message.get("prediction_enabled") != self.prediction_enabled or
                message.get("state") != ("running" if message["sampling"] else "paused" if paused else "error" if message.get("incomplete") else "stopped")):
            raise ProtocolError("malformed_status")
        total, oldest, acked, buffered = (_uint(message.get(key)) for key in
            ("total_samples", "oldest_seq", "acked_next_seq", "buffered_samples"))
        if (not acked <= oldest <= self.next_seq <= total or total - oldest != buffered or buffered > 640 or
                type(message.get("incomplete")) is not bool):
            raise ProtocolError("invalid_prefix")
        self.total_samples, self.oldest_seq, self.acked_next_seq, self.buffered_samples = total, oldest, acked, buffered
        self.sampling, self.paused = message["sampling"], paused
        # A running heartbeat cannot disguise a stalled acquisition worker.
        if paused or self._control is not None:
            self._last_progress_at = self._clock()
        if message["incomplete"]:
            from wireless_dataset_replay import _reason
            self._terminal_incomplete = True
            self.terminal_reason = _reason(message.get("reason"))
        control, intent = self._control, self._transition_intent
        if intent:
            if transition not in (intent["seq"] - 1, intent["seq"]):
                raise ProtocolError("transition_identity_changed")
        elif transition != self.transition_seq:
            raise ProtocolError("transition_identity_changed")
        if control and control["acked"]:
            command = control["cmd"]
            if command in {"START_DATASET", "RESUME_DATASET"}:
                self._control = None
                self._stream_confirmed = self._start_confirmed = True
                self.recovery_active, self.error = False, ""
                if command == "RESUME_DATASET":
                    self.replay_target_seq = total
                self._start_event.set()
                if intent and transition == intent["seq"]:
                    terminal = message["incomplete"] and not message["sampling"] and not paused
                    if paused != (intent["cmd"] == "PAUSE_DATASET") and not terminal:
                        raise ProtocolError("transition_identity_changed")
                    self._transition_intent = None
                    self._transition_event.set()
                elif intent and not self._stop_intent:
                    self._send_transition()
                if self._stop_intent and not self._stop_acked:
                    self._transition_intent = None
                    self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
            elif command in {"PAUSE_DATASET", "CONTINUE_DATASET"}:
                if not intent or transition != intent["seq"] or paused != (intent["cmd"] == "PAUSE_DATASET"):
                    raise ProtocolError("transition_identity_changed")
                self._control = self._transition_intent = None
                self._transition_event.set()
                if self._stop_intent and not self._stop_acked:
                    self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
        if self._stream_confirmed and self._stop_intent and not self._stop_acked and self._control is None:
            self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
        self.transition_seq = transition
        if self._control:
            self.state = "stopping" if self._control["cmd"] == "STOP_DATASET" else self.state
        else:
            self.state = "paused" if paused else "replaying" if self.next_seq < self.replay_target_seq or not self.sampling else "recording"
        self._emit()

    def _receive(self, message):
        if message.get("type") == "ack":
            control = self._control
            if not control or any(message.get(key) != control[key] for key in ("cmd", "command_id")) or message.get("session_id") != self.session_id:
                return
            if message.get("boot_id") != self.boot_id:
                raise ProtocolError("session_identity_changed")
            if message.get("result") != "ok":
                if control["cmd"] in {"PAUSE_DATASET", "CONTINUE_DATASET"}:
                    self._control = self._transition_intent = None
                    self.error = "device_rejected_transition"
                    self._transition_event.set()
                    if self._stop_intent and not self._stop_acked:
                        self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
                        self.state = "stopping"
                    self._emit()
                    return
                raise ProtocolError("device_rejected_" + control["cmd"].lower())
            _uint(message.get("transition_seq"))
            if type(message.get("paused")) is not bool:
                raise ProtocolError("malformed_ack")
            expected = (self._transition_intent["seq"] if control["cmd"] in
                {"PAUSE_DATASET", "CONTINUE_DATASET"} and self._transition_intent else self.transition_seq)
            if message["transition_seq"] != expected:
                raise ProtocolError("transition_identity_changed")
            control["acked"] = True
            if control["cmd"] == "STOP_DATASET":
                if message["paused"]:
                    raise ProtocolError("malformed_stop_ack")
                self._stop_acked, self.paused, self._control = True, False, None
                self._finish()
            return
        if message.get("type") == "summary" and self.paused:
            raise ProtocolError("terminal_summary_while_paused")
        return super()._receive(message)

    def _record(self, message):
        self._metadata(message)
        if (message.get("device_id") != self.device_id or message.get("label") != self.label or
                message.get("mode") != "DATASET" or message.get("feature_order") != FEATURE_ORDER or
                type(message.get("nulling_profile_id")) is not int or message["nulling_profile_id"] != self.nulling_profile_id):
            raise ProtocolError("invalid_sample_identity")
        seq = _uint(message.get("seq"))
        for key in ("timestamp_ms", "scan_end_ms", "overrun_count"):
            _uint(message.get(key))
        voltage, gains, statuses = (message.get(k) for k in ("sensor_voltage", "sensor_gain", "sensor_status"))
        if (not isinstance(voltage, list) or len(voltage) != 8 or any(type(x) not in (int, float) or not math.isfinite(x) for x in voltage) or
                not isinstance(gains, list) or len(gains) != 8 or any(type(x) is not int or x not in VALID_GAINS for x in gains) or
                not isinstance(statuses, list) or len(statuses) != 8 or any(type(x) is not int or x != 0 for x in statuses)):
            raise ProtocolError("malformed_sample")
        prediction = message.get("prediction")
        if (not isinstance(prediction, dict) or type(prediction.get("enabled")) is not bool or
                prediction["enabled"] != self.prediction_enabled or type(prediction.get("valid")) is not bool or
                prediction.get("status") not in {"disabled", "not_ready", "warmup", "error", "valid"}):
            raise ProtocolError("invalid_prediction")
        _uint(prediction.get("inference_duration_ms"))
        if prediction["valid"]:
            index, confidence = prediction.get("predicted_class"), prediction.get("confidence")
            if (not prediction["enabled"] or prediction["status"] != "valid" or type(index) is not int or
                    not 0 <= index < self.model["output_elements"] or type(prediction.get("gas_class")) is not int or
                    prediction["gas_class"] != self.model["class_map"][index] or
                    type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                raise ProtocolError("invalid_prediction")
        elif (prediction["status"] == "valid" or any(prediction.get(k) is not None for k in ("predicted_class", "gas_class", "confidence")) or
                (not prediction["enabled"] and prediction["status"] != "disabled") or
                (prediction["enabled"] and prediction["status"] == "disabled")):
            raise ProtocolError("invalid_prediction")
        record = {key: copy.deepcopy(message[key]) for key in list(CSV_HEADERS[:9]) +
            ["sensor_voltage", "sensor_gain", "sensor_status", "feature_order", "prediction"]}
        if seq < self.next_seq:
            prior = next((row for row in reversed(self._history) if row["seq"] == seq), None)
            if prior != record:
                raise ProtocolError("duplicate_sample_content_changed")
            self.duplicate_count += 1
        elif seq > self.next_seq:
            self.gap_count += seq - self.next_seq
            raise ProtocolError("noncontiguous_sample")
        else:
            try:
                self._persist(record, self)
            except OSError:
                self._fatal("disk_failure_before_ack")
                return
            self.count += 1
            self.next_seq += 1
            self.total_samples = max(self.total_samples, self.next_seq)
            self.replayed_count += int(seq < self.replay_target_seq)
            self._history.append(record)
            self._last_progress_at = self._clock()
            if self.next_seq >= self.replay_target_seq and self.sampling and not self._stop_intent:
                self.state = "recording"
            self._emit(dict(type="sample", sample=record, **self._snapshot(False)))
        self._send(dict(cmd="ACK_SAMPLES", session_id=self.session_id, boot_id=self.boot_id, next_seq=self.next_seq))

    def resume_owned(self, password):
        with self._lock:
            if not self.direct_cutoff or self.ownership_absent or self.start_rejected:
                raise RuntimeError("Tidak ada pembersihan sesi milik aplikasi yang dapat dilanjutkan.")
            self._password = password
            self._cancel.clear()
            self._active = self._want_link = True
            self._summary = self._control = None
            self._stream_confirmed = False
            super()._loss("owned_cleanup_retry")
            self._next_retry_at = self._clock()
            if self._automatic:
                self._worker_epoch += 1
                self._thread = threading.Thread(target=self._run, args=(self._worker_epoch,), daemon=True,
                    name="gld-workflow-cleanup")
                self._thread.start()
            return self.snapshot()
