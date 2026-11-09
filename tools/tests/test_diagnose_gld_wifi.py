"""Pure PC route checks; never connect to a GLD during unit tests."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnose_gld_wifi as diagnostic


class WifiDiagnosticTests(unittest.TestCase):
    def test_ssid_match_is_exact(self):
        output = '    SSID                   : GLD-DATASET-1002\n'
        with mock.patch.object(diagnostic, 'command', return_value=output):
            self.assertTrue(diagnostic.associated('GLD-DATASET-1002'))
            self.assertFalse(diagnostic.associated('GLD-DATASET-1003'))

    def test_route_must_be_direct_to_gld_subnet(self):
        valid = '{"IPAddress":"192.168.4.2","NextHop":"0.0.0.0","DestinationPrefix":"192.168.4.0/24"}'
        via_gateway = '{"IPAddress":"192.168.4.2","NextHop":"192.168.4.254","DestinationPrefix":"0.0.0.0/0"}'
        with mock.patch.object(diagnostic, 'command', return_value=valid):
            self.assertTrue(diagnostic.on_link())
        with mock.patch.object(diagnostic, 'command', return_value=via_gateway):
            self.assertFalse(diagnostic.on_link())

    def test_no_authentication_when_target_not_associated(self):
        with mock.patch.object(diagnostic, 'associated', return_value=False), \
                mock.patch.object(diagnostic, 'on_link') as route, \
                mock.patch.object(diagnostic, 'hub_busy') as hub:
            result = diagnostic.diagnose('1002', 0)
        self.assertEqual(result['outcome'], 'target_association_or_dhcp_not_observed')
        route.assert_not_called()
        hub.assert_not_called()


if __name__ == '__main__':
    unittest.main()
