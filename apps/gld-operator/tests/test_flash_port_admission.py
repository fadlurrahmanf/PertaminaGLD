"""Port-admission concurrency tests; synthetic serial only."""
import importlib.util
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'apps/gld-operator'))
spec=importlib.util.spec_from_file_location('port_admission_bridge', ROOT/'apps/gld-operator/bridge.py')
bridge=importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)

class Port:
    def __init__(self, entered=None, release=None, fail=False):
        self.is_open=False; self.entered=entered; self.release=release; self.fail=fail
    def open(self):
        if self.entered: self.entered.set()
        if self.release and not self.release.wait(2): raise RuntimeError('test timeout')
        if self.fail: raise OSError('synthetic open failure')
        self.is_open=True
    def close(self): self.is_open=False
    def setDTR(self, value): pass
    def setRTS(self, value): pass
    def read(self, n): time.sleep(.005); return b''

class PortAdmission(unittest.TestCase):
    def setUp(self):
        with bridge.flash_port_lock:
            bridge.flash_ports.clear(); bridge.flash_port_operations.clear()
        with bridge.serial_bridges_lock: bridge.serial_bridges.clear()

    def test_two_slots_open_barrier_blocks_reservation(self):
        entered, release=threading.Event(), threading.Event(); failures=[]
        fake=Port(entered,release); one=bridge.SerialBridge(bridge.EventHub(),1); two=bridge.SerialBridge(bridge.EventHub(),2)
        def open_one():
            try: one.connect('com999')
            except Exception as exc: failures.append(exc)
        with mock.patch.object(bridge,'serial',type('Fake',(),{'Serial':staticmethod(lambda:fake)})):
            thread=threading.Thread(target=open_one,daemon=True); thread.start(); self.assertTrue(entered.wait(1))
            self.assertIsNone(bridge.reserve_flash_port('COM999'))
            release.set(); thread.join(2); self.assertFalse(thread.is_alive()); self.assertEqual(failures,[])
            token=bridge.reserve_flash_port('com999'); self.assertIsNotNone(token)
            with self.assertRaisesRegex(RuntimeError,'reserved'): two.connect('COM999')
            bridge.release_flash_port('COM999',token); one.disconnect()

    def test_probe_barrier_and_internal_token(self):
        entered, release=threading.Event(), threading.Event(); answers=[]
        fake=Port(entered,release)
        with mock.patch.object(bridge,'serial',type('Fake',(),{'Serial':staticmethod(lambda:fake)})):
            t=threading.Thread(target=lambda: answers.append(bridge.probe_port('com999')),daemon=True); t.start()
            self.assertTrue(entered.wait(1)); self.assertIsNone(bridge.reserve_flash_port('COM999'))
            release.set(); t.join(2); self.assertFalse(t.is_alive()); self.assertTrue(answers[0]['free'])
            token=bridge.reserve_flash_port('COM999'); self.assertIsNotNone(token)
            with self.assertRaisesRegex(RuntimeError,'reserved'): bridge.probe_port('com999')
            with self.assertRaisesRegex(RuntimeError,'reserved'): bridge.probe_port('COM999',_reservation=object())
            self.assertTrue(bridge.probe_port('com999',_reservation=token)['free'])
            with self.assertRaisesRegex(RuntimeError,'cannot be released'): bridge.release_flash_port('COM999',object())
            bridge.release_flash_port('COM999',token)

    def test_failure_cleanup_and_release_during_inflight(self):
        fake=Port(fail=True)
        with mock.patch.object(bridge,'serial',type('Fake',(),{'Serial':staticmethod(lambda:fake)})):
            with self.assertRaises(OSError): bridge.SerialBridge(bridge.EventHub()).connect('COM999')
            self.assertFalse(bridge.probe_port('COM999')['free'])
        token=bridge.reserve_flash_port('com999'); self.assertIsNotNone(token)
        bridge._begin_port_operation('COM999',token)
        try:
            with self.assertRaisesRegex(RuntimeError,'cannot be released'): bridge.release_flash_port('com999',token)
        finally: bridge._end_port_operation('com999')
        bridge.release_flash_port('COM999',token)
        with self.assertRaisesRegex(RuntimeError,'not valid'): bridge._require_flash_reservation('COM999',token)

    def test_upload_exception_releases_only_owned_token(self):
        with mock.patch.object(bridge, 'require_atex_release'), \
             mock.patch.object(bridge, 'reject_atex_manifest_before_release'), \
             mock.patch.object(bridge, '_firmware_upload_reserved', side_effect=RuntimeError('synthetic upload failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic upload failure'):
                bridge.firmware_upload({'port':'COM999'})
        self.assertFalse(bridge.is_flash_port_reserved('com999'))
        with self.assertRaisesRegex(RuntimeError, 'not valid'):
            bridge.probe_port('COM999', _reservation=object())

    def test_gld1_disconnected_skip(self):
        one=bridge.SerialBridge(bridge.EventHub(),1)
        self.assertTrue(one.write_line('GET_INFO',require_connected=False)['skipped'])
        a=bridge.reserve_flash_port('COM1'); b=bridge.reserve_flash_port('COM2')
        self.assertIsNotNone(a); self.assertIsNotNone(b)
        bridge.release_flash_port('com1',a); bridge.release_flash_port('com2',b)

if __name__=='__main__': unittest.main()
