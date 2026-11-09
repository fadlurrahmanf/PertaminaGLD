"""Synthetic profiles/generators and inert local HTTP API; no Node-RED service."""
from pathlib import Path
import hashlib
import http.server
import importlib.util
import json
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("handover_nodered_under_test", TOOLS / "handover_nodered.py")
nr = importlib.util.module_from_spec(spec); spec.loader.exec_module(nr)


class NodeRedPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.repo = self.root / "repo"; self.source = self.repo / "server/nodered"; (self.source / "functions").mkdir(parents=True)
        (self.source / "apply-pertamina-gld-flow.js").write_text("// synthetic copied generator only")
        (self.source / "apply-pertamina-gld-dataset-flow.ps1").write_text('$csvHeader = "device_id,seq,sv0"\n')
        (self.source / "functions/example.js").write_text("return msg;")
        self.snapshot = self.root / "snapshot"; profile = self.snapshot / "nodered"; profile.mkdir(parents=True)
        (profile / "settings.js").write_text("module.exports={functionGlobalContext:{custom:1},contextStorage:{default:'memoryOnly',memoryOnly:{module:'memory'},customFile:{module:'localfilesystem',config:{dir:'old-context'}}}};\n")
        (profile / "flows.json").write_text(json.dumps([
            dict(id="old-main",type="tab",label="Pertamina GLD Server"),dict(id="old-node",type="inject",z="old-main"),
            dict(id="pgl_old_broker",type="mqtt-broker",broker="old-host",port="1884"),
            dict(id="pgld_ds_old",type="tab",label="GLD Dataset Server"),
            dict(id="other-tab",type="tab",label="User preserved"),
            dict(id="aedes",type="aedes broker",mqtt_port="1883",mqtt_ws_port=""),
            dict(id="other-broker",type="mqtt-broker",broker="127.0.0.1",port="1883")]))
        (profile / "flows_cred.json").write_text('{"$":"SYNTHETIC_ENCRYPTED_CREDS"}')
        (profile / ".config.runtime.json").write_text('{"_credentialSecret":"SYNTHETIC_KEY_ONLY"}')
        (profile / "old-context").mkdir(); (profile / "old-context/state.json").write_text('{"kept":true}')
        self.runtime = self.root / "runtime"; (self.runtime / "node").mkdir(parents=True)
        (self.runtime / "node/node.exe").write_bytes(b"NOT_EXECUTED")
        modules = self.runtime / "user-node_modules/node-red-node-mysql"; modules.mkdir(parents=True)
        (modules / "package.json").write_text('{"name":"node-red-node-mysql","version":"3.0.4"}')
        self.work = self.root / "work"
        self.system = dict(serverEnv={"GLD_AES128_KEY_HEX":"SYNTHETIC_AES","PGL_COMMAND_AUTH_TOKEN":"SYNTHETIC_TOKEN"},
                           broker=dict(host="127.0.0.1",port=1884,username="synthetic-user",password="SYNTHETIC_BROKER"))
        self.database = dict(name="pertamina_gld",user="pgl",password="SYNTHETIC_DATABASE",rootPassword="SYNTHETIC_ROOT")
        self.ports = dict(nodeRed=1880,mqtt=1884,database=33306,hub=5173)
        self.commands = []

    def tearDown(self): self.temp.cleanup()

    def generate(self, args, **kwargs):
        self.commands.append((args, kwargs))
        for secret in ("SYNTHETIC_BROKER", "SYNTHETIC_DATABASE", "SYNTHETIC_TOKEN", "SYNTHETIC_AES"):
            self.assertNotIn(secret," ".join(args))
        if len(args)>1 and args[1].endswith("apply-pertamina-gld-flow.js"):
            path=Path(args[1]).parent/"pertamina-gld-server.flow.json"
            path.write_text(json.dumps([dict(id="pgl_tab",type="tab",label="Pertamina GLD Server"),
                dict(id="pgl_mqtt_broker",type="mqtt-broker",broker=args[args.index('--mqtt-host')+1],port=args[args.index('--mqtt-port')+1]),
                dict(id="pgl_reader",type="mqtt in",z="pgl_tab",broker="pgl_mqtt_broker")]))
        elif args[0]=="powershell":
            path=Path(args[args.index('-File')+1]).parent/"pertamina-gld-dataset.flow.json"
            path.write_text(json.dumps([dict(id="pgld_ds_tab",type="tab",label="GLD Dataset Server"),
                dict(id="pgld_ds_mysql",type="MySQLdatabase",host="127.0.0.1",port=args[args.index('-MySqlPort')+1])]))
        return SimpleNamespace(returncode=0,stdout=b"",stderr=b"")

    def prepare(self, offset=10000):
        with mock.patch.object(nr.subprocess,"run",side_effect=self.generate):
            return nr.prepare(self.repo,self.snapshot,self.runtime,self.work,self.system,self.database,self.ports,offset)

    def test_prepare_copied_generators_merged_flows_and_preserved_raw_profile(self):
        before={p:p.read_bytes() for parent in (self.repo,self.snapshot) for p in parent.rglob('*') if p.is_file()}
        result=self.prepare();profile=Path(result['profile']);merged=json.loads(Path(result['flows']).read_text())
        self.assertEqual(result['ports']['nodeRed'],11880);self.assertEqual(result['ports']['database'],43306)
        self.assertEqual(len({n['id'] for n in merged}),len(merged))
        initial=json.loads((profile/'flows.json').read_text());self.assertFalse(any(n['id'].startswith(('pgl_','pgld_ds_')) for n in initial))
        self.assertFalse(any(n['id']=='old-node' for n in merged));self.assertTrue(any(n['id']=='other-tab' for n in merged))
        self.assertEqual(next(n for n in initial if n['id']=='aedes')['mqtt_port'],'11883')
        self.assertEqual(next(n for n in initial if n['id']=='other-broker')['port'],'11883')
        self.assertEqual(next(n for n in merged if n['type']=='MySQLdatabase')['credentials'],dict(user='pgl',password='SYNTHETIC_DATABASE'))
        self.assertEqual(next(n for n in merged if n['id']=='pgl_mqtt_broker')['credentials']['password'],'SYNTHETIC_BROKER')
        for name in ('settings.js','flows.json','flows_cred.json','.config.runtime.json'):
            self.assertEqual((profile/'handover-original'/name).read_bytes(),(self.snapshot/'nodered'/name).read_bytes())
        self.assertEqual((profile/'.config.runtime.json').read_bytes(),(self.snapshot/'nodered/.config.runtime.json').read_bytes())
        settings=(profile/'settings.js').read_text();self.assertIn("module.exports.uiHost = '127.0.0.1'",settings)
        self.assertIn('module.exports.uiPort = 11880',settings);self.assertIn('pglTopologyFile',settings);self.assertIn('Object.assign',settings)
        self.assertEqual(Path(result['csv']).read_bytes(),b'device_id,seq,sv0\r\n')
        self.assertTrue((profile/'node_modules/node-red-node-mysql/package.json').is_file())
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertEqual(len(self.commands),3)

    def test_repeat_then_upgrade_preserves_nonproject_context_credentials_and_csv(self):
        result=self.prepare();profile=Path(result['profile'])
        (profile/'flows.json').write_text(json.dumps([
            dict(id='user-edited',type='tab',label='Operator note'),
            dict(id='pgl_old',type='inject',z='pgl_tab')]))
        (profile/'old-context/state.json').write_text('{"afterStart":true}')
        (profile/'flows_cred.json').write_text('{"$":"UPDATED_SYNTHETIC_ENCRYPTED_CREDS"}')
        Path(result['csv']).write_bytes(b'device_id,seq,sv0\r\nGLD,1,0.5\r\n')
        self.commands=[];again=self.prepare();self.assertEqual(again,result);self.assertEqual(self.commands,[])
        self.system['broker']['password']='CHANGED_SYNTHETIC'
        upgraded=self.prepare();new_profile=Path(upgraded['profile'])
        self.assertNotEqual(new_profile,profile);self.assertTrue(profile.is_dir())
        self.assertEqual((new_profile/'old-context/state.json').read_text(),'{"afterStart":true}')
        self.assertEqual((new_profile/'flows_cred.json').read_text(),'{"$":"UPDATED_SYNTHETIC_ENCRYPTED_CREDS"}')
        self.assertEqual((new_profile/'.config.runtime.json').read_bytes(),(profile/'.config.runtime.json').read_bytes())
        self.assertEqual(Path(upgraded['csv']).read_bytes(),b'device_id,seq,sv0\r\nGLD,1,0.5\r\n')
        ids={n['id'] for n in json.loads(Path(upgraded['flows']).read_text())}
        self.assertIn('user-edited',ids);self.assertNotIn('pgl_old',ids)
        receipt=json.loads((self.work/nr.RECEIPT).read_text())
        self.assertEqual(receipt['profile'],str(new_profile))
        self.assertEqual(new_profile.name,'n'+receipt['fingerprint'][:10])

    def test_partial_version_publish_recovers_without_deleting_old_profile(self):
        prior=self.prepare();old=Path(prior['profile'])
        self.system['broker']['password']='CHANGED_SYNTHETIC'
        publish=nr._publish_directory
        calls=[]
        def interrupted(*args):
            result=publish(*args);calls.append(args[1])
            if len(calls)==1:raise RuntimeError('synthetic crash after profile rename')
            return result
        with mock.patch.object(nr,'_publish_directory',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'synthetic crash'):self.prepare()
        self.assertTrue(old.is_dir());self.assertTrue(calls[0].is_dir())
        self.assertEqual(json.loads((self.work/nr.RECEIPT).read_text())['profile'],str(old))
        upgraded=self.prepare()
        self.assertEqual(upgraded['profile'],str(calls[0]))
        self.assertTrue(Path(upgraded['generator']).is_dir());self.assertTrue(Path(upgraded['flows']).is_file())
        self.assertTrue(old.is_dir())

    def test_receipt_replace_failure_keeps_previous_version_and_retry_recovers(self):
        prior=self.prepare();old=Path(prior['profile'])
        old_receipt=(self.work/nr.RECEIPT).read_bytes()
        self.system['broker']['password']='CHANGED_SYNTHETIC'
        replace=Path.replace
        def interrupted(path,target):
            if Path(target)==self.work/nr.RECEIPT:
                raise OSError('synthetic crash before atomic receipt')
            return replace(path,target)
        with mock.patch.object(Path,'replace',interrupted):
            with self.assertRaisesRegex(OSError,'synthetic crash'):self.prepare()
        self.assertEqual((self.work/nr.RECEIPT).read_bytes(),old_receipt)
        self.assertTrue(old.is_dir())
        self.assertFalse(list(self.work.glob('.*.tmp')))
        upgraded=self.prepare()
        self.assertNotEqual(upgraded['profile'],str(old))
        self.assertEqual(json.loads((self.work/nr.RECEIPT).read_text())['profile'],upgraded['profile'])

    def test_migration_refuses_linked_prior_state_without_changing_receipt(self):
        prior=self.prepare();old=Path(prior['profile']);receipt=(self.work/nr.RECEIPT).read_bytes()
        (old/'old-context/state.json').write_text('{"keep":true}')
        self.system['broker']['password']='CHANGED_SYNTHETIC'
        actual=nr.archive_util._reparse
        with mock.patch.object(nr.archive_util,'_reparse',side_effect=lambda path: (Path(path).is_relative_to(old) and Path(path).name=='state.json') or actual(path)):
            with self.assertRaisesRegex(ValueError,'LINKED_PRIOR_PROFILE_REFUSED'):self.prepare()
        self.assertEqual((self.work/nr.RECEIPT).read_bytes(),receipt)
        self.assertEqual((old/'old-context/state.json').read_text(),'{"keep":true}')

    def test_existing_unknown_profile_and_generator_failure_are_not_overwritten(self):
        profile=self.work/'nodered';profile.mkdir(parents=True);(profile/'keep').write_text('preserve')
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual((profile/'keep').read_text(),'preserve')

    def test_generator_failure_is_redacted_and_no_profile_published(self):
        with mock.patch.object(nr.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=b'SYNTHETIC_SECRET',stderr=b'SYNTHETIC_SECRET')):
            with self.assertRaisesRegex(ValueError,'COPIED_GENERATOR_FAILED') as error:
                nr.prepare(self.repo,self.snapshot,self.runtime,self.work,self.system,self.database,self.ports)
        self.assertNotIn('SYNTHETIC_SECRET',str(error.exception));self.assertFalse((self.work/'nodered').exists())

    def test_production_ports_are_not_shifted(self):
        result=self.prepare(offset=0);self.assertEqual(result['ports'],self.ports)
        initial=json.loads((Path(result['profile'])/'flows.json').read_text())
        self.assertEqual(next(n for n in initial if n['id']=='aedes')['mqtt_port'],'1883')


