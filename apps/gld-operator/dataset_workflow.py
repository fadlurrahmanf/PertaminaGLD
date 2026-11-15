"""Operator workflow and authoritative two-file Dataset persistence.

Only injected platform actions can scan/join/pick a destination. Existing CSVs
are never overwritten; device samples are ACKed only after both ledgers fsync.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from wireless_dataset import FEATURE_ORDER
from wireless_dataset_replay import _label
from wireless_dataset_workflow import WorkflowCollector
from workflow_credentials import resolve_workflow_password

PREDICTION_FIELDS = ("enabled", "status", "valid", "predicted_class", "gas_class", "confidence", "inference_duration_ms")
BASE_COLUMNS = ("Waktu (ms)", "Label pengujian", *(name + " (V)" for name in FEATURE_ORDER),
    "Predicted Class", "Confidence")
ACTIVE_STATES = {"starting", "recording", "pausing", "continuing", "paused", "recovering", "replaying", "stopping", "stop_pending"}
STATE_NAMES = {"disconnected": "belum_terhubung", "connecting": "menghubungkan", "ready": "siap",
    "not_ready": "belum_siap", "starting": "memulai", "recording": "merekam", "pausing": "menjeda",
    "continuing": "melanjutkan", "paused": "jeda", "recovering": "memulihkan", "replaying": "memulihkan_data",
    "stopping": "menghentikan", "stop_pending": "menunggu_berhenti", "complete": "selesai", "incomplete": "tidak_lengkap", "error": "galat"}

CONNECT_DIAGNOSTICS = {
    "connection_timeout": ("transport", "Layanan data GLD (192.168.4.1:81) tidak menjawab dalam batas waktu. Tunggu boot GLD selesai, lalu coba Connect lagi."),
    "connection_refused": ("transport", "Layanan data GLD pada port 81 menolak koneksi. Pastikan GLD memakai paket Hotspot Wizard Dataset yang sesuai."),
    "network_unreachable": ("transport", "Alamat data GLD tidak terjangkau. Pastikan laptop masih tersambung ke hotspot GLD yang dipilih."),
    "connection_reset": ("transport", "Koneksi data ditutup oleh GLD saat Connect. Tunggu GLD selesai boot, lalu coba lagi."),
    "authentication_rejected": ("authentication", "Autentikasi layanan data GLD ditolak. Pastikan firmware dan password hotspot berasal dari paket GLD yang sesuai."),
    "incompatible_hello": ("protocol", "Protokol GLD tidak sesuai Workspace. Gunakan paket Hotspot Wizard Dataset final dengan protokol 3."),
    "incompatible_capabilities": ("protocol", "Fitur protokol GLD belum sesuai Workspace. Gunakan paket Hotspot Wizard Dataset final yang sesuai model."),
    "invalid_model_metadata": ("protocol", "Metadata model dari GLD tidak valid untuk Workspace. Periksa paket firmware yang diupload."),
    "selected_device_identity_mismatch": ("identity", "Identitas GLD yang menjawab berbeda dari pilihan perangkat. Scan ulang dan pilih GLD yang benar."),
    "invalid_profile": ("readiness", "GLD belum melaporkan profil nulling tersimpan yang valid. Periksa profil nulling melalui COM setelah Disconnect."),
    "device_not_ready": ("readiness", "GLD menjawab, tetapi belum siap merekam. Periksa catu 24 V, sensor ADS/DAC, mode GLD dan profil nulling tersimpan."),
    "retained_session_requires_original_backend": ("ownership", "GLD masih memiliki sesi atau data milik backend sebelumnya. Pulihkan dan selesaikan sesi lewat backend asal sebelum membuat sesi baru."),
    "malformed_message": ("protocol", "Balasan awal layanan data GLD tidak valid. Periksa paket firmware Hotspot Wizard Dataset."),
    "invalid_integer": ("protocol", "Metadata awal layanan data GLD tidak valid. Periksa paket firmware Hotspot Wizard Dataset."),
    "invalid_prefix": ("protocol", "Metadata urutan sesi GLD tidak valid. Koneksi ditahan agar data sesi tetap terlindungi."),
    "wifi_association_failed": ("wifi", "Windows belum berhasil memastikan koneksi ke hotspot GLD. Periksa adaptor, izin lokasi/Wi-Fi, jaringan yang dipilih dan password."),
    "wifi_route_not_ready": ("wifi", "Wi-Fi GLD tersambung, tetapi Windows belum memiliki IP dan rute langsung ke 192.168.4.1. Tunggu beberapa detik lalu Connect lagi; periksa adaptor atau VPN jika tetap gagal."),
    "connection_failed_check_hotspot_and_password": ("transport", "Koneksi ke layanan data GLD gagal. Periksa hotspot GLD dan paket firmware, lalu coba Connect lagi."),
}

DIAGNOSTIC_REASONS = {
    "native_operation_busy": "Perintah Start bertepatan dengan operasi kontrol GLD; perangkat menolak sebelum merekam.",
    "transport_busy": "Antrean kontrol GLD penuh saat Start; perangkat menolak sebelum merekam.",
    "session_or_retained_data_pending": "GLD masih mempunyai sesi atau sampel tertahan dari rekaman sebelumnya.",
    "session_id_reused": "Identitas sesi Start sudah pernah dipakai GLD.",
    "requires_500ms_24v_and_saved_valid_profile": "GLD belum memenuhi interval 500 ms, catu 24 V, atau profil nulling tersimpan yang valid.",
    "prediction_unavailable": "Prediksi yang dipilih belum siap pada GLD.",
    "idempotency_mismatch": "Perintah Start berbeda dari perintah dengan identitas yang sama.",
    "device_rejected_start_dataset": "GLD menolak Start sebelum rekaman dimulai; rincian penolakan tidak tersedia.",
    "explicit_disconnect": "Operator memutus koneksi saat sesi aktif.",
    "transport_lost": "Transport data terputus saat sesi aktif.",
    "reconnect_failed": "Upaya menyambung ulang transport gagal.",
    "sample_silence_resume_required": "Sampel tidak diterima dalam batas waktu; status sesi perlu dikonfirmasi.",
    "radio_fault": "Radio GLD mengalami gangguan; rekaman dihentikan sebagai tidak lengkap dan sampel yang tersimpan tetap dipertahankan.",
    "cutoff_disk_failure": "Pencatatan saat cutoff mengalami kegagalan disk.",
    "disk_failure_before_ack": "Penyimpanan sampel gagal sebelum ACK.",
}


def _safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", value) else "reason_unavailable"


def read_session_diagnostic(ledger_path):
    """Read a sidecar without changing the sample ledger or the recorded CSV."""
    path = Path(ledger_path).with_suffix(".diagnostics.jsonl")
    if not path.is_file():
        return dict(available=False, path=str(path), events=0, last_event=None,
                    message="Catatan diagnostik historis tidak tersedia; penyebab belum diketahui.")
    count, last, malformed = 0, None, 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                last = json.loads(line)
                count += 1
            except json.JSONDecodeError:
                malformed += 1
    return dict(available=bool(count), path=str(path), events=count, last_event=last,
        malformed_lines=malformed,
        message="Sebagian catatan diagnostik tidak dapat dibaca." if malformed else "")


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recent_ledger_lines(path, limit):
    """Read only the newest complete ledger lines, including during an append."""
    found, prefix = [], b""
    with Path(path).open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        complete_tail = True
        if position:
            stream.seek(position - 1)
            complete_tail = stream.read(1) == b"\n"
        while position and len(found) < limit:
            size = min(position, 65536)
            position -= size
            stream.seek(position)
            parts = (stream.read(size) + prefix).split(b"\n")
            prefix = parts[0]
            for line in reversed(parts[1:]):
                if not complete_tail:
                    complete_tail = True
                    continue
                if line.strip():
                    found.append(line.rstrip(b"\r"))
                    if len(found) == limit:
                        break
        if position == 0 and len(found) < limit and complete_tail and prefix.strip():
            found.append(prefix.rstrip(b"\r"))
    return reversed(found)


def csv_columns(fields):
    result = list(BASE_COLUMNS)
    if fields["gain"]:
        result += ["Gain " + name for name in FEATURE_ORDER]
    if fields["status"]:
        result += ["Status " + name for name in FEATURE_ORDER]
    return result


def project_record(record, fields):
    # Only the public projection is compact. The complete raw sample, model,
    # timing and session identities remain in the durable internal ledger.
    result = {"Waktu (ms)": record["timestamp_ms"], "Label pengujian": record["display_label"]}
    result.update({name + " (V)": record["sensor_voltage"][i] for i, name in enumerate(FEATURE_ORDER)})
    prediction = record["prediction"]
    valid = fields["prediction"] and prediction["valid"]
    result.update({"Predicted Class": prediction["predicted_class"] if valid else None,
                   "Confidence": prediction["confidence"] if valid else None})
    for source, field, prefix in (("sensor_gain", "gain", "Gain "), ("sensor_status", "status", "Status ")):
        if fields[field]:
            result.update({prefix + name: record[source][i] for i, name in enumerate(FEATURE_ORDER)})
    return result


class DatasetWorkflowService:
    def __init__(self, output_dir, platform, event_callback=None, websocket_factory=None, *,
                 clock=time.monotonic, fsync=os.fsync, autostart_worker=True,
                 command_timeout=8.0, silence_timeout=3.0,
                 credential_resolver=resolve_workflow_password,
                 wall_clock=lambda: datetime.now(timezone(timedelta(hours=7)))):
        self.output_dir = Path(output_dir).resolve()
        self.platform = platform
        self._callback = event_callback or (lambda event: None)
        self._factory, self._clock, self._fsync = websocket_factory, clock, fsync
        self._automatic, self._timeout, self._silence = autostart_worker, command_timeout, silence_timeout
        self._credential_resolver, self._wall_clock = credential_resolver, wall_clock
        self._lock, self._operation = threading.RLock(), threading.RLock()
        self._engine = None
        self._engine_state = {}
        self._password = None
        self.revision = 0
        self._clear_form()
        self._recent_diagnostic_path = self._find_recent_diagnostic()

    def _find_recent_diagnostic(self):
        if not self.output_dir.is_dir():
            return ""
        latest, latest_mtime = "", -1
        for path in self.output_dir.glob("workflow_*.diagnostics.jsonl"):
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime > latest_mtime:
                latest, latest_mtime = str(path), mtime
        return latest

    def _clear_form(self):
        self.devices = []
        self.selected_device_id = self.selected_ssid = ""
        self.csv_path = self.ledger_path = ""
        self.label, self.mode = "clear_air_test", "direct"
        self.label_timestamp = ""
        self._logical_label_timestamp = None
        self.fields = dict(prediction=False, gain=False, status=False, timing=False)
        self.locked = False
        self._steps = dict.fromkeys(("scan", "device", "connection", "file", "fields", "mode", "label"), False)
        self._steps.update(fields=True, mode=True, label=True)
        self.count = self._segment_id = 0
        self._history = deque(maxlen=7200)
        self._public = self._ledger = self._private = None
        self._private_path = ""
        self._public_offset = self._ledger_offset = self._private_offset = 0
        self._csv_digest, self._ledger_digest = hashlib.sha256(), hashlib.sha256()
        self._columns = []
        self._logical_identity = self._logical_config = None
        self._segment_closed = True
        self._logical_incomplete = self._file_error = False
        self._private_failure = False
        self._continue_invalid = False
        self._cleanup_pending = self._cleanup_paused = self._cleanup_confirmed = False
        self._cleanup_error = ""
        self.verification = dict(verified=False, attempted=False, count=0, matched_count=0, stored_count=0,
            ledger_count=0, sha256="", message="Belum ada rekaman yang diverifikasi.")
        self._complete = False
        self.error = ""
        self.connection_diagnostic = {}
        self._engine_notice_reason = ""
        self.diagnostic_path = self.diagnostic_error = ""
        self._diagnostic_last_state = None
        self._cause_code = self._cause_description = ""
        self._cause_evidence = "unknown"

    def _busy(self):
        return self._cleanup_pending or (self._engine is not None and not self._segment_closed)

    def _readiness(self):
        ready, result = True, {}
        for name, value in self._steps.items():
            if name == "connection" and not self.ledger_path:
                value = value and self._engine_state.get("connected") and self._engine_state.get("ready")
            ready = ready and bool(value)
            result[name] = ready
        return result

    def _display_label(self):
        return f"{self.label_timestamp} {self.label}" if self.label_timestamp else self.label

    def _snapshot(self, history=True):
        engine = self._engine_state
        steps = self._readiness()
        wizard_steps = {name: steps[name] for name in ("connection", "file", "fields", "mode", "label")}
        active_state = engine.get("state", "disconnected")
        state = "incomplete" if self._cleanup_pending else active_state
        if self._segment_closed and self.ledger_path:
            state = "complete" if self._complete and self.verification["verified"] else "incomplete"
        # Treat an old or disconnected report as unknown; the field is
        # informational and never changes Dataset readiness or controls.
        observed, seen = engine.get("radio_auto_tx_observed"), engine.get("radio_auto_tx_seen")
        age = self._clock() - seen if type(seen) in (int, float) else None
        radio_auto_tx = observed if (engine.get("connected") and type(observed) is bool and
            age is not None and 0 <= age <= 30.0) else None
        result = dict(radio_auto_tx=radio_auto_tx, revision=self.revision, devices=copy.deepcopy(self.devices), scanned=self._steps["scan"],
            selected_device_id=self.selected_device_id, selected_ssid=self.selected_ssid,
            device_id=engine.get("device_id", self.selected_device_id),
            boot_id=engine.get("boot_id", ""), session_id=engine.get("session_id", ""),
            nulling_profile_id=engine.get("nulling_profile_id", 0), model=copy.deepcopy(engine.get("model", {})),
            connected=bool(engine.get("connected")), ready=bool(engine.get("ready")),
            prediction_available=bool(engine.get("prediction_available")), locked=self.locked,
            state=state, state_message=STATE_NAMES.get(state, state), csv_path=self.csv_path,
            ledger_path=self.ledger_path, label=self.label, mode=self.mode, fields=copy.deepcopy(self.fields),
            label_timestamp=self.label_timestamp, display_label=self._display_label(),
            configured=all(steps.values()), steps=steps, wizard_steps=wizard_steps, count=self.count,
            configuration_frozen=bool(self.ledger_path),
            segment_id=self._segment_id, verification=copy.deepcopy(self.verification), error=self.error,
            start_rejected=bool(engine.get("start_rejected")),
            start_reject_detail=engine.get("start_reject_detail", ""),
            start_retry_count=engine.get("start_retry_count", 0),
            diagnostic_path=self.diagnostic_path, diagnostic_error=self.diagnostic_error,
            recent_diagnostic_path=self._recent_diagnostic_path if not self.diagnostic_path else "",
            cause=dict(code=self._cause_code, description=self._cause_description,
                       evidence=self._cause_evidence),
            session_closure_status=self._session_closure_status(),
            device_final_total=self._device_final_total(),
            reconciliation_status=self._reconciliation_status(),
            connection_diagnostic=copy.deepcopy(self.connection_diagnostic),
            cleanup_pending=self._cleanup_pending, cleanup_active=self._cleanup_pending and not self._cleanup_paused,
            cleanup_paused=self._cleanup_paused, cleanup_confirmed=self._cleanup_confirmed,
            cleanup_error=self._cleanup_error, cleanup_ledger_path=self._private_path,
            cleanup_next_seq=engine.get("next_seq", 0),
            can_continue=bool(self._segment_closed and self.verification["verified"] and not self._cleanup_pending and
                self.csv_path and self._password and self._logical_identity and not self._file_error and not self._continue_invalid),
            complete=self._complete, paused=bool(engine.get("paused")),
            recovery_active=bool(engine.get("recovery_active")) and not self._cleanup_pending,
            stop_pending=bool(engine.get("stop_requested")) and not engine.get("stop_acknowledged", False),
            next_seq=engine.get("next_seq", 0), replayed_count=engine.get("replayed_count", 0),
            gap_count=engine.get("gap_count", 0), duplicate_count=engine.get("duplicate_count", 0),
            total_samples=engine.get("total_samples", 0), buffered_samples=engine.get("buffered_samples", 0),
            reason=engine.get("terminal_reason", ""), transition_seq=engine.get("transition_seq", 0))
        if history:
            result["history"] = copy.deepcopy(list(self._history))
        return result

    def _device_final_total(self):
        summary = getattr(self._engine, "_summary", None)
        total = summary.get("total_samples") if isinstance(summary, dict) else None
        if type(total) is not int or total < 0:
            return dict(status="unknown", count=None)
        reconciled = (self._segment_closed and not self._cleanup_pending and
            not getattr(self._engine, "_active", True) and getattr(self._engine, "next_seq", None) == total)
        return dict(status="reconciled" if reconciled else "reported", count=total)

    def _session_closure_status(self):
        engine = self._engine
        if not self.ledger_path:
            return "not_started"
        if self._cleanup_pending:
            return "pending"
        if not self._segment_closed:
            return "ongoing"
        if engine is not None and getattr(engine, "start_rejected", False) and self.count == 0:
            return "not_started"
        if self._cleanup_confirmed:
            return "cleanup_confirmed"
        if engine is not None and getattr(engine, "complete", False):
            return "confirmed_normal"
        if (engine is not None and getattr(engine, "_summary", None) is not None and
                getattr(engine, "_terminal_incomplete", False) and not getattr(engine, "_active", True)):
            return "confirmed_incomplete"
        return "unconfirmed"

    def _reconciliation_status(self):
        if self._cleanup_pending:
            return "pending"
        if self._segment_closed and self._engine is not None and getattr(self._engine, "start_rejected", False) and self.count == 0:
            return "not_started"
        if self._cleanup_confirmed:
            return "cleanup_confirmed"
        if self._device_final_total()["status"] == "reconciled":
            return "confirmed"
        if self._segment_closed and self.ledger_path:
            return "unconfirmed"
        return "not_started"

    def _set_cause(self, code, evidence="confirmed_event"):
        if self._cause_code:
            return
        self._cause_code = _safe_code(code)
        self._cause_description = DIAGNOSTIC_REASONS.get(self._cause_code,
            "Kode kejadian tercatat; lihat catatan diagnostik untuk urutannya.")
        self._cause_evidence = evidence

    def _diagnostic_event(self, event, reason=""):
        if not self.diagnostic_path:
            return
        engine, state = self._engine, self._engine_state
        last = next((row for row in reversed(self._history) if row.get("segment_id") == self._segment_id), None)
        summary = getattr(engine, "_summary", None)
        payload = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), event=_safe_code(event),
            reason_code=_safe_code(reason) if reason else "",
            reason_description=(DIAGNOSTIC_REASONS.get(reason,
                "Kode alasan diterima; rincian penyebab fisik tidak tersedia.") if reason else ""),
            device_id=getattr(engine, "device_id", "") or self.selected_device_id,
            boot_id=getattr(engine, "boot_id", ""), session_id=getattr(engine, "session_id", ""),
            segment_id=self._segment_id, mode=self.mode,
            last_saved_seq=last.get("seq") if last else None,
            last_saved_row_id=last.get("row_id") if last else None,
            saved_count=self.count, connected=bool(state.get("connected")),
            engine_state=state.get("state", ""), stop_requested=bool(state.get("stop_requested")),
            stop_acknowledged=bool(state.get("stop_acknowledged")),
            cleanup_pending=self._cleanup_pending, cleanup_confirmed=self._cleanup_confirmed,
            reconciliation_status=self._reconciliation_status(),
            device_final_total=summary.get("total_samples") if isinstance(summary, dict) else None,
            device_final_total_status=self._device_final_total()["status"],
            start_retry_count=state.get("start_retry_count", 0),
            cause_code=self._cause_code, cause_description=self._cause_description,
            cause_evidence=self._cause_evidence,
            verification=copy.deepcopy(self.verification))
        try:
            with Path(self.diagnostic_path).open("a", encoding="utf-8", newline="") as stream:
                stream.write(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
                stream.flush(); self._fsync(stream.fileno())
            self._recent_diagnostic_path = self.diagnostic_path
        except (OSError, TypeError, ValueError) as exc:
            self.diagnostic_error = f"Catatan diagnostik gagal disimpan ({type(exc).__name__}); bukti kejadian ini tidak tersimpan."

    def snapshot(self):
        with self._lock:
            return self._snapshot()

    def _emit(self, sample=None):
        with self._lock:
            self.revision += 1
            payload = dict(type="sample" if sample is not None else "state", **self._snapshot(False))
            if sample is not None:
                payload["sample"] = copy.deepcopy(sample)
        try:
            self._callback(payload)
        except Exception:
            pass

    def _editable(self):
        if self.locked or self._busy():
            raise RuntimeError("Buka kunci setelah sesi selesai sebelum mengubah pengaturan.")

    def scan(self):
        with self._operation:
            self._editable()
            result = self.platform.scan()
            clean = []
            for item in result:
                if not isinstance(item, dict):
                    continue
                match = re.fullmatch(r"GLD-DATASET-([0-9A-Fa-f]{4})", str(item.get("ssid", "")))
                if match and str(item.get("device_id", "")).upper() == match[1].upper():
                    clean.append(dict(ssid=item["ssid"], device_id=match[1].upper(), name="GLD-" + match[1].upper()))
            with self._lock:
                self.devices = clean
                self._steps["scan"] = bool(clean)
                self.error = "" if clean else "Hotspot GLD belum ditemukan."
            self._emit()
            return self.snapshot()

    def select(self, device_id):
        with self._operation:
            self._editable()
            if self._engine_state.get("connected") or self.csv_path:
                raise RuntimeError("Reset pengaturan sebelum memilih perangkat lain.")
            found = next((item for item in self.devices if item["device_id"] == device_id), None)
            if not found or not self._steps["scan"]:
                raise ValueError("Pilih GLD dari hasil pemindaian.")
            with self._lock:
                self.selected_device_id, self.selected_ssid = found["device_id"], found["ssid"]
                self._steps["device"] = True
                self._steps["connection"] = False
            self._emit()
            return self.snapshot()

    def _make_engine(self):
        return WorkflowCollector(self.output_dir, self._on_engine, persist=self._persist,
            cutoff=self._cutoff, expected_device_id=self.selected_device_id, mode=self.mode,
            rejoin_wifi=lambda password: self.platform.join(self.selected_ssid, password),
            websocket_factory=self._factory, clock=self._clock, fsync=self._fsync,
            autostart_worker=self._automatic, command_timeout=self._timeout, silence_timeout=self._silence)

    def connect(self, device_id, password=None):
        if password is None:
            password = self._password or self._credential_resolver()
        if not isinstance(password, str) or not 8 <= len(password) <= 63 or any(not 32 <= ord(x) <= 126 for x in password):
            raise ValueError("Password hotspot harus berisi 8–63 karakter ASCII.")
        with self._operation:
            if device_id != self.selected_device_id or not self._steps["device"]:
                raise ValueError("Pilih GLD yang sama dengan hasil pemindaian.")
            if self._busy() and not (self._cleanup_pending and self._cleanup_paused):
                raise RuntimeError("Sesi masih aktif; tunggu penyelesaian perangkat.")
            if self._engine_state.get("connected"):
                raise RuntimeError("GLD sudah terhubung.")
            phase, failure_code = "wifi", ""
            attempt_engine = None
            self.connection_diagnostic = {}
            try:
                self.platform.join(self.selected_ssid, password)
                phase = "data"
                if self._cleanup_pending:
                    attempt_engine = self._engine
                    self._open_private()
                    self._cleanup_paused = False
                    self._engine.resume_owned(password)
                else:
                    candidate = self._make_engine()
                    attempt_engine = candidate
                    self._engine = candidate
                    candidate.connect(password)
                    if not candidate.ready:
                        # Preserve the controlled readiness/ownership reason
                        # before disconnect emits a disconnected snapshot.
                        failure_code = candidate.error or candidate.terminal_reason or "device_not_ready"
                        candidate.disconnect()
                        raise RuntimeError("not_ready")
                self._password = password
                self._steps["connection"] = True
                self.error = ""
            except Exception as exc:
                code = (getattr(exc, "workflow_code", "wifi_association_failed") if phase == "wifi"
                        else failure_code or getattr(attempt_engine, "error", ""))
                if code not in CONNECT_DIAGNOSTICS:
                    code = "connection_failed_check_hotspot_and_password"
                phase, self.error = CONNECT_DIAGNOSTICS[code]
                self.connection_diagnostic = dict(phase=phase, code=code, message=self.error)
                self._emit()
                raise RuntimeError(self.error) from None
            self._emit()
            return self.snapshot()

    def choose_file(self):
        with self._operation:
            self._editable()
            if self.ledger_path:
                raise RuntimeError("Reset sebelum memilih file rekaman baru.")
            if not self._readiness()["connection"]:
                raise RuntimeError("Hubungkan GLD hingga siap sebelum memilih file CSV.")
            value = self.platform.choose_file()
            if value is None:
                return self.snapshot()
            return self._assign_file(value)

    def choose_default_file(self):
        """Select a fresh CSV in the app's Dataset folder without a native dialog."""
        with self._operation:
            self._editable()
            if self.ledger_path:
                raise RuntimeError("Reset sebelum memilih file rekaman baru.")
            if not self._readiness()["connection"]:
                raise RuntimeError("Hubungkan GLD hingga siap sebelum memilih file CSV.")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = self._wall_clock().strftime("%Y%m%d-%H%M%S")
            value = self.output_dir / f"dataset-GLD-{self.selected_device_id}-{stamp}-{uuid.uuid4().hex[:8]}.csv"
            return self._assign_file(value)

    def _assign_file(self, value):
        value = self.platform.validate_file(value)
        with self._lock:
            self.csv_path = str(value)
            self._steps["file"] = True
            if not self.label_timestamp:
                now = self._wall_clock()
                day = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")[now.weekday()]
                self.label_timestamp = f"{now:%H:%M} {day} {now:%d/%m/%y}"
        self._emit()
        return self.snapshot()

    def configure(self, payload):
        with self._operation:
            self._editable()
            if not isinstance(payload, dict) or set(payload) - {"label", "mode", "fields"}:
                raise ValueError("Pengaturan Dataset tidak valid.")
            label, mode, fields = payload.get("label", self.label), payload.get("mode", self.mode), payload.get("fields", self.fields)
            if label:
                try:
                    _label(label)
                except ValueError:
                    raise ValueError("Label harus 1–31 karakter ASCII dan tidak diawali =, +, -, atau @.") from None
            elif not isinstance(label, str):
                raise ValueError("Label harus berupa teks.")
            if mode not in {"direct", "replay"}:
                raise ValueError("Pilih Rekam langsung atau Pulih otomatis.")
            if (not isinstance(fields, dict) or set(fields) != {"prediction", "gain", "status", "timing"} or
                    any(type(value) is not bool for value in fields.values())):
                raise ValueError("Pilihan kolom harus berupa empat nilai boolean.")
            if self.ledger_path:
                # Unlock/re-lock submits the visible form again. An unchanged
                # configuration must remain usable for Continue, while the
                # existing CSV's schema and label stay immutable.
                if dict(label=label, mode=mode, fields=fields) != self._logical_config:
                    raise RuntimeError("Reset dan pilih file baru sebelum mengubah skema atau label.")
                self._emit()
                return self.snapshot()
            if fields["prediction"] and not self._engine_state.get("prediction_available"):
                raise ValueError("Prediksi belum tersedia untuk model/perangkat ini.")
            with self._lock:
                self.label, self.mode, self.fields = label, mode, dict(fields)
                self._steps.update(label=bool(label), fields=True, mode=True)
            self._emit()
            return self.snapshot()

    def lock(self, locked):
        if type(locked) is not bool:
            raise ValueError("Pilihan kunci harus berupa boolean.")
        with self._operation:
            if not locked and self._busy():
                raise RuntimeError("Pengaturan tetap terkunci selama sesi aktif atau belum terselesaikan.")
            if locked and not all(self._readiness().values()):
                raise RuntimeError("Selesaikan semua langkah pengaturan secara berurutan sebelum mengunci.")
            with self._lock:
                self.locked = locked
            self._emit()
            return self.snapshot()

    def _csv_line(self, values):
        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerow(values)
        return buffer.getvalue()

    def _open_first(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._columns = csv_columns(self.fields)
        self._logical_config = dict(label=self.label, mode=self.mode, fields=dict(self.fields))
        self._logical_label_timestamp = self.label_timestamp
        self._logical_identity = dict(device_id=self._engine.device_id,
            nulling_profile_id=self._engine.nulling_profile_id, model=copy.deepcopy(self._engine.model))
        self.ledger_path = str(self.output_dir / ("workflow_" + uuid.uuid4().hex + ".jsonl"))
        self.diagnostic_path = str(Path(self.ledger_path).with_suffix(".diagnostics.jsonl"))
        self._public = Path(self.csv_path).open("x+", encoding="utf-8", newline="")
        self._ledger = Path(self.ledger_path).open("x+", encoding="utf-8", newline="")
        header = self._csv_line(self._columns)
        self._ledger.flush(); self._fsync(self._ledger.fileno())
        self._public.write(header); self._public.flush(); self._fsync(self._public.fileno())
        self._public_offset, self._ledger_offset = self._public.tell(), self._ledger.tell()
        self._csv_digest.update(header.encode("utf-8"))

    def _open_append(self):
        if not self.verification["verified"] or self._file_error:
            raise RuntimeError("CSV sebelumnya belum terverifikasi.")
        if _hash(self.csv_path) != self._csv_digest.hexdigest() or _hash(self.ledger_path) != self._ledger_digest.hexdigest():
            self.verification.update(verified=False, attempted=False, count=0, matched_count=0,
                stored_count=None, ledger_count=None, sha256="",
                message="CSV atau ledger berubah setelah verifikasi; kecocokan terkini belum diketahui.")
            self._complete = False
            self._set_cause("file_changed_after_verification")
            self._diagnostic_event("file_changed_after_verification")
            self._emit()
            raise RuntimeError("CSV/ledger telah berubah di luar aplikasi; pilih file baru melalui Reset.")
        actual = dict(device_id=self._engine.device_id, nulling_profile_id=self._engine.nulling_profile_id,
            model=copy.deepcopy(self._engine.model))
        if (actual != self._logical_identity or self._logical_config != dict(label=self.label, mode=self.mode, fields=self.fields) or
                self.label_timestamp != self._logical_label_timestamp):
            self._continue_invalid = True
            self._emit()
            raise RuntimeError("Perangkat, profil, model, atau skema tidak cocok untuk Lanjut dalam CSV yang sama.")
        self._public = Path(self.csv_path).open("r+", encoding="utf-8", newline="")
        self._ledger = Path(self.ledger_path).open("r+", encoding="utf-8", newline="")
        self._public.seek(0, 2); self._ledger.seek(0, 2)

    def _start_segment(self, append):
        if not self.locked or not all(self._readiness().values()) or self._busy():
            raise RuntimeError("Kunci semua langkah dan selesaikan sesi sebelumnya sebelum Mulai.")
        previous_start_rejected = bool(append and self.count == 0 and self._engine is not None and
            self._engine.start_rejected)
        if not self._engine_state.get("connected"):
            if not self._password:
                raise RuntimeError("Hubungkan ulang GLD sebelum memulai segmen berikutnya.")
            self._engine = self._make_engine()
            self._engine.connect(self._password)  # Same selected hotspot; no new OS network action.
        if not self._engine.ready:
            raise RuntimeError("GLD belum siap untuk segmen baru.")
        try:
            self._open_append() if append else self._open_first()
        except (OSError, ValueError):
            self._close_public()
            raise RuntimeError("File CSV/ledger belum dapat dibuka dengan aman.") from None
        with self._lock:
            self._segment_id += 1
            self._segment_closed = False
            self._cleanup_pending = self._cleanup_paused = self._cleanup_confirmed = False
            self._cleanup_error = self.error = ""
            if previous_start_rejected:
                # A correlated negative START ACK never opened an acquisition
                # session; it must not poison a later successful Continue.
                self._cause_code = self._cause_description = ""
                self._cause_evidence = "unknown"
            self._complete = False
            self.verification = dict(verified=False, attempted=False, count=self.count, matched_count=0,
                stored_count=self.count, ledger_count=self.count, sha256="",
                message="Rekaman berjalan; belum diverifikasi.")
            self._engine.mode = self.mode
            self._diagnostic_event("segment_started")
        self._engine.start(self.label, prediction_enabled=self.fields["prediction"])
        self._emit()
        return self.snapshot()

    def start(self):
        with self._operation:
            if self.ledger_path:
                raise RuntimeError("Gunakan Lanjut untuk CSV yang sama, atau Reset untuk rekaman baru.")
            return self._start_segment(False)

    def continue_recording(self):
        with self._operation:
            if not self.snapshot()["can_continue"]:
                raise RuntimeError("Lanjut tersedia setelah CSV terverifikasi dan sesi perangkat selesai.")
            return self._start_segment(True)

    def _rollback(self):
        for stream, offset in ((self._ledger, self._ledger_offset), (self._public, self._public_offset)):
            if stream is not None:
                stream.seek(offset); stream.truncate(); stream.flush(); self._fsync(stream.fileno())

    def _persist(self, record, engine):
        with self._lock:
            saved = dict(copy.deepcopy(record), row_id=self.count, segment_id=self._segment_id,
                boot_id=engine.boot_id, model=copy.deepcopy(engine.model),
                label_timestamp=self.label_timestamp, display_label=self._display_label())
            if engine.direct_cutoff:
                saved.update(row_id=None, private_cleanup=True)
            line = json.dumps(saved, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
            if engine.direct_cutoff:
                if self._private is None:
                    raise OSError("private ledger unavailable")
                try:
                    self._private.write(line); self._private.flush(); self._fsync(self._private.fileno())
                    self._private_offset = self._private.tell()
                except OSError:
                    self._private_failure = True
                    try:
                        self._private.seek(self._private_offset); self._private.truncate()
                        self._private.flush(); self._fsync(self._private.fileno())
                    except OSError:
                        self._cleanup_error = "Ledger pembersihan belum dapat dipastikan; tidak ada ACK lanjutan."
                    raise
                return
            projected = project_record(saved, self.fields)
            csv_line = self._csv_line([projected[key] for key in self._columns])
            try:
                self._ledger.write(line); self._ledger.flush(); self._fsync(self._ledger.fileno())
                self._public.write(csv_line); self._public.flush(); self._fsync(self._public.fileno())
            except OSError:
                try:
                    self._rollback()
                except OSError:
                    self._file_error = True
                raise
            self._ledger_offset, self._public_offset = self._ledger.tell(), self._public.tell()
            self._ledger_digest.update(line.encode("utf-8")); self._csv_digest.update(csv_line.encode("utf-8"))
            self.count += 1
            self._history.append(saved)

    def _close_public(self):
        failed = False
        for name in ("_ledger", "_public"):
            stream = getattr(self, name)
            setattr(self, name, None)
            if stream is not None:
                try:
                    stream.flush(); self._fsync(stream.fileno()); stream.close()
                except OSError:
                    failed = self._file_error = True
                    try: stream.close()
                    except OSError: pass
        if failed:
            raise OSError("public ledger close failure")

    def _open_private(self):
        if not self._private_path:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            candidate = self.output_dir / ("cleanup_" + uuid.uuid4().hex + ".jsonl")
            stream = candidate.open("x+", encoding="utf-8", newline="")
            self._private_path, self._private = str(candidate), stream
        elif self._private is None:
            self._private = Path(self._private_path).open("r+", encoding="utf-8", newline="")
            self._private.seek(self._private_offset); self._private.truncate()
        self._private.flush(); self._fsync(self._private.fileno())
        self._private_failure = False

    def _cutoff(self, reason):
        with self._lock:
            self._set_cause(reason)
            self._diagnostic_event("cutoff", reason)
            self._logical_incomplete = self._cleanup_pending = True
            self._cleanup_confirmed = self._complete = False
            self.error = "Rekaman dihentikan sebelum penutupan normal. CSV asli dibekukan; aplikasi menyelesaikan sesi perangkat secara terpisah."
            try:
                self._rollback()
            except OSError:
                self._file_error = True
            try:
                self._close_public()
            except OSError:
                self._file_error = True
            self._open_private()
            self._diagnostic_event("cleanup_started")

    def _verify(self):
        if self._file_error:
            raise RuntimeError("Kondisi file belum dapat dipastikan setelah kegagalan disk.")
        digest_ok = _hash(self.csv_path) == self._csv_digest.hexdigest() and _hash(self.ledger_path) == self._ledger_digest.hexdigest()
        matched = stored = ledger_count = 0
        mismatch = False
        with Path(self.csv_path).open(encoding="utf-8", newline="") as public, Path(self.ledger_path).open(encoding="utf-8") as ledger:
            rows = csv.DictReader(public)
            schema_ok = rows.fieldnames == self._columns
            for row, line in itertools.zip_longest(rows, ledger):
                if row is not None:
                    stored += 1
                if line is not None:
                    ledger_count += 1
                if row is None or line is None or not schema_ok:
                    mismatch = True
                    continue
                try:
                    record = json.loads(line)
                    projected = project_record(record, self.fields)
                    expected = {key: "" if projected[key] is None else str(projected[key]) for key in self._columns}
                    if row == expected and record["row_id"] == stored - 1:
                        matched += 1
                    else:
                        mismatch = True
                except (ValueError, TypeError, KeyError, IndexError):
                    mismatch = True
        valid = digest_ok and schema_ok and not mismatch and stored == ledger_count == self.count
        reason = ("Skema CSV berbeda." if not schema_ok else
            "Jumlah baris CSV dan ledger berbeda." if stored != ledger_count else
            "Isi baris CSV dan ledger berbeda." if mismatch else
            "Jumlah baris tidak sama dengan prefix tersimpan." if stored != self.count else
            "Hash file berubah setelah penyimpanan." if not digest_ok else "")
        message = (f"{matched}/{stored} baris tersimpan terverifikasi terhadap ledger."
                   if valid else f"Verifikasi CSV gagal: {matched}/{stored} baris tersimpan cocok dengan ledger. {reason}")
        self.verification = dict(verified=valid, attempted=True, count=matched, matched_count=matched,
            stored_count=stored, ledger_count=ledger_count, sha256=_hash(self.csv_path) if valid else "",
            message=message)
        self._diagnostic_event("verification_passed" if valid else "verification_failed",
                               "" if valid else "csv_ledger_verification_failed")
        if not valid:
            raise RuntimeError(message)

    def _on_engine(self, event):
        with self._lock:
            self._engine_state = {key: copy.deepcopy(value) for key, value in event.items() if key not in {"history", "sample", "type"}}
            if event.get("type") == "start_retry":
                self._diagnostic_event("start_retry", event.get("start_reject_detail", ""))
            engine = self._engine
            sample = None
            if engine is not None and event.get("type") == "sample" and not engine.direct_cutoff and self._history:
                sample = self._history[-1]
            if engine is not None and engine.direct_cutoff:
                self._cleanup_pending = True
                if not engine._active:
                    reconciled = not self._private_failure and bool(engine.ownership_absent or (engine._summary is not None and
                        engine._stop_acked and not engine.sampling and not engine.paused and
                        engine.next_seq == engine._summary.get("total_samples")))
                    if reconciled:
                        self._cleanup_pending = self._cleanup_paused = False
                        self._cleanup_confirmed = True
                    else:
                        self._cleanup_paused = True
                        self._cleanup_error = "Penyelesaian sesi belum dikonfirmasi. Hubungkan GLD yang sama untuk mencoba lagi."
                    if self._private is not None:
                        try:
                            self._private.flush(); self._fsync(self._private.fileno()); self._private.close()
                        except OSError:
                            self._private_failure = True
                            self._cleanup_pending = self._cleanup_paused = True
                            self._cleanup_confirmed = False
                        finally:
                            self._private = None
            fingerprint = (event.get("state"), event.get("connected"), event.get("error"),
                event.get("terminal_reason"), event.get("stop_requested"),
                event.get("stop_acknowledged"), self._cleanup_pending,
                self._cleanup_confirmed, bool(getattr(engine, "_summary", None)))
            if fingerprint != self._diagnostic_last_state:
                self._diagnostic_last_state = fingerprint
                self._diagnostic_event("state_changed", event.get("terminal_reason") or event.get("error") or "")
            terminal = (engine is not None and engine.session_id and not engine._active and not self._segment_closed and
                (not engine.direct_cutoff or not self._cleanup_pending))
            if terminal:
                self._segment_closed = True
                self._logical_incomplete = self._logical_incomplete or (not engine.complete and
                    not (engine.start_rejected and self.count == 0))
                if not engine.complete and engine.terminal_reason:
                    self._set_cause(engine.start_reject_detail if engine.start_rejected and
                        engine.start_reject_detail not in {"", "unknown"} else engine.terminal_reason,
                        "device_ack" if engine.start_rejected else "device_or_engine_reported")
                    if engine.start_rejected:
                        self._diagnostic_event("start_rejected", engine.start_reject_detail or engine.terminal_reason)
                try:
                    self._close_public()
                    self._verify()
                    self._complete = engine.complete and not self._logical_incomplete
                    if self._complete:
                        self.error = ""
                    elif engine.start_rejected and self.count == 0:
                        self.error = ("GLD menolak Mulai sebelum ada sampel. " + self._cause_description +
                            " Gunakan Continue setelah penyebabnya selesai, atau Reset sesi.")
                    else:
                        self.error = self.verification["message"]
                except (OSError, ValueError, RuntimeError):
                    self._complete = False
                    if self.verification["verified"] or not self.verification["message"].startswith("Verifikasi CSV gagal"):
                        self.verification = dict(verified=False, attempted=True, count=0, matched_count=0,
                            stored_count=None, ledger_count=None, sha256="",
                            message="Verifikasi CSV gagal; kondisi file belum dapat dipastikan. File tetap dipertahankan.")
                    self._set_cause("csv_ledger_verification_failed")
                    self.error = self.verification["message"]
                self._diagnostic_event("segment_closed", engine.terminal_reason or "")
            elif engine is not None and not engine.direct_cutoff:
                notice = "Perangkat belum mengonfirmasi tindakan. Periksa status koneksi dan kesiapan GLD."
                transport_reasons = {"transport_lost", "reconnect_failed", "sample_silence_resume_required"}
                uncertain_reasons = {"start_result_unknown_resume_required", "transition_result_unknown_resume_required",
                    "stop_result_unknown_resume_required", "command_result_unknown_resume_required"}
                if self.error != notice:
                    self._engine_notice_reason = ""
                expected_recovery = (engine.error in transport_reasons and self.mode == "replay" and
                    engine._active and engine.recovery_active and engine.state == "recovering" and
                    engine._start_confirmed and engine._transition_intent is None and engine._stop_intent is None)
                if engine.error and not expected_recovery:
                    if not self.error or self.error == notice and self._engine_notice_reason:
                        self.error = notice
                        self._engine_notice_reason = engine.error if engine.error in transport_reasons | uncertain_reasons else ""
                elif (not engine.error and self._engine_notice_reason and self.error == notice and
                        engine.connected and engine._active and engine._start_confirmed and engine._stream_confirmed and
                        not engine.recovery_active and engine._control is None and engine._transition_intent is None and
                        engine._stop_intent is None and engine.state in {"recording", "paused", "replaying"}):
                    # Only our transient control/transport notice can be removed,
                    # and only after an acknowledged status confirms acquisition.
                    self.error = self._engine_notice_reason = ""
        self._emit(sample)

    def pause(self):
        with self._operation:
            if not self.locked or self._engine is None or self._cleanup_pending:
                raise RuntimeError("Tidak ada rekaman aktif yang dapat dijeda.")
            self._engine.transition(True)
            return self.snapshot()

    def resume(self):
        with self._operation:
            if not self.locked or self._engine is None or self._cleanup_pending:
                raise RuntimeError("Tidak ada sesi jeda yang dapat dilanjutkan.")
            self._engine.transition(False)
            return self.snapshot()

    def stop(self):
        with self._operation:
            if self._engine is None or self._segment_closed:
                raise RuntimeError("Tidak ada rekaman aktif yang dapat dihentikan.")
            if not self._cleanup_pending:
                self._diagnostic_event("stop_requested")
                self._engine.stop()
            return self.snapshot()

    def reset(self):
        with self._operation:
            if self._cleanup_pending:
                raise RuntimeError("Selesaikan sesi perangkat sebelum Reset; CSV tetap tersimpan.")
            if not self._segment_closed:
                if not self._engine_state.get("paused") or self._engine_state.get("transition_pending"):
                    raise RuntimeError("Jeda yang dikonfirmasi atau Hentikan rekaman sebelum Reset.")
                self._engine.stop()
                if not self._segment_closed or not self.verification["verified"]:
                    raise RuntimeError("Reset menunggu STOP dan verifikasi CSV; pengaturan tetap dipertahankan.")
            if self._engine is not None:
                self._diagnostic_event("reset_requested")
                self._engine.disconnect()
            with self._lock:
                self._engine = None
                self._engine_state = {}
                self._password = None
                self._clear_form()
            self._emit()
            return self.snapshot()

    def disconnect(self):
        with self._operation:
            if self.diagnostic_path:
                self._diagnostic_event("disconnect_requested")
            self._password = None
            if self._engine is not None:
                if self._cleanup_pending:
                    self._engine.disconnect()
                    self._cleanup_paused = True
                elif not self._segment_closed:
                    with self._engine._lock:
                        self._engine.mode = "direct"
                        self._engine._loss("explicit_disconnect")
                else:
                    self._engine.disconnect()
            self._steps["connection"] = False
            self._emit()
            return self.snapshot()

    def chart_history(self):
        """Read-only compact history for chart smoothing after a page reload."""
        with self._lock:
            ledger_path = self.ledger_path
        if not ledger_path:
            return dict(ledger_path="", history=[])
        result = []
        try:
            for line in _recent_ledger_lines(ledger_path, 180001):
                try:
                    row = json.loads(line)
                except (UnicodeDecodeError, ValueError):
                    continue  # A concurrent append may expose an unfinished last line.
                if not isinstance(row, dict):
                    continue
                volts = row.get("sensor_voltage")
                if (type(row.get("seq")) is not int or row["seq"] < 0 or
                        type(row.get("timestamp_ms")) is not int or row["timestamp_ms"] < 0 or
                        not isinstance(row.get("session_id"), str) or
                        not isinstance(row.get("boot_id"), str) or
                        not isinstance(volts, list) or len(volts) != 8 or
                        any(type(value) not in (int, float) or not math.isfinite(value) for value in volts)):
                    continue
                result.append(dict(session_id=row["session_id"], boot_id=row["boot_id"],
                    seq=row["seq"], row_id=row.get("row_id"),
                    timestamp_ms=row["timestamp_ms"], sensor_voltage=volts))
        except OSError:
            raise RuntimeError("Riwayat grafik belum dapat dibaca; rekaman tetap berjalan.") from None
        return dict(ledger_path=ledger_path, history=result)

    def export_csv(self):
        with self._lock:
            if not self.csv_path or self._file_error or not Path(self.csv_path).is_file():
                raise RuntimeError("CSV belum tersedia atau kondisinya belum dapat dipastikan.")
            if self._public is not None:
                self._public.flush()
            try:
                if self.verification["verified"] and _hash(self.csv_path) != self.verification["sha256"]:
                    self.verification.update(verified=False, attempted=False, count=0, matched_count=0,
                        stored_count=None, ledger_count=None, sha256="",
                        message="CSV berubah setelah verifikasi; kecocokan terkini belum diketahui.")
                    self._complete = False
                    self._set_cause("file_changed_after_verification")
                    self._diagnostic_event("file_changed_after_verification")
                    self._emit()
                    raise RuntimeError("CSV berubah setelah verifikasi; file tetap dipertahankan.")
                # Keep CRLF bytes identical to the verified file on Windows.
                with Path(self.csv_path).open("r", encoding="utf-8", newline="") as source:
                    return dict(filename=Path(self.csv_path).name, csv=source.read())
            except OSError:
                raise RuntimeError("CSV belum dapat dibaca.") from None
