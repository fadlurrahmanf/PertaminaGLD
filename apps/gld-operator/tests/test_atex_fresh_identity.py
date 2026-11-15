"""ATEX nonce challenge using in-memory serial doubles only; no COM or network."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("atex_nonce_test_bridge", ROOT / "apps/gld-operator/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class Wire:
    def __init__(self, *, fail=False):
        self.is_open = True
        self.commands = []
        self.sent = threading.Event()
        self.fail = fail
    def write(self, value):
        self.commands.append(value.decode().strip())
        self.sent.set()
        if self.fail: raise OSError("ambiguous write")
    def flush(self): pass
    def close(self): self.is_open = False

class Challenge(unittest.TestCase):
    def setUp(self):
        self.wire = Wire()
        self.serial = bridge.SerialBridge(bridge.EventHub(), slot=1)
        with self.serial._lock:
            self.serial._serial = self.wire
            self.serial.port = "COM999"
            self.serial._telemetry_stream = "stream-one"
        self.results = []
        self.thread = None
    def start(self, timeout=0.4):
        def go():
            try: self.serial.challenge_atex_identity("COM999", "1001", timeout)
            except Exception as exc: self.results.append(exc)
            else: self.results.append("ok")
        self.thread = threading.Thread(target=go, daemon=True)
        self.thread.start()
        self.assertTrue(self.wire.sent.wait(1), "challenge command was not sent")
        self.assertTrue(self.wire.commands[-1].startswith("GET_ATEX_IDENTITY_JSON "))
        nonce = json.loads(self.wire.commands[-1].split(" ",1)[1])["nonce"]
        self.assertRegex(nonce, r"^[0-9a-f]{32}$")
        return nonce
    def emit(self, nonce, *, board="GLD ATEX MotherBoardGLDVer2", device="1001", profile="different-model-before-update"):
        line = "GLD_ATEX_IDENTITY_JSON " + json.dumps(dict(nonce=nonce, boardProfile=board, deviceId=device, modelProfileId=profile, firmwareVersion="0.8.30"))
        self.serial._record_line(line)
    def finish(self):
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive(), "challenge deadlocked")
        self.assertEqual(len(self.results), 1)
        return self.results[0]
    def test_prior_info_and_wrong_nonce_are_ignored_before_correct_reply(self):
        nonce = self.start()
        self.serial._record_line('GLD_INFO_JSON {"boardProfile":"GLD ATEX MotherBoardGLDVer2","deviceId":"1001"}')
        self.emit("0" * 32)
        self.emit(nonce)
        self.assertEqual(self.finish(), "ok")
        self.assertFalse(self.wire.is_open)
        self.assertEqual(len(self.wire.commands),1)
    def test_wrong_nonce_or_no_reply_times_out_and_quarantines_without_retry(self):
        for wrong in (False, True):
            with self.subTest(wrong=wrong):
                self.setUp()
                self.start(timeout=0.12)
                if wrong: self.emit("1"*32)
                result = self.finish()
                self.assertIsInstance(result, RuntimeError)
                self.assertIn("timed out", str(result))
                self.assertTrue(self.serial._poll_gate.is_quarantined())
                self.assertTrue(self.wire.is_open)
                with self.assertRaisesRegex(RuntimeError, "unknown"):
                    self.serial.challenge_atex_identity("COM999", "1001", 0.1)
                with self.assertRaisesRegex(RuntimeError, "unknown"):
                    self.serial.write_line("GET_INFO")
                self.assertEqual(len(self.wire.commands),1)
    def test_invalid_or_mismatched_reply_cannot_disconnect(self):
        for change in ("board", "device", "malformed", "profile_empty", "profile_bad"):
            with self.subTest(change=change):
                self.setUp()
                nonce=self.start()
                if change == "malformed": self.serial._record_line("GLD_ATEX_IDENTITY_JSON {")
                else: self.emit(nonce, board="GLD2" if change=="board" else "GLD ATEX MotherBoardGLDVer2",
                                device="1002" if change=="device" else "1001",
                                profile="" if change=="profile_empty" else "bad\nprofile" if change=="profile_bad" else "existing-model")
                result=self.finish()
                self.assertIsInstance(result, RuntimeError)
                self.assertTrue(self.wire.is_open)
                self.assertEqual(len(self.wire.commands),1)
    def test_version_missing_empty_or_extra_field_rejected(self):
        for kind in ("missing", "empty", "whitespace", "extra"):
            with self.subTest(kind=kind):
                self.setUp()
                nonce = self.start()
                reply = dict(nonce=nonce, boardProfile="GLD ATEX MotherBoardGLDVer2", deviceId="1001", modelProfileId="model", firmwareVersion="0.8.30")
                if kind == "missing": del reply["firmwareVersion"]
                elif kind == "empty": reply["firmwareVersion"] = ""
                elif kind == "whitespace": reply["firmwareVersion"] = "  "
                else: reply["extra"] = 1
                self.serial._record_line("GLD_ATEX_IDENTITY_JSON " + json.dumps(reply))
                self.assertIsInstance(self.finish(), RuntimeError)
                self.assertTrue(self.wire.is_open)

    def test_duplicate_matching_replies_in_same_batch_rejected(self):
        nonce=self.start()
        line="GLD_ATEX_IDENTITY_JSON "+json.dumps(dict(nonce=nonce,boardProfile="GLD ATEX MotherBoardGLDVer2",deviceId="1001",modelProfileId="model",firmwareVersion="0.8.30"))
        with self.serial._lock:
            for _ in range(2):
                self.serial._line_sequence += 1
                self.serial._recent_lines.append(dict(sequence=self.serial._line_sequence,line=line))
        result=self.finish()
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("duplicate",str(result))
        self.assertTrue(self.wire.is_open)
    def test_concurrent_commands_poll_and_external_disconnect_rejected_without_deadlock(self):
        nonce=self.start()
        for call in (lambda:self.serial.write_line("GET_STATUS"),
                     lambda:self.serial.write_line("RESTART"),
                     lambda:self.serial.start_background_poll("x"*16,500,"stream-one"),
                     lambda:self.serial.stop_background_poll("x"*16),
                     lambda:self.serial.disconnect()):
            with self.assertRaisesRegex(RuntimeError, "owns serial"): call()
        self.emit(nonce)
        self.assertEqual(self.finish(), "ok")
        self.assertEqual(len(self.wire.commands),1)
    def test_existing_pending_command_blocks_challenge_before_nonce_write(self):
        self.serial.write_line("GET_INFO")
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.serial.challenge_atex_identity("COM999","1001",0.1)
        self.assertEqual(self.wire.commands,["GET_INFO"])
    def test_same_com_reconnect_changed_stream_rejected(self):
        nonce=self.start()
        with self.serial._lock: self.serial._telemetry_stream = "stream-two"
        self.emit(nonce)
        result=self.finish()
        self.assertIsInstance(result,RuntimeError)
        self.assertIn("connection or ownership changed",str(result))
        self.assertTrue(self.wire.is_open)
    def test_busy_poll_gate_blocks_before_sending(self):
        token = self.serial._poll_gate.reserve("GET_TELEMETRY")
        self.assertIsNotNone(token)
        with self.assertRaisesRegex(RuntimeError,"busy or quarantined"):
            self.serial.challenge_atex_identity("COM999","1001",0.1)
        self.assertEqual(self.wire.commands, [])
        self.serial._poll_gate.cancel_unsent(token)

    def test_competing_existing_write_is_rejected_without_deadlock(self):
        written = threading.Event()
        release = threading.Event()
        original = self.wire.write
        def slow_write(value):
            written.set()
            if not release.wait(1): raise RuntimeError("test timed out")
            original(value)
        self.wire.write = slow_write
        failures = []
        def ordinary():
            try: self.serial.write_line("GET_INFO")
            except Exception as exc: failures.append(exc)
        worker = threading.Thread(target=ordinary, daemon=True)
        worker.start()
        self.assertTrue(written.wait(1))
        try:
            with self.assertRaisesRegex(RuntimeError,"another serial command"):
                self.serial.challenge_atex_identity("COM999","1001",0.1)
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive(), "ordinary writer deadlocked")
        self.assertEqual(failures, [])
        self.assertEqual(self.wire.commands,["GET_INFO"])

    def test_same_com_changes_immediately_before_disconnect(self):
        original = self.serial.disconnect
        def swap(*, _atex_identity_guard=None):
            with self.serial._lock: self.serial._telemetry_stream = "stream-two"
            return original(_atex_identity_guard=_atex_identity_guard)
        self.serial.disconnect = swap
        nonce = self.start()
        self.emit(nonce)
        result = self.finish()
        self.assertIsInstance(result,RuntimeError)
        self.assertIn("before disconnect",str(result))
        self.assertTrue(self.wire.is_open)

    def test_gate_reset_during_challenge_is_rejected(self):
        nonce = self.start()
        self.serial._poll_gate.reset()
        self.emit(nonce)
        result = self.finish()
        self.assertIsInstance(result,RuntimeError)
        self.assertIn("ownership changed",str(result))
        self.assertTrue(self.wire.is_open)

    def test_two_delayed_opens_are_serialized_and_block_challenge(self):
        first_started, first_release = threading.Event(), threading.Event()
        second_started, second_release = threading.Event(), threading.Event()
        class OpenWire(Wire):
            def __init__(self, started, release):
                super().__init__(); self.is_open = False; self.started = started; self.release = release
            def open(self):
                self.started.set()
                if not self.release.wait(2): raise RuntimeError("open fixture timed out")
                self.is_open = True
            def setDTR(self, value): pass
            def setRTS(self, value): pass
            def read(self, count): time.sleep(0.005); return b""
        one, two = OpenWire(first_started, first_release), OpenWire(second_started, second_release)
        wires = iter((one, two)); errors = []
        def open_port():
            try: self.serial.connect("COM999")
            except Exception as exc: errors.append(exc)
        with mock.patch.object(bridge, "serial", type("FakeSerialModule", (), {"Serial": staticmethod(lambda: next(wires))})), \
             mock.patch.object(bridge, "is_flash_port_reserved", return_value=False):
            first = threading.Thread(target=open_port, daemon=True); first.start()
            self.assertTrue(first_started.wait(1))
            second = threading.Thread(target=open_port, daemon=True); second.start()
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                with self.serial._atex_identity_state_lock: count=self.serial._atex_command_writers
                if count>=2: break
                time.sleep(.005)
            self.assertGreaterEqual(count,2, "second connect was not admitted")
            self.assertFalse(second_started.is_set(), "second open bypassed connection lease")
            with self.assertRaisesRegex(RuntimeError,"another serial command"):
                self.serial.challenge_atex_identity("COM999","1001",0.1)
            first_release.set()
            self.assertTrue(second_started.wait(1))
            self.assertFalse(one.is_open, "first handle must close before second opens")
            with self.assertRaisesRegex(RuntimeError,"another serial command"):
                self.serial.challenge_atex_identity("COM999","1001",0.1)
            second_release.set()
            first.join(2); second.join(2)
            self.assertFalse(first.is_alive() or second.is_alive(), "connect deadlocked")
            self.assertEqual(errors, [])
            self.assertTrue(two.is_open)
            self.serial.disconnect()
            self.assertFalse(two.is_open)

    def test_reader_exit_at_guard_detach_boundary_closes_verified_handle(self):
        # Reproduce the old check-then-detach gap by injecting reader exit at
        # the first release of the serial lock. New code detaches in that same
        # critical section; the exit cannot clear the handle before capture.
        raw_lock=self.serial._lock
        outer=self
        class ExitOnRelease:
            fired=False
            def __enter__(self): raw_lock.acquire(); return self
            def __exit__(self, *args):
                raw_lock.release()
                if not self.fired:
                    self.fired=True
                    with raw_lock:
                        if outer.serial._serial is outer.wire:
                            outer.serial._serial=None  # reader exit on current handle
        self.serial._lock=ExitOnRelease()
        with self.serial._atex_identity_state_lock: self.serial._atex_identity_active=True
        name="ATEX_IDENTITY_GUARD_" + "A"*32
        self.assertIsNotNone(self.serial._poll_gate.reserve(name))
        guard=("stream-one","COM999",self.serial._poll_gate.epoch(),"ack:"+name)
        self.serial.disconnect(_atex_identity_guard=guard)
        self.assertTrue(self.serial._lock.fired)
        self.assertFalse(self.wire.is_open, "verified handle was lost before close")

    def test_guard_mismatch_does_not_stop_poller_or_close_handle(self):
        with self.serial._atex_identity_state_lock: self.serial._atex_identity_active=True
        name="ATEX_IDENTITY_GUARD_" + "A"*32
        self.assertIsNotNone(self.serial._poll_gate.reserve(name))
        guard=("wrong-stream","COM999",self.serial._poll_gate.epoch(),"ack:"+name)
        with mock.patch.object(self.serial._poller,"stop_for_disconnect") as stop:
            with self.assertRaisesRegex(RuntimeError,"connection changed before disconnect"):
                self.serial.disconnect(_atex_identity_guard=guard)
            stop.assert_not_called()
        self.assertTrue(self.wire.is_open)

    def test_close_exception_or_still_open_never_confirms_identity(self):
        for mode in ("exception", "still_open"):
            with self.subTest(mode=mode):
                self.setUp()
                def bad_close():
                    if mode == "exception": raise OSError("close failed")
                self.wire.close=bad_close
                nonce=self.start()
                self.emit(nonce)
                result=self.finish()
                self.assertIsInstance(result,RuntimeError)
                self.assertIn("did not close",str(result))
                self.assertTrue(self.wire.is_open)
                self.assertEqual(self.serial._atex_identity_unknown_stream, "stream-one")
                with self.assertRaisesRegex(RuntimeError,"unknown|connect the selected port"):
                    self.serial.challenge_atex_identity("COM999","1001",.1)
                self.assertEqual(len(self.wire.commands),1)

    def test_ambiguous_write_quarantines_and_never_retries(self):
        self.wire.fail=True
        with self.assertRaises(OSError): self.serial.challenge_atex_identity("COM999","1001",0.1)
        self.assertTrue(self.serial._poll_gate.is_quarantined())
        with self.assertRaisesRegex(RuntimeError,"unknown"):
            self.serial.challenge_atex_identity("COM999","1001",0.1)
        self.assertEqual(len(self.wire.commands),1)

if __name__ == "__main__": unittest.main()