class RevisionDeploy(unittest.TestCase):
    def test_local_v2_revision_merge_and_redacted_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'desired.json';path.write_text(json.dumps([dict(id='pgl_tab',type='tab',label='Pertamina GLD Server'),dict(id='pgl_mqtt_broker',type='mqtt-broker',credentials=dict(user='synthetic',password='SYNTHETIC_PASSWORD'))]))
            requests=[];failure={'enabled':False}
            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self,*_):pass
                def do_GET(self):
                    requests.append(('GET',self.headers.get('Node-RED-API-Version'),None));self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                    self.wfile.write(json.dumps(dict(rev='fresh-revision',flows=[dict(id='current-user-tab',type='tab',label='User'),dict(id='pgl_old',type='inject')])).encode())
                def do_POST(self):
                    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(('POST',self.headers.get('Node-RED-API-Version'),body))
                    self.send_response(500 if failure['enabled'] else 200);self.send_header('Content-Type','application/json');self.end_headers()
                    self.wfile.write(b'{"error":"SYNTHETIC_PASSWORD"}' if failure['enabled'] else b'{"rev":"new-revision"}')
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_address[1]}'
                result=nr.deploy(url,path,token='SYNTHETIC_TOKEN');self.assertTrue(result['applied']);self.assertEqual(result['preservedNodes'],1)
                self.assertEqual(requests[-1][2]['rev'],'fresh-revision');self.assertEqual(requests[-1][1],'v2')
                ids={n['id'] for n in requests[-1][2]['flows']};self.assertIn('current-user-tab',ids);self.assertNotIn('pgl_old',ids)
                failure['enabled']=True
                with self.assertRaisesRegex(ValueError,'NODE_RED_DEPLOY_FAILED') as error:nr.deploy(url,path,token='SYNTHETIC_TOKEN')
                self.assertNotIn('SYNTHETIC_PASSWORD',str(error.exception));self.assertNotIn('SYNTHETIC_TOKEN',str(error.exception))
                with self.assertRaises(ValueError):nr.deploy('http://example.com',path,token='SYNTHETIC_TOKEN')
            finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
