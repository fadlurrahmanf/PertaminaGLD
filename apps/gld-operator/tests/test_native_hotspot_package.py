"""Package admission only; no device, network, serial or firmware operation."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'apps/operator-hub/tests'))
from test_child_package_validators import GLD_BRIDGE, package_for


class NativeHotspotPackage(unittest.TestCase):
    def test_each_final_model_accepts_explicit_native_capabilities(self):
        for model in (1, 2, 3):
            env = f'gld_model_{model}_dataset_workflow_wifi'
            manifest, files = package_for(GLD_BRIDGE, env, {
                'capabilities': {'nativeSerial': True, 'datasetWifi': True}})
            with self.subTest(model=model):
                validated, verified = GLD_BRIDGE.validate_firmware_package(
                    manifest, files, env, '1002')
                self.assertTrue(validated['capabilities']['nativeSerial'])
                self.assertEqual(len(verified), 1)

    def test_old_manifest_stays_valid_without_capabilities(self):
        for env in ('gld_model_1', 'gld_model_1_dataset_wifi',
                    'gld_model_1_dataset_replay_wifi', 'gld_model_1_dataset_workflow_wifi'):
            manifest, files = package_for(GLD_BRIDGE, env, {})
            with self.subTest(env=env):
                GLD_BRIDGE.validate_firmware_package(manifest, files, env, '1002')

    def test_rejects_false_ambiguous_or_unrelated_capability_claims(self):
        env = 'gld_model_1_dataset_workflow_wifi'
        base, files = package_for(GLD_BRIDGE, env, {})
        for value in (None, True, {}, {'nativeSerial': True},
                      {'nativeSerial': 1, 'datasetWifi': True},
                      {'nativeSerial': 'true', 'datasetWifi': True},
                      {'nativeSerial': True, 'datasetWifi': False},
                      {'nativeSerial': True, 'datasetWifi': True, 'unknown': True}):
            manifest = copy.deepcopy(base)
            manifest['capabilities'] = value
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'capabilities'):
                GLD_BRIDGE.validate_firmware_package(manifest, files, env, '1002')
        for old_env in ('gld_model_1', 'gld_model_1_dataset_wifi', 'gld_model_1_dataset_replay_wifi'):
            manifest, files = package_for(GLD_BRIDGE, old_env, {
                'capabilities': {'nativeSerial': True, 'datasetWifi': True}})
            with self.subTest(env=old_env), self.assertRaisesRegex(RuntimeError, 'capabilities'):
                GLD_BRIDGE.validate_firmware_package(manifest, files, old_env, '1002')

    def test_unknown_metadata_is_still_rejected(self):
        env = 'gld_model_1_dataset_workflow_wifi'
        manifest, files = package_for(GLD_BRIDGE, env, {'unknown': 'field'})
        with self.assertRaisesRegex(RuntimeError, 'unsupported'):
            GLD_BRIDGE.validate_firmware_package(manifest, files, env, '1002')


if __name__ == '__main__':
    unittest.main()
