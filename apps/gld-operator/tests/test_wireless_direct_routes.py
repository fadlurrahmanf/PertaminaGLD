"""Direct-mode compatibility dispatch and cleanup admission; inert HTTP fakes."""
import unittest
from unittest.mock import patch

from test_wireless_replay_routes import bridge, MemoryHandler, FakeCollector, ORIGIN


class DirectCompatibilityRoutes(unittest.TestCase):
    def setUp(self):
        self.direct = FakeCollector('gld-dataset-wifi/2')
        self.replay = FakeCollector('gld-dataset-wifi/2')
        for current in (
            patch.object(bridge, 'BRIDGE_ALLOWED_ORIGINS', {ORIGIN}),
            patch.object(bridge, 'serial_bridges', {}),
            patch.object(bridge, 'wireless_dataset_collector', self.direct),
            patch.object(bridge, 'wireless_replay_collector', self.replay),
            patch.object(bridge, 'get_wireless_dataset_collector', return_value=self.direct),
            patch.object(bridge, 'get_wireless_replay_collector', return_value=self.replay),
        ):
            current.start()
            self.addCleanup(current.stop)

    def request(self, path, payload=None):
        return MemoryHandler(path, payload).execute()

    def test_existing_direct_routes_accept_protocol_two_without_replay_dispatch(self):
        code, value = self.request('/api/wireless-dataset/connect', {'password': 'fixture-only'})
        self.assertEqual(code, 200)
        self.assertEqual(value['protocol'], 'gld-dataset-wifi/2')
        self.assertEqual(self.replay.calls, [])
        self.assertEqual(self.direct.calls, [('connect', 'fixture-only')])

    def test_cleanup_blocks_other_mode_and_device_entry_points_even_if_transport_is_closed(self):
        self.direct.value.update(state='incomplete', connected=False, recovery_active=False,
                                 cleanup_pending=True)
        with (patch.object(bridge, 'probe_port') as probe,
              patch.object(bridge, 'firmware_upload') as upload,
              patch.object(bridge, 'get_serial_bridge') as serial):
            for path, body in (
                ('/api/wireless-replay/connect', {'password': 'fixture-only'}),
                ('/api/serial/connect', {'port': 'COM999'}),
                ('/api/serial/port-status?port=COM999', None),
                ('/api/firmware/upload', {'port': 'COM999'}),
            ):
                with self.subTest(path=path):
                    self.assertGreaterEqual(self.request(path, body)[0], 400)
            probe.assert_not_called()
            upload.assert_not_called()
            serial.assert_not_called()
            self.assertEqual(self.replay.calls, [])

    def test_cleanup_finished_releases_other_wireless_mode(self):
        self.direct.value.update(state='incomplete', connected=False, recovery_active=False,
                                 cleanup_pending=False)
        self.assertEqual(self.request('/api/wireless-replay/connect', {'password': 'fixture-only'})[0], 200)
        self.assertEqual(len(self.replay.calls), 1)

    def test_disconnected_idle_snapshot_does_not_keep_completed_stop_lock(self):
        # Replay retains its completed Stop intent across reconnect. Disconnect
        # before a new Start must release admission even if its state is ready.
        for state in ('ready', 'not_ready'):
            with self.subTest(state=state):
                self.replay.value.update(state=state, connected=False, recovery_active=False,
                                         stop_requested=True, sampling=False)
                self.assertFalse(bridge.wireless_collector_in_use(self.replay))
                self.assertEqual(self.request('/api/wireless-dataset/connect', {'password': 'fixture-only'})[0], 200)
                self.replay.value['connected'] = True
                self.assertTrue(bridge.wireless_collector_in_use(self.replay))

    def test_compatibility_collector_keeps_direct_sse_namespace(self):
        # The getter patched in setUp is bypassed only for lazy construction.
        from test_wireless_replay_routes import APP
        import importlib.util
        spec = importlib.util.spec_from_file_location('direct_factory_bridge', APP / 'bridge.py')
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        with (patch.object(fresh, 'wireless_dataset_collector', None),
              patch.object(fresh, 'WirelessDatasetDirectCollector', return_value=self.direct) as factory,
              patch.object(fresh.events, 'emit') as emit):
            self.assertIs(fresh.get_wireless_dataset_collector(), self.direct)
            self.assertIs(fresh.get_wireless_dataset_collector(), self.direct)
            factory.assert_called_once()
            payload = {'type': 'state', 'state': 'stop_pending', 'cleanup_pending': True}
            factory.call_args.args[1](payload)
            emit.assert_called_once_with('wireless_dataset', payload)


if __name__ == '__main__':
    unittest.main()
