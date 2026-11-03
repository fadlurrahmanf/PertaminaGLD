"""Root-executed bounded Wi-Fi context; importing performs no OS/network action."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'firmware/.pio/gld-real-test-20261102'
sys.path.insert(0, str(BASE))
from run_hotspot_test import System as BaseSystem, Failure, profile_xml, write_json


class System(BaseSystem):
    def remove_profile(self, name, interface):
        if not name.startswith('Codex-GLD-dual-'):
            raise Failure('refuse_delete_nonowned_wifi_profile')
        return self.command(['netsh.exe', 'wlan', 'delete', 'profile', 'name=' + name,
                             'interface=' + interface])

    def arm_watchdog(self, state_path):
        flags = (getattr(subprocess, 'DETACHED_PROCESS', 0) |
                 getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) |
                 getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    '--watchdog', str(state_path)], cwd=HERE,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, creationflags=flags, shell=False)
        return process.pid


def restore(system, state, path):
    """Delete only this transaction's alias, only after original Wi-Fi proven."""
    original = state['original_wifi']
    result = dict(verified=False, temporary_profile_removed=False)
    try:
        system.connect_profile(original['profile'], original['name'])
        result['wifi'] = system.wait_wifi(original['name'], profile=original['profile'],
                                          ssid=original['ssid'], seconds=20)
        result['verified'] = True
        if state.get('profile_added'):
            try:
                system.remove_profile(state['temporary_profile'], original['name'])
                result['temporary_profile_removed'] = True
            except Exception:
                result['profile_cleanup_error'] = 'temporary_profile_removal_unconfirmed'
        state['watchdog_cancel'] = result['verified'] and (
            not state.get('profile_added') or result['temporary_profile_removed'])
        state['restoration'] = result
    except Exception:
        result['error'] = 'original_wifi_restoration_unconfirmed'
        state['restoration'] = result
    write_json(path, state)
    return result


class WifiVisit:
    def __init__(self, system, output, original, device_id, password):
        self.system, self.output, self.original = system, Path(output), original
        self.password, self.device_id = password, device_id
        self.output.mkdir(parents=True, exist_ok=True)
        self.path = self.output / 'restore-state.json'
        self.profile = 'Codex-GLD-dual-' + uuid.uuid4().hex[:10]
        self.state = dict(original_wifi=original, target_ssid='GLD-DATASET-' + device_id,
            temporary_profile=self.profile, created_unix_s=time.time(), watchdog_delay_s=90,
            watchdog_cancel=False, profile_added=False)
        self.network = []
        self.armed = False

    def join(self):
        write_json(self.path, self.state)
        self.state['watchdog_pid'] = self.system.arm_watchdog(self.path)
        self.armed = True
        write_json(self.path, self.state)
        xml = self.output / 'profile.private.xml'
        xml.write_bytes(profile_xml(self.profile, self.state['target_ssid'], self.password))
        # Track possible mutation BEFORE command; unknown add response still needs cleanup.
        self.state['profile_added'] = True
        write_json(self.path, self.state)
        self.system.add_profile(xml, self.original['name'])
        self.system.connect_profile(self.profile, self.original['name'])
        self.state['joined'] = self.system.wait_wifi(self.original['name'], profile=self.profile,
            ssid=self.state['target_ssid'], seconds=20)
        try:
            self.system.probe(self.original['name'], observe=self.network.append)
        finally:
            write_json(self.output / 'network-diagnostics.json', self.network)
        return self.state['joined']

    def close(self):
        if self.armed:
            return restore(self.system, self.state, self.path)
        return dict(verified=True, no_network_mutation=True)


def watchdog(path, system=None, wall=time.time):
    path = Path(path).resolve()
    if not path.is_relative_to((HERE / 'output').resolve()) or path.name != 'restore-state.json':
        raise Failure('watchdog_state_outside_owned_output')
    system = system or System()
    state = json.loads(path.read_text(encoding='utf-8'))
    deadline = state['created_unix_s'] + 90
    while wall() < deadline:
        try:
            latest = json.loads(path.read_text(encoding='utf-8'))
            if latest.get('watchdog_cancel'):
                return
            state = latest
        except (OSError, ValueError):
            pass
        system.sleep(0.5)
    # A cancellation written on the deadline boundary must not restore over a
    # later AP visit. Re-read before acting, as in the established watchdog.
    try:
        latest = json.loads(path.read_text(encoding='utf-8'))
        if latest.get('watchdog_cancel'):
            return
        state = latest
    except (OSError, ValueError):
        pass
    restore(system, state, path)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--watchdog':
        watchdog(sys.argv[2])
    else:
        raise SystemExit('Only root-created watchdog invocation is supported')
