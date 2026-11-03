"""Visible one-shot connection regression; no recording, COM or Wi-Fi changes.

Run --smoke for a synthetic loopback-only transport test. Hardware execution
requires --run-real; root/operator launches that mode in a visible console.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "apps/gld-operator"))
from wireless_dataset import _transport_factory, FEATURE_ORDER
from wireless_dataset_workflow import WorkflowCollector
from wireless_dataset_replay import ProtocolError
from workflow_credentials import resolve_workflow_password
import workflow_platform as wlan

DEVICE = "1002"
SSID = "GLD-DATASET-1002"
MODEL = "cnn-dualbranch-board-2-2class-v2"
ENDPOINT = "ws://192.168.4.1:81/dataset"
ADDRESS = ("192.168.4.1", 81)
HUB = "http://127.0.0.1:5174"
REPORT = HERE / "real-connection-result.json"
ACTIVE = {"connecting", "starting", "recording", "pausing", "paused", "continuing", "resuming",
          "recovering", "reconnecting", "replaying", "stopping", "stop_pending", "cleanup_wait", "cleanup_pending"}


class CheckFailure(Exception):
    pass


def failure_code(error):
    if isinstance(error, CheckFailure):
        return str(error)  # Only this script's fixed literals construct it.
    if isinstance(error, ProtocolError):
        return "hello_protocol_validation_failed"
    if isinstance(error, TimeoutError) or type(error).__name__ == "WebSocketTimeoutException":
        return "transport_timeout"
    if isinstance(error, ConnectionRefusedError):
        return "connection_refused"
    if getattr(error, "status_code", None) in (401, 403):
        return "authentication_rejected"
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "invalid_response"
    return "check_failed"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def local_api(path, payload=None):
    """Only loopback Hub calls; credentials/tokens never enter reports."""
    with OPENER.open(HUB + "/api/health", timeout=2) as response:
        health = json.load(response)
    if health.get("appId") != "gld-operator":
        raise CheckFailure("unexpected_local_bridge")
    token = health.get("csrfToken")
    if not isinstance(token, str) or len(token) < 16:
        raise CheckFailure("local_bridge_token_unavailable")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(HUB + path, data=data,
        headers={"X-GLD-Bridge-Token": token, "Content-Type": "application/json"})
    with OPENER.open(request, timeout=12 if payload is not None else 2) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise CheckFailure("invalid_local_bridge_response")
    return result, health


def busy(state):
    return bool(state.get("connected") or state.get("cleanup_pending") or state.get("recovery_active") or
                state.get("state") in ACTIVE or state.get("stop_pending") or state.get("stop_requested"))


def idle_workspace():
    state, health = local_api("/api/dataset-workflow/state")
    if health.get("slots") or busy(state) or state.get("csv_path") or state.get("ledger_path") or state.get("locked"):
        raise CheckFailure("workspace_or_com_busy_no_probe")
    for path in ("/api/wireless-dataset/state", "/api/wireless-replay/state"):
        other, _ = local_api(path)
        if busy(other):
            raise CheckFailure("legacy_collector_busy_no_probe")
    return state


def associated_guids():
    """Native WLAN query only: never scan, set a profile or join a network."""
    if sys.platform != "win32":
        raise CheckFailure("windows_required")
    api = wlan._wlan_api()
    handle, version, listing = wintypes.HANDLE(), wintypes.DWORD(), ctypes.c_void_p()
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        raise CheckFailure("wlan_query_unavailable")
    try:
        if api.WlanEnumInterfaces(handle, None, ctypes.byref(listing)) or not listing.value:
            raise CheckFailure("wlan_query_unavailable")
        count = ctypes.c_uint32.from_address(listing.value).value
        if not 0 <= count <= 4096:
            raise CheckFailure("invalid_wlan_inventory")
        result = set()
        for index in range(count):
            interface = wlan._Interface.from_address(listing.value + 8 + index * ctypes.sizeof(wlan._Interface))
            if interface.state == 1 and wlan._connection_ssid(api, handle, interface.guid) == SSID.encode("ascii"):
                result.add(str(uuid.UUID(bytes_le=bytes(interface.guid))).lower())
        return result
    finally:
        if listing.value:
            api.WlanFreeMemory(listing)
        api.WlanCloseHandle(handle, None)


def route_matches(guids, snapshot):
    adapters = {int(item["ifIndex"]) for item in snapshot.get("adapters", [])
                if str(item.get("InterfaceGuid", "")).strip("{}").lower() in guids}
    target = ipaddress.ip_address(ADDRESS[0])
    routes = [item for item in snapshot.get("routes", [])
              if target in ipaddress.ip_network(item["DestinationPrefix"], strict=False)]
    if not routes:
        return False
    longest = max(ipaddress.ip_network(item["DestinationPrefix"], strict=False).prefixlen for item in routes)
    # Require a unique unambiguous directly attached target subnet. A VPN or
    # another adapter with an equal/more-specific target route fails closed.
    best = [item for item in routes if ipaddress.ip_network(item["DestinationPrefix"], strict=False).prefixlen == longest]
    if longest != 24 or any(int(item["InterfaceIndex"]) not in adapters or item.get("NextHop") != "0.0.0.0" for item in best):
        return False
    return any(int(item["InterfaceIndex"]) in adapters and int(item["PrefixLength"]) == 24 and
               ipaddress.ip_address(item["IPAddress"]) in ipaddress.ip_network("192.168.4.0/24") and
               item["IPAddress"] not in {"192.168.4.0", "192.168.4.1", "192.168.4.255"}
               for item in snapshot.get("addresses", []))


def network_guard():
    guids = associated_guids()
    if not guids:
        raise CheckFailure("waiting_target_ssid")
    command = ("$ErrorActionPreference='Stop'; @{adapters=@(Get-NetAdapter -IncludeHidden | Select-Object ifIndex,InterfaceGuid);"
               "routes=@(Get-NetRoute -AddressFamily IPv4 | Select-Object InterfaceIndex,DestinationPrefix,NextHop);"
               "addresses=@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceIndex,IPAddress,PrefixLength)}"
               " | ConvertTo-Json -Depth 4 -Compress")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or not route_matches(guids, json.loads(result.stdout)):
        raise CheckFailure("waiting_direct_target_route")
    # Association could change while PowerShell gathers its route snapshot.
    if not guids.intersection(associated_guids()):
        raise CheckFailure("network_changed_no_probe")
    return {"ssid": SSID, "directSubnetRoute": True}


def probe_guard():
    state = idle_workspace()
    network_guard()  # Fresh association/route immediately before socket/auth.
    return state


def validate_hello(message):
    collector = WorkflowCollector(HERE, persist=lambda *_:None, cutoff=lambda *_:None,
        expected_device_id=DEVICE, autostart_worker=False)
    collector._hello(message, False)  # No connect/Start/worker/file/ACK.
    if (not collector.ready or collector.sampling or collector.paused or collector.total_samples or
            message.get("session_id") or message.get("incomplete")):
        raise CheckFailure("hello_not_idle_and_ready")
    model = collector.model
    if collector.nulling_profile_id != 2:
        raise CheckFailure("unexpected_nulling_profile")
    if model.get("profile_id") != MODEL or model.get("scaler_profile_id") != MODEL:
        raise CheckFailure("unexpected_model")
    if model.get("production_approved") is not True or message.get("prediction_ready") is not True:
        raise CheckFailure("model_prediction_not_ready")
    return {"protocol": "gld-dataset-wifi/3", "device_id": collector.device_id, "boot_id": collector.boot_id,
        "ready": collector.ready, "nulling_profile_id": collector.nulling_profile_id,
        "model_profile": MODEL, "production_approved": True, "prediction_ready": True,
        "runtime_version": model.get("runtime_version"), "sampling": False, "paused": False}


def healthy_hello(endpoint, guard, password_loader, deadline=None):
    guard()
    password = password_loader()  # Real resolver only after route/SSID checks.
    authorization = base64.b64encode(("gld:" + password).encode("ascii")).decode("ascii")
    remaining = lambda: 3.0 if deadline is None else max(0.0, deadline - time.monotonic())
    if remaining() < .2:
        raise CheckFailure("post_abort_deadline_exceeded")
    ws = None
    try:
        ws = _transport_factory(endpoint, timeout=min(3.0, remaining()), enable_multithread=True,
            header=["Authorization: Basic " + authorization], http_no_proxy=["*"], redirect_limit=0)
        if remaining() <= 0:
            raise CheckFailure("post_abort_deadline_exceeded")
        ws.settimeout(min(3.0, remaining()))
        raw = ws.recv()
        if not isinstance(raw, str) or len(raw) > 16384:
            raise CheckFailure("invalid_hello_frame")
        summary = validate_hello(json.loads(raw))
        if deadline is not None and time.monotonic() > deadline:
            raise CheckFailure("post_abort_deadline_exceeded")
        return summary
    finally:
        if ws is not None:
            try:
                ws.close(timeout=.1)
            finally:
                ws.shutdown()


def aborted_header(address, guard):
    guard()
    with socket.create_connection(address, timeout=2) as connection:
        connection.sendall(b"GET /dataset HTTP/1.1\r\nHost: 192.168.4.1:81\r\nX-GLD-Partial: pending")
        time.sleep(.1)  # Deliberate unfinished header line, then close.
    return time.monotonic()


def workspace_connect_check(expected_boot):
    state = probe_guard()
    if state.get("selected_device_id") != DEVICE or state.get("selected_ssid") != SSID:
        return {"outcome": "skipped_device_not_selected", "disconnected_verified": True}
    attempted = False
    answer = {"outcome": "checking", "disconnected_verified": False}
    try:
        attempted = True
        result, _ = local_api("/api/dataset-workflow/connect", {"device_id": DEVICE})
        state, _ = local_api("/api/dataset-workflow/state")
        if (not state.get("connected") or not state.get("ready") or state.get("device_id") != DEVICE or
                state.get("boot_id") != expected_boot):
            raise CheckFailure("workspace_not_ready")
        if state.get("nulling_profile_id") != 2 or not state.get("prediction_available"):
            raise CheckFailure("workspace_prediction_or_profile_not_ready")
        answer.update(outcome="ready", device_id=DEVICE, ready=True,
                      nulling_profile_id=2, prediction_available=True, count=state.get("count"))
        return answer
    finally:
        if attempted:
            # Reconcile even a lost Connect response. Never retry Connect or
            # close a session that became active/changed while this check ran.
            state, _ = local_api("/api/dataset-workflow/state")
            if not state.get("connected"):
                answer["disconnected_verified"] = True
            elif (state.get("boot_id") == expected_boot and state.get("device_id") == DEVICE and
                    not state.get("session_id") and not state.get("count")
                    and not state.get("csv_path") and not state.get("cleanup_pending") and state.get("state") not in ACTIVE):
                local_api("/api/dataset-workflow/disconnect", {})
                final, _ = local_api("/api/dataset-workflow/state")
                if final.get("connected") or final.get("cleanup_pending"):
                    raise CheckFailure("workspace_disconnect_unconfirmed")
                answer["disconnected_verified"] = True
            else:
                raise CheckFailure("workspace_changed_connection_not_stolen")


def write_report(result):
    temporary = REPORT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(REPORT)


def run_real(use_workspace=False):
    result = {"capturedAt": datetime.datetime.now().astimezone().isoformat(), "target": SSID,
        "commandsSent": [], "wifiChanged": False, "serialOpened": False,
        "recordingStarted": False, "csvWritten": False, "stages": [], "outcome": "running",
        "safe_to_return_internet": not use_workspace}
    def stage(name, **values):
        result["stages"].append({"stage": name, **values}); write_report(result)
        print(name, flush=True)
    print("PEMERIKSAAN KONEKSI GLD - MODEL 2", flush=True)
    print("Hubungkan Windows ke GLD-DATASET-1002. Biarkan Hub terbuka dan jangan mulai rekaman selama pemeriksaan.", flush=True)
    print("Script tidak mengganti Wi-Fi, membuka COM atau merekam data.", flush=True)
    try:
        stage("waiting_ssid_and_direct_route")
        end = time.monotonic() + 600
        while True:
            try:
                network_guard(); break
            except CheckFailure as error:
                if str(error) not in {"waiting_target_ssid", "waiting_direct_target_route", "network_changed_no_probe"}:
                    raise
            if time.monotonic() >= end:
                raise CheckFailure("association_or_route_not_observed")
            time.sleep(1)
        stage("workspace_idle_guard")
        probe_guard()
        stage("hello_before")
        result["hello_before"] = healthy_hello(ENDPOINT, probe_guard, lambda:resolve_workflow_password(ROOT))
        stage("hello_before_ok")
        time.sleep(.2)
        stage("partial_header_abort")
        aborted_at = aborted_header(ADDRESS, probe_guard)
        stage("hello_after_abort")
        result["hello_after"] = healthy_hello(ENDPOINT, probe_guard,
            lambda:resolve_workflow_password(ROOT), deadline=aborted_at + 5)
        result["post_abort_elapsed_ms"] = round((time.monotonic() - aborted_at) * 1000)
        if result["post_abort_elapsed_ms"] > 5000:
            raise CheckFailure("post_abort_deadline_exceeded")
        stage("hello_after_abort_ok", elapsed_ms=result["post_abort_elapsed_ms"])
        if use_workspace:
            stage("workspace_connect_check")
            result["workspace"] = workspace_connect_check(result["hello_after"]["boot_id"])
            result["safe_to_return_internet"] = result["workspace"]["disconnected_verified"]
        result["outcome"] = "passed"
        stage("complete")
    except Exception as error:
        result["outcome"] = "skipped" if isinstance(error, CheckFailure) and "busy" in str(error) else "failed"
        result["failure_code"] = failure_code(error)
        stage("finished_without_recording", code=result["failure_code"])
    finally:
        write_report(result)
    print("Hasil:", result["outcome"], "| laporan:", REPORT, flush=True)
    return result


def fixture_hello():
    return {"type":"hello", "protocol":"gld-dataset-wifi/3", "device_id":DEVICE, "boot_id":"a"*32,
        "session_id":"", "label":"", "ready":True, "nulling_profile_id":2,
        "interval_ms":500, "retention_ms":300000, "capacity":640, "feature_order":list(FEATURE_ORDER),
        "sampling":False, "paused":False, "incomplete":False, "total_samples":0, "oldest_seq":0,
        "acked_next_seq":0, "transition_seq":0, "prediction_enabled":False, "prediction_ready":True,
        "capabilities":{"pause":True, "continue":True, "durable_replay":True, "prediction":True, "requires_protocol3_client":True},
        "model":{"profile_id":MODEL, "scaler_profile_id":MODEL, "runtime_version":"synthetic-smoke",
            "production_approved":True, "output_elements":2, "class_map":[0,1]}}


def smoke():
    """Real vendored transport, synthetic password, loopback ephemeral only."""
    password = "synthetic-smoke-only"
    expected = "Basic " + base64.b64encode(("gld:"+password).encode()).decode()
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            headers = {}
            for _ in range(80):
                line = self.rfile.readline(8192)
                if not line: return  # Controlled partial-header abort.
                if line == b"\r\n": break
                if b":" in line:
                    key,value=line.decode("ascii").split(":",1); headers[key.lower()]=value.strip()
            if headers.get("authorization") != expected:
                self.wfile.write(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n"); return
            key=headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept=base64.b64encode(hashlib.sha1(key.encode()).digest())
            self.wfile.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+accept+b"\r\n\r\n")
            payload=json.dumps(fixture_hello()).encode()
            self.wfile.write(b"\x81\x7e"+struct.pack("!H",len(payload))+payload); self.wfile.flush()
    server=socketserver.ThreadingTCPServer(("127.0.0.1",0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    endpoint=f"ws://127.0.0.1:{server.server_address[1]}/dataset"
    try:
        first=healthy_hello(endpoint,lambda:None,lambda:password)
        aborted_at=aborted_header(server.server_address,lambda:None)
        second=healthy_hello(endpoint,lambda:None,lambda:password,deadline=aborted_at+5)
        assert first["ready"] and second["ready"]
        guid="a"*32
        snapshot={"adapters":[{"ifIndex":10,"InterfaceGuid":guid}],
            "routes":[{"InterfaceIndex":10,"DestinationPrefix":"192.168.4.0/24","NextHop":"0.0.0.0"}],
            "addresses":[{"InterfaceIndex":10,"PrefixLength":24,"IPAddress":"192.168.4.2"}]}
        assert route_matches({guid},snapshot)
        assert not route_matches({"wrong-adapter"},snapshot)
        snapshot["routes"].append({"InterfaceIndex":11,"DestinationPrefix":"192.168.4.1/32","NextHop":"0.0.0.0"})
        assert not route_matches({guid},snapshot)
        print("PASS offline: actual vendored WS101 + actual Workflow Hello validator, partial-header close + next Hello, adapter/route guards; synthetic credentials only.")
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke",action="store_true")
    mode.add_argument("--run-real",action="store_true")
    parser.add_argument("--hub-connect",action="store_true",help="also check already-selected Workspace Connect, then Disconnect")
    args=parser.parse_args()
    if args.smoke:
        smoke(); return 0
    result = {}
    try:
        result=run_real(args.hub_connect)
        return 0 if result["outcome"] == "passed" else 1
    finally:
        message = ("Pemeriksaan selesai. Anda dapat kembali ke jaringan Internet. " if result.get("safe_to_return_internet") else
                   "Pemeriksaan selesai. Pastikan Workspace sudah Disconnect sebelum kembali ke Internet. ")
        try: input(message + "Tekan Enter untuk menutup jendela…")
        except (EOFError,KeyboardInterrupt): pass


if __name__ == "__main__":
    raise SystemExit(main())
