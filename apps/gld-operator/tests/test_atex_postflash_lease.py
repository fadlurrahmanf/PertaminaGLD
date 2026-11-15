"""ATEX postflash nonce lease, synthetic serial only."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/gld-operator'))
spec=importlib.util.spec_from_file_location('postflash_lease_bridge',ROOT/'apps/gld-operator/bridge.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

class Wire:
 def __init__(self): self.is_open=True;self.commands=[];self.sent=threading.Event()
 def write(self,data): self.commands.append(data.decode().strip());self.sent.set()
 def flush(self): pass
 def close(self): self.is_open=False

class PostflashLease(unittest.TestCase):
 def setUp(self):
  self.wire=Wire();self.serial=bridge.SerialBridge(bridge.EventHub())
  with self.serial._lock:
   self.serial._serial=self.wire; self.serial.port='COM999'; self.serial._telemetry_stream='fresh-stream'
  self.results=[]
 def begin(self,timeout=.25):
  def run():
   try: self.results.append(self.serial.challenge_atex_identity('COM999','1001',timeout,keep_connected=True))
   except Exception as exc: self.results.append(exc)
  self.thread=threading.Thread(target=run,daemon=True);self.thread.start();self.assertTrue(self.wire.sent.wait(1))
  return json.loads(self.wire.commands[-1].split(' ',1)[1])['nonce']
 def respond(self,nonce):
  value=dict(nonce=nonce,boardProfile='GLD ATEX MotherBoardGLDVer2',deviceId='1001',modelProfileId='model',firmwareVersion='1.2.3')
  self.serial._record_line('GLD_ATEX_IDENTITY_JSON '+json.dumps(value));return value
 def finish(self):
  self.thread.join(2); self.assertFalse(self.thread.is_alive());self.assertEqual(len(self.results),1);return self.results[0]
 def test_success_keeps_handle_and_serial_gate_usable(self):
  nonce=self.begin(); expected=self.respond(nonce);result=self.finish()
  self.assertEqual(result,dict(ok=True,identity=expected,telemetryStream='fresh-stream'))
  self.assertTrue(self.wire.is_open);self.assertTrue(self.serial._poll_gate.is_idle());self.assertFalse(self.serial._atex_identity_active)
  self.assertTrue(self.serial.write_line('GET_INFO')['ok']);self.assertEqual(len(self.wire.commands),2)
 def test_concurrent_writes_disconnect_and_connect_rejected(self):
  nonce=self.begin()
  for action in (lambda:self.serial.write_line('GET_STATUS'),lambda:self.serial.disconnect(),lambda:self.serial.connect('COM999')):
   with self.assertRaisesRegex(RuntimeError,'owns serial'): action()
  self.respond(nonce);self.assertIsInstance(self.finish(),dict)
 def test_stale_nonce_and_timeout_quarantine_without_retry(self):
  self.serial._record_line('GLD_ATEX_IDENTITY_JSON '+json.dumps(dict(nonce='0'*32)))
  self.begin(.1);result=self.finish();self.assertIsInstance(result,RuntimeError);self.assertIn('timed out',str(result))
  self.assertTrue(self.serial._poll_gate.is_quarantined());self.assertTrue(self.wire.is_open)
  with self.assertRaisesRegex(RuntimeError,'unknown'): self.serial.write_line('GET_INFO')
  self.assertEqual(len(self.wire.commands),1)
 def test_handle_swap_after_matching_reply_is_rejected(self):
  original=self.serial.recent_lines; swapped=[False]
  def recent(after=0):
   data=original(after)
   if data['lines'] and not swapped[0]:
    with self.serial._lock:
     self.serial._serial=Wire();self.serial._generation+=1
    swapped[0]=True
   return data
  self.serial.recent_lines=recent
  nonce=self.begin(); self.respond(nonce);result=self.finish()
  self.assertIsInstance(result,RuntimeError);self.assertIn('ownership changed',str(result));self.assertTrue(self.wire.is_open)
  self.assertEqual(self.serial._atex_identity_unknown_stream,'fresh-stream')
 def test_endpoint_only_uses_atomic_atex_lease(self):
  handler=object.__new__(bridge.Handler);handler.path='/api/serial/atex-identity'
  payload=dict(slot=2,port='COM999',targetDeviceId='1001')
  expected=dict(ok=True,identity={'modelProfileId':'model'},telemetryStream='stream')
  serial=mock.Mock();serial.challenge_atex_identity.return_value=expected
  with mock.patch.object(bridge.Handler,'_require_api_access'), mock.patch.object(bridge,'read_json',return_value=payload), \
       mock.patch.object(bridge,'get_serial_bridge',return_value=serial) as get_bridge, \
       mock.patch.object(bridge,'json_response',return_value='response') as response:
   self.assertEqual(handler.do_POST(),'response')
  get_bridge.assert_called_once_with(2)
  serial.challenge_atex_identity.assert_called_once_with('COM999','1001',keep_connected=True)
  response.assert_called_once_with(handler,expected)

 def test_preflash_still_disconnects_and_gld1_skip_unchanged(self):
  out=[]
  def preflash():
   try: out.append(self.serial.challenge_atex_identity('COM999','1001',.3))
   except Exception as exc: out.append(exc)
  t=threading.Thread(target=preflash,daemon=True);t.start();self.assertTrue(self.wire.sent.wait(1));nonce=json.loads(self.wire.commands[0].split(' ',1)[1])['nonce'];self.respond(nonce);t.join(2)
  self.assertFalse(t.is_alive());self.assertEqual(out,[None]);self.assertFalse(self.wire.is_open)
  gld1=bridge.SerialBridge(bridge.EventHub());self.assertTrue(gld1.write_line('GET_INFO',require_connected=False)['skipped'])

if __name__=='__main__': unittest.main()

