"""Windows conveniences for explicit operator actions; no actions at import.

Tests/simulators inject a platform instead. Never log passwords or put a WLAN
profile password on a command line or in a temporary plaintext file.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
from xml.sax.saxutils import escape

SSID_PATTERN = re.compile(r"GLD-DATASET-([0-9A-Fa-f]{4})\Z")
GLD_ROUTE_WAIT_SECONDS = 8.0


class WorkflowNetworkNotReady(RuntimeError):
    workflow_code = "wifi_route_not_ready"


# Native layouts follow wlanapi.h. Keep them separate from the file dialog ABI.
class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                ("d", ctypes.c_ubyte * 8)]


class _Interface(ctypes.Structure):
    _fields_ = [("guid", _GUID), ("description", wintypes.WCHAR * 256), ("state", wintypes.DWORD)]


class _SSID(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("value", ctypes.c_ubyte * 32)]


class _AvailableNetwork(ctypes.Structure):
    _fields_ = [("profile", wintypes.WCHAR * 256), ("ssid", _SSID), ("bss", wintypes.DWORD),
                ("bssids", wintypes.DWORD), ("connectable", wintypes.BOOL), ("reason", wintypes.DWORD),
                ("phy_count", wintypes.DWORD), ("phy_types", wintypes.DWORD * 8),
                ("more_phys", wintypes.BOOL), ("quality", wintypes.DWORD), ("security", wintypes.BOOL),
                ("auth", wintypes.DWORD), ("cipher", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("reserved", wintypes.DWORD)]


class _Association(ctypes.Structure):
    _fields_ = [("ssid", _SSID), ("bss", wintypes.DWORD), ("bssid", ctypes.c_ubyte * 6),
                ("phy", wintypes.DWORD), ("phy_index", wintypes.DWORD), ("quality", wintypes.DWORD),
                ("rx_rate", wintypes.DWORD), ("tx_rate", wintypes.DWORD)]


class _Security(ctypes.Structure):
    _fields_ = [("enabled", wintypes.BOOL), ("one_x", wintypes.BOOL),
                ("auth", wintypes.DWORD), ("cipher", wintypes.DWORD)]


class _Connection(ctypes.Structure):
    _fields_ = [("state", wintypes.DWORD), ("mode", wintypes.DWORD),
                ("profile", wintypes.WCHAR * 256), ("association", _Association), ("security", _Security)]


class _Parameters(ctypes.Structure):
    _fields_ = [("mode", ctypes.c_int), ("profile", wintypes.LPCWSTR), ("ssid", ctypes.c_void_p),
                ("desired", ctypes.c_void_p), ("bss", ctypes.c_int), ("flags", wintypes.DWORD)]


class _ProfileInfo(ctypes.Structure):
    _fields_ = [("name", wintypes.WCHAR * 256), ("flags", wintypes.DWORD)]


def _ssid_bytes(value):
    return bytes(value.value[:value.length]) if value.length <= 32 else b""


def _wlan_api():
    api = ctypes.WinDLL("wlanapi", use_last_error=True)
    signatures = {
        "WlanOpenHandle": [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.HANDLE)],
        "WlanEnumInterfaces": [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        "WlanScan": [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
        "WlanGetAvailableNetworkList": [wintypes.HANDLE, ctypes.POINTER(_GUID), wintypes.DWORD,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        "WlanGetProfileList": [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.c_void_p,
                               ctypes.POINTER(ctypes.c_void_p)],
        "WlanQueryInterface": [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.c_int, ctypes.c_void_p,
                               ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p],
        "WlanSetProfile": [wintypes.HANDLE, ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.LPCWSTR,
                           wintypes.LPCWSTR, wintypes.BOOL, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)],
        "WlanConnect": [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.POINTER(_Parameters), ctypes.c_void_p],
        "WlanFreeMemory": [ctypes.c_void_p],
        "WlanCloseHandle": [wintypes.HANDLE, ctypes.c_void_p],
    }
    for name, arguments in signatures.items():
        function = getattr(api, name)
        function.argtypes = arguments
        function.restype = None if name == "WlanFreeMemory" else wintypes.DWORD
    return api


def _connection_ssid(api, handle, guid):
    data, size = ctypes.c_void_p(), wintypes.DWORD()
    try:
        result = api.WlanQueryInterface(handle, ctypes.byref(guid), 7, None,
                                        ctypes.byref(size), ctypes.byref(data), None)
        if result == 5023:  # ERROR_INVALID_STATE: association has not completed.
            return b""
        if result or not data.value or size.value < ctypes.sizeof(_Connection):
            raise RuntimeError("Status adaptor Wi-Fi belum dapat diperiksa. Periksa izin lokasi Windows.")
        connection = _Connection.from_address(data.value)
        return _ssid_bytes(connection.association.ssid) if connection.state == 1 else b""
    finally:
        if data.value:
            api.WlanFreeMemory(data)


def _visible_quality(api, handle, guid, target):
    listing = ctypes.c_void_p()
    try:
        result = api.WlanGetAvailableNetworkList(handle, ctypes.byref(guid), 0, None, ctypes.byref(listing))
        if result or not listing.value:
            return None
        count = ctypes.c_uint32.from_address(listing.value).value
        if count > 65536:
            raise RuntimeError("Daftar jaringan Wi-Fi Windows tidak valid.")
        qualities = []
        for index in range(count):
            network = _AvailableNetwork.from_address(listing.value + 8 + index * ctypes.sizeof(_AvailableNetwork))
            if network.bss == 1 and network.connectable and _ssid_bytes(network.ssid) == target:
                qualities.append(network.quality)
        return max(qualities) if qualities else None
    finally:
        if listing.value:
            api.WlanFreeMemory(listing)


def _profile_flags(api, handle, guid, name):
    """Preserve exact target profile scope without requesting its XML or key."""
    listing = ctypes.c_void_p()
    try:
        result = api.WlanGetProfileList(handle, ctypes.byref(guid), None, ctypes.byref(listing))
        if result or not listing.value:
            raise RuntimeError("Daftar profil hotspot belum dapat diperiksa. Periksa izin Wi-Fi Windows.")
        count = ctypes.c_uint32.from_address(listing.value).value
        if count > 65536:
            raise RuntimeError("Daftar profil Wi-Fi Windows tidak valid.")
        matching = []
        for index in range(count):
            profile = _ProfileInfo.from_address(listing.value + 8 + index * ctypes.sizeof(_ProfileInfo))
            if profile.name == name:
                matching.append(profile.flags)
        if any(flags & 1 for flags in matching):
            raise RuntimeError("Profil hotspot GLD dikelola Group Policy Windows dan tidak dapat diubah oleh Operator Hub.")
        if len(matching) > 1 or any(flags not in (0, 2) for flags in matching):
            raise RuntimeError("Jenis profil hotspot GLD belum dapat dipastikan. Periksa profil Wi-Fi Windows.")
        return matching[0] if matching else 2  # New profiles remain per-user.
    finally:
        if listing.value:
            api.WlanFreeMemory(listing)


def validate_ssid(ssid):
    match = SSID_PATTERN.fullmatch(ssid) if isinstance(ssid, str) else None
    if not match:
        raise ValueError("Pilih hotspot GLD dari hasil Scan Nearby GLD.")
    return match[1].upper()


def parse_scan(text):
    found = {}
    for line in text.splitlines():
        match = re.match(r"\s*SSID\s+\d+\s*:\s*(.*?)\s*$", line)
        if not match or not SSID_PATTERN.fullmatch(match[1]):
            continue
        ssid = match[1]
        identifier = validate_ssid(ssid)
        found[ssid] = dict(ssid=ssid, device_id=identifier, name=f"GLD-{identifier}")
    return sorted(found.values(), key=lambda item: (item["device_id"], item["ssid"]))


def profile_xml(ssid, password):
    validate_ssid(ssid)
    if not isinstance(password, str) or not 8 <= len(password) <= 63 or any(not 32 <= ord(c) <= 126 for c in password):
        raise ValueError("Password hotspot harus berisi 8–63 karakter ASCII.")
    name, secret = escape(ssid), escape(password)
    return ('<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
            f'<name>{name}</name><SSIDConfig><SSID><name>{name}</name></SSID></SSIDConfig>'
            '<connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security>'
            '<authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption>'
            '<useOneX>false</useOneX></authEncryption><sharedKey><keyType>passPhrase</keyType>'
            f'<protected>false</protected><keyMaterial>{secret}</keyMaterial></sharedKey>'
            '</security></MSM></WLANProfile>')


class WindowsWorkflowPlatform:
    def __init__(self, *, runner=subprocess.run, clock=time.monotonic, sleep=time.sleep,
                 route_probe=None):
        self._run, self._clock, self._sleep = runner, clock, sleep
        self._route_probe = route_probe

    def _route_ready(self, guid):
        if self._route_probe is not None:
            return bool(self._route_probe(guid))
        identifier = uuid.UUID(bytes_le=ctypes.string_at(ctypes.byref(guid), 16))
        # Association precedes Windows DHCP. Require the selected WLAN adapter
        # to own both the GLD subnet address and the best on-link route before
        # sending the private WebSocket Authorization header.
        script = (
            # Get-NetAdapter.InterfaceGuid is a string with braces, not Guid.
            f"$g='{{{identifier}}}';"
            "$a=Get-NetAdapter -IncludeHidden | Where-Object {$_.InterfaceGuid -eq $g} | Select-Object -First 1;"
            "if(-not $a){'WAIT';exit};"
            "$r=@(Find-NetRoute -RemoteIPAddress 192.168.4.1 -ErrorAction SilentlyContinue);"
            "$ip=@($r | Where-Object {$_.InterfaceIndex -eq $a.ifIndex -and "
            "$_.IPAddress -like '192.168.4.*' -and $_.IPAddress -ne '192.168.4.1'});"
            "$link=@($r | Where-Object {$_.InterfaceIndex -eq $a.ifIndex -and "
            "$_.DestinationPrefix -eq '192.168.4.0/24' -and $_.NextHop -eq '0.0.0.0'});"
            "if($ip.Count -gt 0 -and $link.Count -gt 0){'READY'}else{'WAIT'}"
        )
        return self._command(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-Command", script]).strip() == "READY"

    def _wait_for_route(self, api, handle, guid, target):
        deadline = self._clock() + GLD_ROUTE_WAIT_SECONDS
        while True:
            if _connection_ssid(api, handle, guid) != target:
                raise WorkflowNetworkNotReady("Koneksi hotspot GLD berubah sebelum IP siap.")
            if self._route_ready(guid):
                return
            if self._clock() >= deadline:
                raise WorkflowNetworkNotReady("Windows belum memperoleh IP/rute langsung ke GLD.")
            self._sleep(.25)

    def _command(self, arguments):
        if os.name != "nt":
            raise RuntimeError("Scan dan koneksi hotspot tersedia melalui backend Windows.")
        result = self._run(arguments, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("Windows belum dapat mengakses Wi-Fi. Periksa adaptor dan izin lokasi Windows.")
        return result.stdout

    def scan(self):
        if os.name != "nt":
            raise RuntimeError("Scan hotspot memerlukan backend Windows.")
        # netsh only reads the driver's cache, which can omit a newly started GLD.
        # Request a refresh on actual usable GUIDs, then allow the documented
        # four-second driver scan window before reading the resulting list.
        api = _wlan_api()
        handle, version, listing = wintypes.HANDLE(), wintypes.DWORD(), ctypes.c_void_p()
        if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
            raise RuntimeError("Windows WLAN belum tersedia.")
        try:
            if api.WlanEnumInterfaces(handle, None, ctypes.byref(listing)) or not listing.value:
                raise RuntimeError("Adaptor Wi-Fi tidak ditemukan.")
            count = ctypes.c_uint32.from_address(listing.value).value
            if count == 0 or count > 4096:
                raise RuntimeError("Adaptor Wi-Fi tidak ditemukan.")
            requested = False
            for index in range(count):
                interface = _Interface.from_address(listing.value + 8 + index * ctypes.sizeof(_Interface))
                if interface.state in (1, 4):
                    result = api.WlanScan(handle, ctypes.byref(interface.guid), None, None, None)
                    requested = requested or result == 0
            if not requested:
                raise RuntimeError("Scan Wi-Fi belum dapat dimulai. Periksa adaptor dan izin lokasi Windows.")
            self._sleep(4.0)
        finally:
            if listing.value:
                api.WlanFreeMemory(listing)
            api.WlanCloseHandle(handle, None)
        return parse_scan(self._command(["netsh", "wlan", "show", "networks", "mode=bssid"]))

    def current_ssid(self):
        # Diagnostic only: multiple active adapters have no single current SSID.
        # join() uses a native query on its selected GUID instead.
        text = self._command(["netsh", "wlan", "show", "interfaces"])
        ssids = set(re.findall(r"^\s*SSID\s*:\s*(.*?)\s*$", text, re.MULTILINE))
        return next(iter(ssids)) if len(ssids) == 1 else ""

    def join(self, ssid, password=""):
        validate_ssid(ssid)
        if os.name != "nt":
            raise RuntimeError("Koneksi hotspot memerlukan backend Windows.")
        # Native WLAN API keeps profile secrets in memory and Windows storage.
        api = _wlan_api()
        handle, version, listing = wintypes.HANDLE(), wintypes.DWORD(), ctypes.c_void_p()
        if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
            raise RuntimeError("Windows WLAN belum tersedia.")
        try:
            if api.WlanEnumInterfaces(handle, None, ctypes.byref(listing)) or not listing.value:
                raise RuntimeError("Adaptor Wi-Fi tidak ditemukan.")
            count = ctypes.c_uint32.from_address(listing.value).value
            if count == 0 or count > 4096:
                raise RuntimeError("Adaptor Wi-Fi tidak ditemukan.")
            target = ssid.encode("ascii")
            candidates = []
            for index in range(count):
                interface = _Interface.from_address(listing.value + 8 + index * ctypes.sizeof(_Interface))
                # Do not commandeer disabled or transitional interfaces.
                if interface.state not in (1, 4):
                    continue
                guid = _GUID.from_buffer_copy(interface.guid)
                if interface.state == 1 and _connection_ssid(api, handle, guid) == target:
                    self._wait_for_route(api, handle, guid, target)
                    return dict(ssid=ssid, associated=True)
                quality = _visible_quality(api, handle, guid, target)
                if quality is not None:
                    # Prefer an unused adapter, preserving an existing network if possible.
                    candidates.append((interface.state != 4, -quality, index, guid))
            if not candidates:
                raise RuntimeError("Hotspot GLD tidak terlihat pada adaptor Wi-Fi yang tersedia. Scan lagi dan periksa daya serta izin lokasi Windows.")
            guid = min(candidates, key=lambda item: item[:3])[3]
            if password:
                reason = wintypes.DWORD()
                xml = profile_xml(ssid, password)
                flags = _profile_flags(api, handle, guid, ssid)
                result = api.WlanSetProfile(handle, ctypes.byref(guid), flags, xml, None,
                                           True, None, ctypes.byref(reason))
                if result == 183:
                    raise RuntimeError("Profil hotspot GLD berubah atau bertabrakan dengan profil Windows lain. Periksa profil lalu Connect kembali.")
                if result:
                    raise RuntimeError("Profil hotspot tidak dapat disimpan. Periksa password dan izin Wi-Fi.")
            params = _Parameters(0, ssid, None, None, 1, 0)
            if api.WlanConnect(handle, ctypes.byref(guid), ctypes.byref(params), None):
                raise RuntimeError("Tidak dapat menghubungkan hotspot. Isi password bila profil belum tersimpan.")
            end = self._clock() + 15
            while self._clock() < end:
                if _connection_ssid(api, handle, guid) == target:
                    self._wait_for_route(api, handle, guid, target)
                    return dict(ssid=ssid, associated=True)
                self._sleep(.25)
            raise RuntimeError("Hotspot belum terhubung. Periksa daya GLD, jarak, dan password.")
        finally:
            if listing.value:
                api.WlanFreeMemory(listing)
            api.WlanCloseHandle(handle, None)

    def choose_file(self):
        if os.name != "nt":
            raise RuntimeError("Pemilih file memerlukan backend Windows.")
        class OPENFILENAME(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("owner", wintypes.HWND), ("instance", wintypes.HINSTANCE),
                ("filter", wintypes.LPCWSTR), ("custom", wintypes.LPWSTR), ("maxcustom", wintypes.DWORD),
                ("filterindex", wintypes.DWORD), ("file", wintypes.LPWSTR), ("maxfile", wintypes.DWORD),
                ("filetitle", wintypes.LPWSTR), ("maxfiletitle", wintypes.DWORD), ("initial", wintypes.LPCWSTR),
                ("title", wintypes.LPCWSTR), ("flags", wintypes.DWORD), ("offset", wintypes.WORD),
                ("extension", wintypes.WORD), ("defext", wintypes.LPCWSTR), ("data", wintypes.LPARAM),
                ("hook", ctypes.c_void_p), ("template", wintypes.LPCWSTR), ("reserved", ctypes.c_void_p),
                ("reserved2", wintypes.DWORD), ("flags2", wintypes.DWORD)]
        filename = ctypes.create_unicode_buffer(32768)
        filename.value = "dataset-gld.csv"
        request = OPENFILENAME()
        request.size = ctypes.sizeof(request)
        request.filter = "CSV (*.csv)\0*.csv\0\0"
        request.file = ctypes.cast(filename, wintypes.LPWSTR)
        request.maxfile = len(filename)
        request.title = "Pilih lokasi dan nama CSV Dataset GLD"
        request.defext = "csv"
        request.flags = 0x80000 | 0x800 | 0x8 | 0x4  # Explorer, existing parent, no cwd change, hide readonly.
        api = ctypes.WinDLL("comdlg32", use_last_error=True)
        api.GetSaveFileNameW.argtypes = [ctypes.POINTER(OPENFILENAME)]
        api.GetSaveFileNameW.restype = wintypes.BOOL
        if not api.GetSaveFileNameW(ctypes.byref(request)):
            api.CommDlgExtendedError.restype = wintypes.DWORD
            if api.CommDlgExtendedError():
                raise RuntimeError("Pemilih file CSV tidak dapat dibuka.")
            return None
        return self.validate_file(filename.value)

    @staticmethod
    def validate_file(value):
        path = Path(value).expanduser()
        if not path.is_absolute() or path.suffix.lower() != ".csv" or not path.parent.is_dir():
            raise ValueError("Pilih nama file .csv di folder yang tersedia.")
        path = path.resolve()
        if path.exists():
            raise ValueError("File sudah ada. Pilih nama baru agar CSV lama tetap tersimpan.")
        try:
            with tempfile.NamedTemporaryFile(prefix=".gld-write-check-", dir=path.parent) as stream:
                stream.write(b"GLD"); stream.flush(); os.fsync(stream.fileno())
        except OSError:
            raise RuntimeError("Folder CSV tidak dapat ditulis.") from None
        return str(path)
