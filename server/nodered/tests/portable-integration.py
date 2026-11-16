"""Isolated MQTT/Node-RED smoke test; no existing service or device is used."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[3]
NODE_RED = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/node-red/red.js'
if not NODE_RED.is_file():
    raise SystemExit('Node-RED CLI not installed; isolated smoke test skipped')
spec = importlib.util.spec_from_file_location('local_broker', ROOT / 'apps/gld-operator/local_mqtt_broker.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

with tempfile.TemporaryDirectory(prefix='pgl-nodered-smoke-') as directory:
    root = Path(directory)
    port, http_port = free_port(), free_port()
    broker_events = []
    broker = module.LocalMqttBroker('127.0.0.1', port, log=broker_events.append,
                                    username='synthetic', password='synthetic-password')
    broker.start()
    process = None
    client = None
    try:
        flows = json.loads((ROOT / 'server/nodered/pertamina-gld-server.flow.json').read_text(encoding='utf-8'))
        for item in flows:
            if item.get('type') == 'mqtt-broker':
                item.update(broker='127.0.0.1', port=str(port), usetls=False)
            if item.get('type') == 'tab':
                for var in item.get('env', []):
                    if var['name'] in ('PGL_REPLAY_STATE_PATH', 'PGL_TOPOLOGY_BOOTSTRAP_FILE'):
                        var['value'] = str(root / (var['name'] + '.json'))
                    if var['name'] == 'PGL_FIELD_TEST_LOG_DIR':
                        var['value'] = str(root / 'logs')
        (root / 'flows.json').write_text(json.dumps(flows), encoding='utf-8')
        (root / 'flows_cred.json').write_text(json.dumps({'pgl_mqtt_broker':{'user':'synthetic','password':'synthetic-password'}}))
        (root / 'settings.js').write_text("module.exports={flowFile:'flows.json', credentialSecret:false, functionExternalModules:true, uiHost:'127.0.0.1'};", encoding='utf-8')
        output = (root / 'nodered.log').open('w+', encoding='utf-8')
        process = subprocess.Popen(['node', str(NODE_RED), '--userDir', str(root), '--port', str(http_port)],
                                   cwd=str(root), stdout=output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('isolated Node-RED exited during startup')
            with broker.lock:
                connected = any(c.client_id == 'node-red-pertamina-gld' and c.authenticated for c in broker.clients)
            if connected:
                break
            time.sleep(.2)
        else:
            output.flush()
            raise RuntimeError('Node-RED did not authenticate with isolated broker: ' + str(broker_events) + '\n' + (root / 'nodered.log').read_text(encoding='utf-8'))
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='synthetic-gateway')
        client.username_pw_set('synthetic', 'synthetic-password')
        client.connect('127.0.0.1', port)
        client.loop_start()
        # Allow Node-RED's subscriptions to complete before publishing.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with broker.lock:
                subscribed = any(c.client_id == 'node-red-pertamina-gld' and 'gld/gateway/status' in c.subscriptions for c in broker.clients)
            if subscribed:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Node-RED did not subscribe to Gateway status')
        client.publish('gld/gateway/status', json.dumps({'kind':'gateway-status','gatewayId':1}), qos=0)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{http_port}/pertamina-gld/topology', timeout=2) as response:
                    payload = json.load(response)
                if '0x0001' in json.dumps(payload):
                    print('PASS isolated authenticated MQTT -> imported Node-RED flow -> topology HTTP')
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Gateway status did not appear in Node-RED topology')
    finally:
        if client:
            client.disconnect()
            client.loop_stop()
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            output.close()
        broker.stop()
