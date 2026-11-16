import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('ch_bridge_candidate_test', ROOT / 'apps/ch-operator/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class CandidatePackageEndpoint(unittest.TestCase):
    def request(self, query):
        handler = object.__new__(bridge.Handler)
        handler.path = '/api/firmware/package?' + query
        with (mock.patch.object(handler, '_require_api_access'),
              mock.patch.object(handler, '_request_error') as error,
              mock.patch.object(bridge, 'json_response') as response):
            handler.do_GET()
        return response, error

    def test_both_boards_load_new_candidate_and_validate_binary(self):
        for env, shape in [('ch_small', 'rectangle'), ('ch_large', 'circle')]:
            with self.subTest(environment=env):
                response, error = self.request(f'env={env}&package=current-source-20261116')
                error.assert_not_called()
                package = response.call_args.args[1]
                self.assertEqual(package['manifest']['boardShape'], shape)
                bridge.validate_firmware_package(package['manifest'], package['packageFiles'], env, '0010')

    def test_legacy_default_preserved_and_unknown_candidate_rejected(self):
        response, error = self.request('env=ch')
        error.assert_not_called()
        self.assertEqual(response.call_args.args[1]['manifest']['environment'], 'ch')
        for query in ['env=ch&package=current-source-20261116', 'env=ch_large&package=..']:
            response, error = self.request(query)
            response.assert_not_called()
            error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
