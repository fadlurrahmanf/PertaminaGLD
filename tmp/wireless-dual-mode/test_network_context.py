"""No OS/network operations: fake System verifies restoration on failure/cancel."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('dual_network', Path(__file__).with_name('network_context.py'))
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class Fake:
    def __init__(self, failure=None):
        self.events, self.failure = [], failure
    def arm_watchdog(self, path):
        self.events.append(('arm', str(path)))
        return 99
    def add_profile(self, path, interface):
        self.events.append(('add', interface))
    def connect_profile(self, profile, interface):
        self.events.append(('connect', profile, interface))
    def wait_wifi(self, interface, **options):
        self.events.append(('wait', options['profile']))
        if self.failure == 'restore' and options['profile'] == 'Internet & café':
            raise mod.Failure('injected_restore_failure')
        return dict(name=interface, profile=options['profile'], ssid=options['ssid'])
    def probe(self, interface, observe):
        self.events.append(('probe', interface))
        observe({'tcp_reachable': False})
        if self.failure == 'probe':
            raise mod.Failure('injected_probe_failure')
    def remove_profile(self, name, interface):
        self.events.append(('delete', name, interface))


class SafetyTests(unittest.TestCase):
    def make(self, system, output):
        return mod.WifiVisit(system, output, dict(name='Wi-Fi', profile='Internet & café',
            ssid='Original'), '1002', 'dummy-test-only')
    def test_watchdog_precedes_any_mutation_and_exact_alias_removed(self):
        with tempfile.TemporaryDirectory() as output:
            system = Fake()
            visit = self.make(system, output)
            visit.join()
            result = visit.close()
            self.assertEqual(system.events[0][0], 'arm')
            self.assertTrue(result['verified'])
            self.assertTrue(result['temporary_profile_removed'])
            self.assertEqual(system.events[-1], ('delete', visit.profile, 'Wi-Fi'))
            self.assertNotEqual(visit.profile, 'Internet & café')
    def test_probe_failure_restores_and_keeps_diagnostics(self):
        with tempfile.TemporaryDirectory() as output:
            system = Fake('probe')
            visit = self.make(system, output)
            try:
                with self.assertRaises(mod.Failure):
                    visit.join()
            finally:
                result = visit.close()
            self.assertTrue(result['verified'])
            self.assertTrue((Path(output) / 'network-diagnostics.json').is_file())
    def test_failed_restore_never_deletes_profile_or_disarms_watchdog(self):
        with tempfile.TemporaryDirectory() as output:
            system = Fake('restore')
            visit = self.make(system, output)
            visit.join()
            result = visit.close()
            self.assertFalse(result['verified'])
            self.assertFalse(visit.state['watchdog_cancel'])
            self.assertFalse(any(event[0] == 'delete' for event in system.events))
    def test_cancel_restores_and_no_profile_command_injection(self):
        with tempfile.TemporaryDirectory() as output:
            system = Fake()
            visit = self.make(system, output)
            visit.join()
            try:
                raise KeyboardInterrupt()
            except KeyboardInterrupt:
                result = visit.close()
            self.assertTrue(result['verified'])
        calls = []
        system = mod.System()
        system.command = lambda args: calls.append(args)
        system.remove_profile('Codex-GLD-dual-abc&$()', 'Wi-Fi & café')
        self.assertEqual(calls[0][-2:], ['name=Codex-GLD-dual-abc&$()', 'interface=Wi-Fi & café'])
        with self.assertRaises(mod.Failure):
            system.remove_profile('Original', 'Wi-Fi')
    def test_watchdog_rejects_foreign_state_path_before_actions(self):
        with tempfile.TemporaryDirectory() as output:
            system = Fake()
            with self.assertRaises(mod.Failure):
                mod.watchdog(Path(output) / 'restore-state.json', system)
            self.assertEqual(system.events, [])
    def test_watchdog_honors_cancellation_written_at_deadline(self):
        (Path(__file__).parent / 'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'output') as output:
            path = Path(output) / 'restore-state.json'
            state = dict(created_unix_s=0, watchdog_cancel=False,
                         original_wifi={}, profile_added=False)
            path.write_text(json.dumps(state))
            def boundary():
                state['watchdog_cancel'] = True
                path.write_text(json.dumps(state))
                return 90
            system = Fake()
            mod.watchdog(path, system, wall=boundary)
            self.assertEqual(system.events, [])


if __name__ == '__main__':
    (Path(__file__).parent / 'output').mkdir(exist_ok=True)
    unittest.main()
