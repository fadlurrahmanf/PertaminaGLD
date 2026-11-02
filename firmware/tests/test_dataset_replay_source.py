"""Protocol-2 source/credential gates; no compiler, board or network access.

These checks deliberately do not claim execution of the C++ ring/task state
machine. Compile/native/hardware proof remains a separate approval gate.
"""
from __future__ import annotations
import configparser
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/gld/src/GldDatasetReplayWifi.cpp"
BUFFER = ROOT / "firmware/gld/include/GldDatasetReplayBuffer.h"
STAGE1_HASHES = {
    "firmware/gld/src/GldDatasetWifi.cpp": "8e89bfca18ae8388571a4be4b036505145662c34bd23e973591b585a27270aa1",
    "firmware/gld/include/GldDatasetWifi.h": "3e63befb0d16e3c797922ea407c7ed00e21df8c39c88c5b24263767635b5d227",
    "firmware/tools/prepare_dataset_wifi.py": "bf25b9c82eebf814a23e83b5ed77bfb5614c26cc3b3c14ca3d3d7089f9587a78",
}


def absent_replay(source):
    stack, output = [], []
    for line in source.splitlines(keepends=True):
        directive = line.strip()
        if re.match(r"#\s*(if|ifdef|ifndef)\b", directive):
            feature = "PGL_GLD_DATASET_REPLAY" in directive
            stack.append([feature, not feature])
            if feature:
                continue
        elif directive.startswith("#else") and stack and stack[-1][0]:
            stack[-1][1] = not stack[-1][1]
            continue
        elif directive.startswith("#endif") and stack:
            if stack.pop()[0]:
                continue
        if all(not feature or enabled for feature, enabled in stack):
            output.append(line)
    if stack:
        raise AssertionError("Unbalanced feature guards")
    return "".join(output)


def body(source, signature):
    start = source.index("{", source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class ReplaySourceIsolation(unittest.TestCase):
    def test_stage_one_module_header_and_credentials_are_byte_identical(self):
        for relative, expected in STAGE1_HASHES.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)

    def test_unflagged_and_stage_one_unified_source_is_preserved(self):
        source = (ROOT / "firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
        selected = absent_replay(source)
        meaningful = "\n".join(line for line in selected.splitlines() if line.strip())
        self.assertEqual(hashlib.sha256(meaningful.encode()).hexdigest(),
                         "e073c2c51df93279bebf8b2dbc2e75e48ea4840d9fecb46b4810557d3d7a261e")

    def test_existing_environment_flags_and_three_new_inheritance_boundaries(self):
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read(ROOT / "firmware/platformio.ini", encoding="utf-8")
        new = {f"env:gld_model_{model}_dataset_replay_wifi" for model in (1, 2, 3)}
        old = {name: dict(config[name]) for name in config.sections() if name not in new}
        digest = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "49b55f0d741884de698f2e5af6f48f26c58c53e3676f3a551444db858437a0cf")
        enabled = {name for name in config.sections()
                   if "-DPGL_GLD_DATASET_REPLAY=1" in config[name].get("build_flags", "")}
        self.assertEqual(enabled, new)
        for model in (1, 2, 3):
            env = config[f"env:gld_model_{model}_dataset_replay_wifi"]
            self.assertEqual(env["extends"], f"env:gld_model_{model}_dataset_wifi")
            self.assertEqual(env["extra_scripts"], "pre:tools/prepare_dataset_replay_wifi.py")
            self.assertIn("-<gld/src/GldDatasetWifi.cpp>", env["build_src_filter"])
            self.assertIn("+<gld/src/GldDatasetReplayWifi.cpp>", env["build_src_filter"])

    def test_existing_packages_are_not_modified(self):
        packages = ROOT / "apps/operator-hub/firmware-packages"
        digest = hashlib.sha256()
        count = 0
        for path in sorted(packages.rglob("*")):
            if path.is_file() and not any("dataset_replay_wifi" in part for part in path.relative_to(packages).parts):
                digest.update(path.relative_to(packages).as_posix().encode())
                digest.update(b"\0")
                digest.update(hashlib.sha256(path.read_bytes()).digest())
                digest.update(b"\n")
                count += 1
        self.assertEqual(count, 184)
        self.assertEqual(digest.hexdigest(), "6009a9dc7f27f83a22ce7c4989a95fc0daf1bae09c84b57cea637f8e253ea8c3")


class ReplayOwnershipAndBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.buffer = BUFFER.read_text(encoding="utf-8")

    def test_compact_capacity_window_and_static_memory_budget(self):
        for token in ("REPLAY_CAPACITY = 640", "REPLAY_RETENTION_MS = 300000", "REPLAY_WINDOW = 8",
                      "sizeof(RetainedSample) == 64", "RetainedSample records_[REPLAY_CAPACITY]"):
            self.assertIn(token, self.buffer)
        self.assertNotIn("Json", self.buffer)
        class Sample(ctypes.Structure):
            _fields_ = [("v", ctypes.c_float * 8), ("g", ctypes.c_uint8 * 8),
                        ("s", ctypes.c_uint8 * 8), ("a", ctypes.c_uint32), ("b", ctypes.c_uint32)]
        class Record(ctypes.Structure):
            _fields_ = [("sample", Sample), ("seq", ctypes.c_uint32), ("overrun", ctypes.c_uint32)]
        self.assertEqual(ctypes.sizeof(Record) * 640, 40960)

    def test_sampler_has_no_transport_gate_and_no_network_or_json(self):
        sampler = body(self.source, "void sampler(void*)")
        self.assertNotRegex(sampler, r"socket\.|WiFi\.|mqtt\.|Json|state\.client|streamEnabled")
        self.assertIn("retained.append(sample, state.overruns)", sampler)
        self.assertLess(sampler.index("checkLimitLocked(millis())"), sampler.index("captureSample(sample)"))
        self.assertLess(sampler.index("checkLimitLocked(sample.scanEndMs)"), sampler.index("retained.append("))

    def test_only_ack_or_resume_release_and_no_disconnect_clears_ring(self):
        sender = body(self.source, "void transmitter(void*)")
        disconnected = body(self.source, "void disconnected(int client)")
        for text in (sender, disconnected):
            self.assertNotIn("retained.acknowledgePrefix", text)
            self.assertNotIn("retained.clear", text)
        self.assertEqual(self.source.count("retained.acknowledgePrefix("), 2)
        self.assertEqual(self.source.count("retained.clear()"), 1)
        self.assertIn("if (full() || next_ == UINT32_MAX) return false", self.buffer)

    def test_control_fifo_and_sample_selection_share_one_guard(self):
        sender = body(self.source, "void transmitter(void*)")
        selection = body(sender, "bool available = false;")
        self.assertIn("Lock lock;", selection)
        self.assertIn("xQueueReceive(controls, &wire, 0)", selection)
        self.assertIn("sampleMessageLocked(wire, sequence)", selection)
        self.assertLess(selection.index("Lock lock;"), selection.index("xQueueReceive(controls"))
        self.assertLess(selection.index("xQueueReceive(controls"), selection.index("sampleMessageLocked"))

    def test_ack_identity_offered_frontier_and_duplicate_progress(self):
        ack = body(self.source, "bool acknowledgeLocked(const Command& command)")
        for token in ("command.bootId, state.boot", "command.sessionId, state.session",
                      "command.nextSequence > state.offeredNext", "retained.nextSequence()"):
            self.assertIn(token, ack)
        self.assertLess(ack.index("<= retained.acknowledgedNext()) return true"), ack.index("ackClock.progress"))
        receiver = body(self.source, "void websocket(uint8_t client")
        self.assertLess(receiver.index("if (ack)"), receiver.index("xQueueSend(commands"))
        self.assertIn("state.client == client && acknowledgeLocked(command)", receiver)

    def test_exact_retention_boundary_and_sticky_terminal_reason(self):
        self.assertIn("static_cast<uint32_t>(now - since_) >= REPLAY_RETENTION_MS", self.buffer)
        process = body(self.source, "void process(const Command& command)")
        self.assertLess(process.index("checkLimitLocked(millis())"), process.index('"RESUME_DATASET"'))
        stop = body(self.source, "void stopLocked(const char* reason, bool incomplete)")
        self.assertIn("if (!state.incomplete) copy(state.reason, reason)", stop)
        self.assertIn("state.incomplete = state.incomplete || incomplete", stop)
        stop_command = process.split('"STOP_DATASET"', 1)[1]
        self.assertNotIn("state.incomplete = false", stop_command)

    def test_summary_requires_stopped_acknowledged_empty_buffer(self):
        poll = body(self.source, "void poll()")
        for token in ("!state.sampling", "state.summaryPending", "retained.size() == 0",
                      "retained.acknowledgedNext() == retained.nextSequence()"):
            self.assertIn(token, poll)
        self.assertIn("if (wire.summary) state.summarySent = true", self.source)
        self.assertIn("state.session[0] && !state.sampling) state.summaryPending = true", self.source)

    def test_start_stop_idempotence_and_resume_label_and_prefix(self):
        process = body(self.source, "void process(const Command& command)")
        self.assertLess(process.index("state.startCommand, command.commandId"), process.index("retained.clear()"))
        for token in ("strcmp(command.label, state.label)", "retained.prefixAvailable(command.nextSequence)",
                      '"stop_already_registered"', "state.stopCommand, command.commandId"):
            self.assertIn(token, process)
        resume = process.split('"RESUME_DATASET"', 1)[1].split('"STOP_DATASET"', 1)[0]
        self.assertLess(resume.index("ackLocked(command, true"), resume.index("statusLocked()"))
        self.assertIn("next >= acknowledged_ && next <= next_", self.buffer)

    def test_listener_startup_is_checked_and_no_credentials_are_logged(self):
        for token in ("static_cast<bool>(*_server)", "socket.beginChecked()", "failStartup(); return false",
                      "vTaskDelete(samplerHandle)", "vQueueDelete(controls)", "WiFi.persistent(false)",
                      'socket.setAuthorization("gld", password)', "esp_fill_random(random, sizeof(random))"):
            self.assertIn(token, self.source)
        self.assertNotRegex(self.source, r"Serial\.|logPrintf\(|printf\(.*password|Preferences")


class ReplayPrivateCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("replay_credentials", ROOT / "firmware/tools/prepare_dataset_replay_wifi.py")
        cls.preparer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.preparer)

    def test_all_three_credentials_are_separate_stable_and_protocol_two(self):
        with tempfile.TemporaryDirectory(prefix="gld-replay-credentials-test-") as directory:
            project = Path(directory).resolve()
            values = []
            for name in sorted(self.preparer.ENVIRONMENTS):
                build = project / ".pio/build" / name
                include = self.preparer.prepare(project, build, name)
                credential = project / ".pio/gld-dataset-replay-wifi" / name / "credentials.local.json"
                raw = credential.read_bytes()
                data = json.loads(raw)
                self.assertEqual(data["protocol"], "gld-dataset-wifi/2")
                self.assertEqual(data["username"], "gld")
                self.assertTrue(24 <= len(data["password"]) <= 63, "Invalid private password length")
                values.append(data["password"])
                header = (include / "GldDatasetReplayWifiSecrets.h").read_text()
                self.assertTrue(json.dumps(data["password"]) in header, "Private header mismatch")
                self.preparer.prepare(project, build, name)
                self.assertTrue(raw == credential.read_bytes(), "Unexpected credential rotation")
            self.assertEqual(len(set(values)), 3, "Replay variants share a private password")
            self.assertFalse((project / ".pio/gld-dataset-wifi").exists())

    def test_stage_one_target_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix="gld-replay-credentials-test-") as directory:
            project = Path(directory)
            with self.assertRaises(ValueError):
                self.preparer.prepare(project, project / "build", "gld_model_1_dataset_wifi")
            self.assertFalse((project / ".pio").exists())

    def test_existing_wrong_protocol_or_corruption_never_silently_rotates(self):
        with tempfile.TemporaryDirectory(prefix="gld-replay-credentials-test-") as directory:
            project = Path(directory)
            name = "gld_model_1_dataset_replay_wifi"
            credential = project / ".pio/gld-dataset-replay-wifi" / name / "credentials.local.json"
            credential.parent.mkdir(parents=True)
            credential.write_text(json.dumps(dict(environment=name, username="gld", protocol="gld-dataset-wifi/1",
                                                 password="invalid-private-placeholder")))
            before = credential.read_bytes()
            with self.assertRaises(ValueError):
                self.preparer.prepare(project, project / "build", name)
            self.assertTrue(before == credential.read_bytes(), "Invalid credential was overwritten")


if __name__ == "__main__":
    unittest.main()
