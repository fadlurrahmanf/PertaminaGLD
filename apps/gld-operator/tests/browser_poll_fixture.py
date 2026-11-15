"""Isolated loopback fake GLD for browser polling tests; never touches COM."""
import json
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge

class FakeWire:
    is_open = True
    def __init__(self): self.serial = None
    def write(self, data):
        if data.decode().strip() != 'GET_TELEMETRY': return
        def reply():
            sample = int(time.monotonic() * 2) * 500
            payload = {'deviceId':'1001','mode':'inference','uptimeMs':sample,
                       'telemetry':{'valid':True,'sampleMs':sample,'sensorVoltage':[.01]*8,
                                    'sensorGain':[1]*8,'sensorStatus':[0]*8,
                                    'featureOrder':['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2']}}
            line = 'GLD_TELEMETRY_JSON ' + json.dumps(payload, separators=(',', ':'))
            meta = self.serial._record_line(line)
            self.serial._emit('serial_line', {'line':line, **meta})
        timer = threading.Timer(.01, reply); timer.daemon = True; timer.start()
    def flush(self): pass
    def close(self): self.is_open = False

wire = FakeWire()
serial = bridge.SerialBridge(bridge.events, slot=1)
serial._serial = wire; serial.port = 'COM999'; wire.serial = serial
bridge.serial_bridges[1] = serial
class IsolatedHandler(bridge.Handler):
    def do_GET(self):
        if urlparse(self.path).path == '/js/bridge-client.js':
            source = (bridge.APP_DIR / 'js' / 'bridge-client.js').read_text(encoding='utf-8')
            source = source.replace('const DEFAULT_BRIDGE_ORIGIN = "http://127.0.0.1:5174";',
                                    'const DEFAULT_BRIDGE_ORIGIN = location.origin;')
            data = source.encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','text/javascript')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        return super().do_GET()

server = bridge.ExclusiveThreadingHTTPServer(('127.0.0.1', 0), IsolatedHandler)
bridge._register_allowed_origins('127.0.0.1', server.server_port)
print(server.server_port, flush=True)
try: server.serve_forever()
finally: server.server_close(); serial.disconnect()
