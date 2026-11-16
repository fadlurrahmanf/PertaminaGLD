import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('gw_bridge_version_test', ROOT / 'apps/gw-operator/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class GatewayVersionCandidates(unittest.TestCase):
    def test_versioned_packages_match_their_board_and_hashes(self):
        for env, shape in [('gw_v1', 'rectangle'), ('gw_v2', 'circle'), ('gw_v3', 'rectangle')]:
            with self.subTest(env=env):
                handler = object.__new__(bridge.Handler)
                handler.path = '/api/firmware/package?env=' + env + '&package=candidate-board-20261116'
                with (mock.patch.object(handler, '_require_api_access'),
                      mock.patch.object(handler, '_request_error') as error,
                      mock.patch.object(bridge, 'json_response') as response):
                    handler.do_GET()
                error.assert_not_called()
                package = response.call_args.args[1]
                self.assertEqual(package['manifest']['boardShape'], shape)
                bridge.validate_firmware_package(package['manifest'], package['packageFiles'], env, '0001')


if __name__ == '__main__':
    unittest.main()
