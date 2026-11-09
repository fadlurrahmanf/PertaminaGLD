"""Run the existing Hub with handover-only paths/ports; normal launcher unchanged."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import threading
import time


def configure_broker_host(hub, *, force_loopback=False):
    """Keep the handover stack usable when this PC has no LAN route.

    This override applies only to the handover wrapper. The ordinary Hub's
    LAN broker policy remains unchanged for normal device operation.
    """
    if force_loopback or hub.local_ipv4() is None:
        hub.local_ipv4 = lambda: '127.0.0.1'
        print('HANDOVER_MQTT_LOOPBACK_ONLY: broker untuk layanan lokal; perangkat luar perlu LAN.', flush=True)
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--hub-port', type=int, default=5173)
    parser.add_argument('--port-offset', type=int, default=0)
    parser.add_argument('--loopback-broker', action='store_true', help='isolated/offline local test only')
    args = parser.parse_args()
    path = args.repo_root / 'apps/operator-hub/bridge.py'
    spec = importlib.util.spec_from_file_location('handover_operator_hub', path)
    hub = importlib.util.module_from_spec(spec); sys.modules[spec.name] = hub; spec.loader.exec_module(hub)
    hub.RUNTIME_DIR = args.runtime_dir
    hub.BROKER_CREDENTIALS_PATH = args.runtime_dir / 'credentials.local.json'
    for cfg in hub.CHILD_APPS.values():
        cfg['port'] += args.port_offset
    configure_broker_host(hub, force_loopback=args.loopback_broker)
    servers = []
    original = hub.ExclusiveThreadingHTTPServer
    class ManagedServer(original):
        def __init__(self, *values, **options):
            super().__init__(*values, **options); servers.append(self)
    hub.ExclusiveThreadingHTTPServer = ManagedServer
    stop = args.runtime_dir / 'stop.request'
    def watch():
        while not stop.exists(): time.sleep(.25)
        for server in servers: server.shutdown()
    threading.Thread(target=watch, daemon=True).start()
    sys.argv = [str(path), '--host', '127.0.0.1', '--port', str(args.hub_port)]
    return hub.main()


if __name__ == '__main__':
    raise SystemExit(main())
