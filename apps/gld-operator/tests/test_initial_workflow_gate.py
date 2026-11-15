"""Confirm initial Workflow admission reaches AES gate without opening a port."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('gld_initial_workflow_bridge', ROOT / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class InitialWorkflowGate(unittest.TestCase):
    def check(self, caps, **fields):
        payload = dict(env='gld_model_1_dataset_workflow_wifi', port='COM999',
                       targetDeviceId='1001', resetNvs=True, **fields)
        with mock.patch.object(bridge, 'validate_firmware_package', return_value=({'capabilities':caps}, [])), \
             mock.patch.object(bridge, 'load_canonical_gld_aes_key', return_value=None):
            with self.assertRaises(RuntimeError) as raised:
                bridge._firmware_upload_reserved(payload)
        return str(raised.exception)
    def test_initial_native_still_requires_aes(self):
        self.assertIn('provisioning AES', self.check({'nativeSerial':True, 'datasetWifi':True},
            initialFirmware=True, resetNvsConfirmation='RESET NVS'))
    def test_noninitial_missing_confirmation_or_capability_are_rejected(self):
        for caps, fields in [({'nativeSerial':True, 'datasetWifi':True}, {}),
                             ({'nativeSerial':True, 'datasetWifi':True}, {'initialFirmware':True}),
                             ({}, {'initialFirmware':True, 'resetNvsConfirmation':'RESET NVS'})]:
            self.assertIn('Reset NVS must be OFF', self.check(caps, **fields))

if __name__ == '__main__': unittest.main()
