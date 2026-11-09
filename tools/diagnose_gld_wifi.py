"""Read-only PC-side Dataset Wi-Fi check for a selected GLD.

This opens a WebSocket only after the selected SSID and on-link route are
verified. It receives Hello, sends no Dataset controls, and never opens COM.
"""

import argparse
import base64
import datetime as dt
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=12,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Windows network query failed")
    return result.stdout


def associated(ssid):
    output = command(["netsh", "wlan", "show", "interfaces"])
    return ssid in re.findall(r"^\s*SSID\s*:\s*(.*?)\s*$", output, re.M)


def on_link():
    output = command(["powershell", "-NoProfile", "-Command",
                      "Find-NetRoute -RemoteIPAddress 192.168.4.1 | "
                      "Select-Object IPAddress,NextHop,DestinationPrefix | ConvertTo-Json -Compress"])
    values = json.loads(output)
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        return False
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            address = ipaddress.ip_address(value.get("IPAddress", ""))
        except ValueError:
            continue
        if (address in ipaddress.ip_network("192.168.4.0/24") and
                address != ipaddress.ip_address("192.168.4.1") and
                value.get("DestinationPrefix") == "192.168.4.0/24" and
                value.get("NextHop") == "0.0.0.0"):
            return True
    return False


def hub_busy():
    try:
        health = json.load(opener.open("http://127.0.0.1:5174/api/health", timeout=3))
    except urllib.error.URLError:
        return False  # No Hub is running on this PC.
    request = urllib.request.Request("http://127.0.0.1:5174/api/dataset-workflow/state",
                                     headers={"X-GLD-Bridge-Token": health["csrfToken"]})
    state = json.load(opener.open(request, timeout=3))
    return bool(state.get("connected") or state.get("cleanup_pending") or
                state.get("state") in {"connecting", "recording", "starting", "paused",
                                       "recovering", "replaying", "stopping", "stop_pending"})


def diagnose(device_id, wait_seconds):
    ssid = f"GLD-DATASET-{device_id}"
    result = {"capturedAt": dt.datetime.now().astimezone().isoformat(),
              "target": ssid, "diagnosticVersion": 3, "stage": "wait_association",
              "commandsSent": [], "wifiChanged": False, "serialOpened": False,
              "configurationChanged": False}
    deadline = time.monotonic() + wait_seconds
    while True:
        if associated(ssid) and on_link():
            break
        if time.monotonic() >= deadline:
            result["outcome"] = "target_association_or_dhcp_not_observed"
            return result
        time.sleep(1)
    result.update(associated=True, directSubnetRoute=True, stage="check_workspace")
    if hub_busy():
        result["outcome"] = "workspace_already_connected_or_busy_no_probe"
        return result
    try:
        result["stage"] = "tcp81"
        with socket.create_connection(("192.168.4.1", 81), timeout=5):
            pass
        result["tcp81"] = "reachable"
    except OSError as error:
        result.update(outcome="tcp_unreachable", errorClass=type(error).__name__,
                      errorNumber=getattr(error, "winerror", None))
        return result
    if not associated(ssid) or not on_link():
        result["outcome"] = "network_changed_before_authentication"
        return result
    sys.path.insert(0, str(ROOT / "apps/gld-operator"))
    from workflow_credentials import resolve_workflow_password
    from wireless_dataset import _transport_factory
    password = resolve_workflow_password(ROOT)
    authorization = base64.b64encode(("gld:" + password).encode("ascii")).decode("ascii")
    ws = None
    try:
        result["stage"] = "websocket_handshake"
        ws = _transport_factory("ws://192.168.4.1:81/dataset", timeout=5,
                                header=["Authorization: Basic " + authorization],
                                http_no_proxy=["*"], redirect_limit=0,
                                enable_multithread=True)
        result["stage"] = "receive_hello"
        raw = ws.recv()
        if not isinstance(raw, str) or len(raw) > 16384:
            raise ValueError("Invalid Hello frame")
        hello = json.loads(raw)
        permitted = ("type", "protocol", "device_id", "ready", "reason",
                     "nulling_profile_id", "interval_ms", "retention_ms", "capacity",
                     "sampling", "paused", "incomplete", "oldest_seq", "acked_next_seq",
                     "total_samples", "prediction_ready", "prediction_enabled", "transition_seq")
        result["hello"] = {key: hello.get(key) for key in permitted}
        result["model"] = {key: hello.get("model", {}).get(key) for key in
                           ("profile_id", "scaler_profile_id", "production_approved",
                            "runtime_version", "output_elements", "class_map")}
        result["capabilities"] = {key: hello.get("capabilities", {}).get(key) for key in
                                  ("pause", "continue", "durable_replay",
                                   "requires_protocol3_client", "prediction")}
        result["outcome"] = "hello_received"
        from wireless_dataset_workflow import WorkflowCollector
        from wireless_dataset_replay import ProtocolError
        probe = WorkflowCollector(ROOT / "output" / "diagnostics" / "unused",
                                  persist=lambda *args: None, cutoff=lambda *args: None,
                                  expected_device_id=device_id, autostart_worker=False)
        try:
            probe._hello(hello, False)
            result.update(protocolCheck="PASS", effectiveReady=probe.ready,
                          deviceReason=probe.error)
        except ProtocolError as error:
            result.update(protocolCheck="REJECTED", deviceReason=str(error))
    except Exception as error:
        result.update(outcome="websocket_or_hello_failed", errorClass=type(error).__name__,
                      httpStatus=getattr(error, "status_code", None))
    finally:
        if ws is not None:
            ws.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True, type=str,
                        help="GLD ID, e.g. 1002 (do not include GLD-DATASET-)")
    parser.add_argument("--wait-seconds", type=int, default=30)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{4,6}", args.device_id):
        parser.error("device ID must be 4-6 digits")
    if not 0 <= args.wait_seconds <= 600:
        parser.error("wait-seconds must be 0-600")
    report_dir = ROOT / "output" / "diagnostics"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"gld-wifi-{args.device_id}-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    print(f"Memeriksa {args.device_id}: SSID, rute lokal, TCP 81 dan Hello (baca saja).", flush=True)
    try:
        result = diagnose(args.device_id, args.wait_seconds)
    except Exception as error:
        result = {"outcome": "diagnostic_failed", "errorClass": type(error).__name__,
                  "commandsSent": [], "wifiChanged": False, "serialOpened": False,
                  "configurationChanged": False}
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Hasil: {result['outcome']}; laporan: {report_path}", flush=True)
    return 0 if result["outcome"] == "hello_received" and result.get("protocolCheck") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
