"""Actual initial Connect diagnostics with inert WLAN/socket fixtures."""
import errno
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataset_workflow import DatasetWorkflowService
from wireless_dataset_replay import ProtocolError
from test_dataset_workflow import Device, Platform, PASSWORD
from test_wireless_dataset_replay import Clock

SECRET = "fixture-private-header-password-must-not-appear"


class WorkflowConnectDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.device = Device(self.clock)
        self.platform = Platform(self.temp.name)
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    def service(self, factory=None):
        service = DatasetWorkflowService(Path(self.temp.name) / "private", self.platform, self.events.append,
            websocket_factory=factory or self.device.factory, clock=self.clock, autostart_worker=False)
        service.scan(); service.select("1002")
        return service

    def refused(self, service, code, phase):
        with self.assertRaises(RuntimeError) as failure:
            service.connect("1002", PASSWORD)
        snapshot = service.snapshot()
        diagnostic = snapshot["connection_diagnostic"]
        self.assertEqual((diagnostic["code"], diagnostic["phase"]), (code, phase))
        self.assertEqual(str(failure.exception), diagnostic["message"])
        self.assertEqual(snapshot["error"], diagnostic["message"])
        self.assertFalse(snapshot["ready"])
        self.assertFalse(snapshot["steps"]["connection"])
        self.assertEqual(snapshot["count"], 0)
        self.assertFalse(snapshot["csv_path"])
        self.assertEqual(self.device.commands, [])
        self.assertNotIn(SECRET, json.dumps([snapshot, self.events, str(failure.exception)]))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        if service._engine:
            service._engine.disconnect()

    def test_initial_timeout_refused_unreachable_and_reset_have_specific_safe_codes(self):
        websocket_timeout = type("WebSocketTimeoutException", (Exception,), {})
        for error, code in ((TimeoutError(SECRET), "connection_timeout"),
                            (websocket_timeout(SECRET), "connection_timeout"),
                            (ConnectionRefusedError(SECRET), "connection_refused"),
                            (OSError(10061, SECRET), "connection_refused"),
                            (OSError(errno.EHOSTUNREACH, SECRET), "network_unreachable"),
                            (ConnectionResetError(SECRET), "connection_reset")):
            def factory(*_args, **_kwargs):
                raise error
            with self.subTest(error=type(error).__name__, code=code):
                self.events.clear()
                self.refused(self.service(factory), code, "transport")

    def test_hello_read_timeout_is_classified_and_socket_closed(self):
        peer = SimpleNamespace(settimeout=lambda _:None, closed=False)
        def close(): peer.closed = True
        def recv(): raise TimeoutError(SECRET)
        peer.close, peer.recv = close, recv
        self.refused(self.service(lambda *_args, **_kwargs:peer), "connection_timeout", "transport")
        self.assertTrue(peer.closed)

    def test_authentication_rejection_and_unknown_exception_do_not_leak_details(self):
        auth = type("Rejected", (Exception,), {"status_code":401})
        for error, code, phase in ((auth(SECRET), "authentication_rejected", "authentication"),
                                    (RuntimeError(SECRET), "connection_failed_check_hotspot_and_password", "transport")):
            def factory(*_args, **_kwargs): raise error
            with self.subTest(code=code):
                self.events.clear()
                self.refused(self.service(factory), code, phase)

    def test_windows_join_failure_has_wifi_phase_without_reflecting_exception(self):
        def join(*_args): raise RuntimeError(SECRET)
        self.platform.join = join
        self.refused(self.service(), "wifi_association_failed", "wifi")

    def test_associated_without_route_has_specific_safe_message(self):
        class MissingRoute(RuntimeError):
            workflow_code = "wifi_route_not_ready"
        def join(*_args): raise MissingRoute(SECRET)
        self.platform.join = join
        self.refused(self.service(), "wifi_route_not_ready", "wifi")

    def test_not_ready_profile_zero_identity_and_retained_session_remain_refused(self):
        for case, code, phase in (("not_ready", "device_not_ready", "readiness"),
                                  ("profile_zero", "invalid_profile", "readiness"),
                                  ("wrong_identity", "selected_device_identity_mismatch", "identity"),
                                  ("retained", "retained_session_requires_original_backend", "ownership"),
                                  ("paused", "retained_session_requires_original_backend", "ownership")):
            self.device = Device(self.clock)
            if case == "not_ready": self.device.ready = False
            if case == "profile_zero": self.device.profile = 0; self.device.ready = False
            if case == "wrong_identity": self.device.device_id = "1003"
            if case == "retained": self.device.sampling = True; self.device.sid = "previous-owner"
            if case == "paused": self.device.paused = True; self.device.sid = "previous-owner"
            with self.subTest(case=case):
                self.events.clear()
                self.refused(self.service(), code, phase)

    def test_malformed_hello_is_protocol_failure_without_raw_payload(self):
        peer = SimpleNamespace(recv=lambda: SECRET, settimeout=lambda _:None, close=lambda:None)
        self.refused(self.service(lambda *_args, **_kwargs:peer), "malformed_message", "protocol")

    def test_wrong_protocol_and_invalid_model_have_specific_safe_diagnostics(self):
        for code in ("incompatible_hello", "invalid_model_metadata"):
            self.device = Device(self.clock)
            original = self.device.hello
            def hello():
                message = original()
                if code == "incompatible_hello": message["protocol"] = "gld-dataset-wifi/2"
                else: message["model"]["runtime_version"] = "\n" + SECRET
                return message
            self.device.hello = hello
            with self.subTest(code=code):
                self.events.clear()
                self.refused(self.service(), code, "protocol")

    def test_failed_engine_creation_cannot_reuse_a_previous_attempts_error(self):
        service = self.service()
        service._engine = SimpleNamespace(error="authentication_rejected")
        def fail(): raise RuntimeError(SECRET)
        service._make_engine = fail
        with self.assertRaises(RuntimeError): service.connect("1002", PASSWORD)
        self.assertEqual(service.snapshot()["connection_diagnostic"]["code"],
                         "connection_failed_check_hotspot_and_password")
        self.assertNotIn(SECRET, json.dumps(service.snapshot()))

    def test_unapproved_prediction_still_allows_raw_connect_and_clears_diagnostic(self):
        service = self.service()
        self.device.ready = False
        self.refused(service, "device_not_ready", "readiness")
        self.device.ready = True
        self.device.model["production_approved"] = False
        self.device.prediction_ready = False
        snapshot = service.connect("1002", PASSWORD)
        self.assertTrue(snapshot["ready"])
        self.assertFalse(snapshot["prediction_available"])
        self.assertEqual(snapshot["connection_diagnostic"], {})
        self.assertEqual(snapshot["error"], "")
        service.disconnect()

    def test_recovery_transport_exceptions_remain_retryable_original_types(self):
        for error in (TimeoutError(SECRET), ConnectionRefusedError(SECRET), OSError(errno.EHOSTUNREACH, SECRET)):
            def factory(*_args, **_kwargs): raise error
            service = self.service(factory)
            collector = service._make_engine()
            collector._password = PASSWORD
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)) as failure:
                collector._open(True)
            self.assertIs(failure.exception, error)
            self.assertNotIsInstance(failure.exception, ProtocolError)


if __name__ == "__main__":
    unittest.main()
