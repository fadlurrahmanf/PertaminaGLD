"""Pure planning and synthetic MQTT checks; never starts the operator stack."""
from pathlib import Path
import importlib.util
import socketserver
import sys
import threading
import tempfile
import json
import hashlib
import unittest
from unittest import mock

TOOLS=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOLS))
import handover_stack as stack
import handover_hub


class StackTests(unittest.TestCase):
    def test_repeat_smoke_uses_unused_node_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            (profile / 'pertamina-gld-replay-state.json').write_text(json.dumps({
                'observations': {'production:57344': {'lastSeq': 35}}}))
            topology = {'nodes': [{'nodeId': 57345}]}
            self.assertEqual(stack.synthetic_node_id(profile, topology), 57346)

    def test_history_receipt_cannot_hide_missing_or_corrupt_owned_rows(self):
        first = 'a' * 64
        second = 'b' * 64
        history = {'files': [{'sha256': first, 'size': 12}, {'sha256': second, 'size': 20}]}
        self.assertEqual(stack.missing_history_rows(b'', history), {first, second})
        healthy = (f'{first}\t12\t{first}\t2\t2\n').encode()
        self.assertEqual(stack.missing_history_rows(healthy, history), {second})
        with self.assertRaisesRegex(ValueError, 'HISTORY_DATABASE_INTEGRITY_FAILED'):
            stack.missing_history_rows((f'{first}\t12\t{first}\t2\t1\n').encode(), history)
        with self.assertRaisesRegex(ValueError, 'HISTORY_DATABASE_INTEGRITY_FAILED'):
            stack.missing_history_rows((f'{first}\t12\t{second}\t2\t2\n').encode(), history)
        with self.assertRaisesRegex(ValueError, 'HISTORY_DATABASE_AUDIT_INVALID'):
            stack.missing_history_rows(b'bad-row\n', history)

    def test_history_row_audit_detects_changed_content_even_with_same_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sensor.csv').write_bytes(b'a,b\nx,y\n')
            digest = hashlib.sha256((root / 'sensor.csv').read_bytes()).hexdigest()
            history = {'files': [{'sha256': digest, 'path': 'sensor.csv', 'size': 8}]}
            row_hash = hashlib.sha256(json.dumps(['x', 'y'], ensure_ascii=False).encode()).hexdigest()
            healthy = f'{digest}\t1\t{row_hash}\n'.encode()
            stack.verify_history_row_digests(healthy, history, root)
            corrupted = f'{digest}\t1\t' + '0' * 64 + '\n'
            with self.assertRaisesRegex(ValueError, 'HISTORY_DATABASE_INTEGRITY_FAILED'):
                stack.verify_history_row_digests(corrupted.encode(), history, root)

    def test_handover_broker_falls_back_to_loopback_without_lan(self):
        from types import SimpleNamespace
        offline = SimpleNamespace(local_ipv4=lambda: None)
        self.assertTrue(handover_hub.configure_broker_host(offline))
        self.assertEqual(offline.local_ipv4(), '127.0.0.1')
        online = SimpleNamespace(local_ipv4=lambda: '192.0.2.20')
        self.assertFalse(handover_hub.configure_broker_host(online))
        self.assertEqual(online.local_ipv4(), '192.0.2.20')
        self.assertTrue(handover_hub.configure_broker_host(online, force_loopback=True))
        self.assertEqual(online.local_ipv4(), '127.0.0.1')

    def test_lock_recovers_only_a_dead_owned_launcher_not_live_or_foreign(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stack.lock'
            path.write_text('not-owned-user-file')
            with self.assertRaisesRegex(ValueError,'LOCK_NOT_OWNED'):stack.acquire_lock(path)
            value=dict(kind='pertamina-gld-handover',pid=1234,workRoot=str(path.parent.resolve()))
            path.write_text(json.dumps(value))
            with mock.patch.object(stack,'pid_alive',return_value=True):
                with self.assertRaisesRegex(ValueError,'ALREADY_RUNNING'):stack.acquire_lock(path)
            with mock.patch.object(stack,'pid_alive',return_value=False):stack.acquire_lock(path)
            self.assertEqual(json.loads(path.read_text())['pid'],stack.os.getpid())

    def test_offsets_are_applied_once_and_normal_ports_remain_unchanged(self):
        cfg={'ports':dict(hub=5173,nodeRed=1880,mqtt=1884,database=33306)}
        ports=stack.effective_ports(cfg,10000)
        self.assertEqual(ports,dict(hub=15173,nodeRed=11880,mqtt=11884,database=43306,gld=15174,ch=15273,gw=15373))
        self.assertEqual(stack.effective_ports(cfg,0)['hub'],5173)
        for offset in (-1,True,100000):
            with self.assertRaises(ValueError):stack.effective_ports(cfg,offset)

    def test_occupied_port_is_not_reused_or_stopped(self):
        with socketserver.TCPServer(('127.0.0.1',0),socketserver.BaseRequestHandler) as server:
            with self.assertRaisesRegex(ValueError,'PORT_OCCUPIED'):
                stack.require_free_ports({'test':server.server_address[1]})

    def test_mqtt_auth_publish_and_broker_confirmation(self):
        captured=[]
        class Peer(socketserver.BaseRequestHandler):
            def packet(self):
                first=self.request.recv(1);size=0;multiple=1
                while True:
                    value=self.request.recv(1)[0];size+=(value&127)*multiple
                    if not value&128:break
                    multiple*=128
                body=b''
                while len(body)<size:body+=self.request.recv(size-len(body))
                return first,body
            def handle(self):
                first,body=self.packet();captured.append((first,body));self.request.sendall(b'\x20\x02\x00\x00')
                captured.append(self.packet());self.packet();self.request.sendall(b'\xd0\x00');self.packet()
        server=socketserver.TCPServer(('127.0.0.1',0),Peer);thread=threading.Thread(target=server.serve_forever);thread.start()
        try:stack.mqtt_publish('127.0.0.1',server.server_address[1],'synthetic_user','synthetic_password','synthetic/topic',{'x':1})
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
        self.assertIn(b'synthetic_user',captured[0][1]);self.assertIn(b'synthetic_password',captured[0][1])
        self.assertIn(b'synthetic/topic',captured[1][1]);self.assertIn(b'"x": 1',captured[1][1])


if __name__=='__main__':unittest.main()
