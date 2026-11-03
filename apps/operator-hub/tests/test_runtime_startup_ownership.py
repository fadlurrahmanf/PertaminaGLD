"""Startup ownership tests: ephemeral sockets only, no device/service actions."""
from __future__ import annotations

import contextlib
import io
import os
import socket
import sys
import unittest
from unittest import mock

from test_child_package_validators import GLD_BRIDGE as gld, load_bridge

hub = load_bridge("startup_ownership_hub", "apps/operator-hub/bridge.py")


class ExclusiveListeners(unittest.TestCase):
    def test_exclusive_listener_rejects_duplicate_then_releases_cleanly(self):
        for module in (gld, hub):
            with self.subTest(app=module.__name__):
                server = module.ExclusiveThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
                address = server.server_address
                try:
                    self.assertFalse(server.allow_reuse_address)
                    with self.assertRaises(OSError):
                        module.ExclusiveThreadingHTTPServer(address, module.Handler)
                    self.assertFalse(hub._port_available(*address))
                    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                        self.assertEqual(server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE), 1)
                        with socket.socket() as duplicate:
                            duplicate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            with self.assertRaises(OSError):
                                duplicate.bind(address)
                finally:
                    server.server_close()
                self.assertTrue(hub._port_available(*address))
                replacement = module.ExclusiveThreadingHTTPServer(address, module.Handler)
                replacement.server_close()

    @unittest.skipUnless(os.name == "nt", "Windows active-address reuse regression")
    def test_old_reuse_listener_cannot_be_shadowed_by_new_exclusive_server(self):
        for module in (gld, hub):
            with self.subTest(app=module.__name__), socket.socket() as old:
                old.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                old.bind(("127.0.0.1", 0))
                old.listen(1)
                address = old.getsockname()
                with self.assertRaises(OSError):
                    module.ExclusiveThreadingHTTPServer(address, module.Handler)
                self.assertFalse(hub._port_available(*address))
                self.assertEqual(old.getsockname(), address)

    def test_gld_bind_failure_happens_before_optional_broker_start(self):
        with (mock.patch.object(sys, "argv", ["bridge.py", "--mqtt-broker-port", "1884"]),
              mock.patch.object(gld, "_register_allowed_origins"),
              mock.patch.object(gld, "ExclusiveThreadingHTTPServer", side_effect=OSError("occupied")),
              mock.patch.object(gld, "LocalMqttBroker") as broker,
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(gld.main(), 2)
        broker.assert_not_called()

    def test_gld_health_identifies_loaded_capability_validator_and_process(self):
        handler = object.__new__(gld.Handler)
        handler.path = "/api/health"
        with (mock.patch.object(handler, "_require_api_access"),
              mock.patch.object(gld, "json_response") as response,
              mock.patch.object(gld, "local_mqtt_broker", None),
              mock.patch.object(gld, "connected_slots_summary", return_value={})):
            handler.do_GET()
        payload = response.call_args.args[1]
        self.assertEqual(payload["processId"], os.getpid())
        self.assertIs(payload["features"]["firmwarePackageCapabilities"], True)
        self.assertEqual(payload["appId"], "gld-operator")


class ChildStartupOwnership(unittest.TestCase):
    def launch(self, health, port_available):
        config = {"gld": hub.CHILD_APPS["gld"]}
        owned = {}
        output = io.StringIO()
        process = mock.Mock(pid=12345)
        process.poll.return_value = None
        with (mock.patch.object(hub, "CHILD_APPS", config),
              mock.patch.object(hub, "child_processes", owned),
              mock.patch.object(hub, "check_health", return_value=health),
              mock.patch.object(hub, "_port_available", return_value=port_available) as probe,
              mock.patch.object(hub, "_python_for", return_value="inert-python"),
              mock.patch.object(hub.subprocess, "Popen", return_value=process) as spawn,
              contextlib.redirect_stdout(output)):
            unavailable = hub.launch_children("127.0.0.1", None)
        return unavailable, owned, spawn, probe, output.getvalue()

    def test_healthy_matching_child_reused_without_spawn_or_shutdown_ownership(self):
        unavailable, owned, spawn, probe, output = self.launch(
            dict(up=True, identityOk=True, processId=23456,
                 features={"firmwarePackageCapabilities": True}), False)
        self.assertEqual(unavailable, [])
        self.assertEqual(owned, {})
        spawn.assert_not_called()
        probe.assert_not_called()
        self.assertIn("HUB_REUSED GLD Operator pid=23456", output)

    def test_older_matching_child_reused_with_explicit_update_notice(self):
        unavailable, owned, spawn, _, output = self.launch(dict(up=True, identityOk=True), False)
        self.assertEqual(unavailable, [])
        self.assertEqual(owned, {})
        spawn.assert_not_called()
        self.assertIn("HUB_REUSED_GLD_UPDATE_REQUIRED", output)

    def test_foreign_and_unresponsive_occupied_ports_never_spawn_competing_child(self):
        for health in (dict(up=True, identityOk=False), dict(up=False, identityOk=False)):
            with self.subTest(health=health):
                unavailable, owned, spawn, _, output = self.launch(health, False)
                self.assertEqual(unavailable, ["gld"])
                self.assertEqual(owned, {})
                spawn.assert_not_called()
                self.assertIn("HUB_CHILD_PORT_CONFLICT", output)

    def test_free_child_is_launched_and_owned(self):
        unavailable, owned, spawn, probe, _ = self.launch(dict(up=False, identityOk=False), True)
        self.assertEqual(unavailable, [])
        self.assertEqual(owned["gld"].pid, 12345)
        probe.assert_called_once_with("127.0.0.1", 5174)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][-2:], ["--port", "5174"])

    def test_exited_new_child_cannot_borrow_old_health_identity(self):
        process = mock.Mock()
        process.poll.return_value = 2
        with (mock.patch.object(hub, "child_processes", {"gld": process}),
              mock.patch.object(hub, "check_health") as health,
              mock.patch.object(hub.time, "monotonic", side_effect=[0, 0, 2]),
              mock.patch.object(hub.time, "sleep")):
            self.assertEqual(hub._wait_for_children_health("127.0.0.1", timeout=1), ["gld"])
        health.assert_not_called()

    def test_owned_gld_readiness_requires_the_launched_process_id(self):
        for reported_pid, expected in ((99999, ["gld"]), (12345, [])):
            process = mock.Mock(pid=12345)
            process.poll.return_value = None
            with (self.subTest(reported_pid=reported_pid),
                  mock.patch.object(hub, "child_processes", {"gld": process}),
                  mock.patch.object(hub, "check_health", return_value=dict(identityOk=True, processId=reported_pid)),
                  mock.patch.object(hub.time, "monotonic", side_effect=[0, 0, 2]),
                  mock.patch.object(hub.time, "sleep")):
                self.assertEqual(hub._wait_for_children_health("127.0.0.1", timeout=1), expected)


if __name__ == "__main__":
    unittest.main()
