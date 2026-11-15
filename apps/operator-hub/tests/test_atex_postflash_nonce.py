import importlib.util, unittest
from pathlib import Path
from unittest import mock
p=Path(__file__).resolve().parent.parent/'bridge.py'; spec=importlib.util.spec_from_file_location('nonce_hub',p); hub=importlib.util.module_from_spec(spec); spec.loader.exec_module(hub)
class FreshIdentity(unittest.TestCase):
 def test_one_leased_call_with_pinned_stream(self):
  status=dict(connected=True,port='COM999',telemetryStream='stream-a')
  identity=dict(nonce='ab'*16,deviceId='1001',modelProfileId='profile-1',firmwareVersion='1.2.3',boardProfile='GLD ATEX MotherBoardGLDVer2')
  def request(host,device,method,path,payload=None,**kwargs):
   if path.startswith('/api/serial/status'): return status
   self.assertEqual(path,'/api/serial/atex-identity')
   self.assertEqual(payload,dict(slot=1,port='COM999',targetDeviceId='1001'))
   return dict(ok=True,telemetryStream='stream-a',identity=identity)
  with mock.patch.object(hub,'child_request',side_effect=request) as call:
   result=hub.wait_for_atex_readback('localhost','COM999','1001')
   self.assertEqual(result['info']['model']['profileId'],'profile-1')
   self.assertEqual(call.call_count,2)
 def test_reconnect_between_status_and_lease_rejected(self):
  status=dict(connected=True,port='COM999',telemetryStream='stream-a')
  leased=dict(ok=True,telemetryStream='stream-b',identity=dict(nonce='ab'*16))
  with mock.patch.object(hub,'child_request',side_effect=[status,leased]):
   with self.assertRaisesRegex(RuntimeError,'stream changed'): hub.wait_for_atex_readback('localhost','COM999','1001')
 def test_no_retry_after_unknown_result(self):
  status=dict(connected=True,port='COM999',telemetryStream='stream-a')
  with mock.patch.object(hub,'child_request',side_effect=[status,RuntimeError('unknown')]) as call:
   with self.assertRaisesRegex(RuntimeError,'unknown'): hub.wait_for_atex_readback('localhost','COM999','1001')
   self.assertEqual(call.call_count,2)
 def test_reject_invalid_nonce_or_wrong_port(self):
  status=dict(connected=True,port='COM999',telemetryStream='stream-a')
  leased=dict(ok=True,telemetryStream='stream-a',identity=dict(nonce='wrong'))
  with mock.patch.object(hub,'child_request',side_effect=[status,leased]):
   with self.assertRaises(RuntimeError): hub.wait_for_atex_readback('localhost','COM999','1001')
  status['port']='COM888'
  with mock.patch.object(hub,'child_request',return_value=status) as call:
   with self.assertRaises(RuntimeError): hub.wait_for_atex_readback('localhost','COM999','1001')
   self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
