# Codex Recovery Note - 2026-07-06 16:01

Scope: real GLD COM9 website dataset capture, no mock.

Status: paused by user because GLD battery is depleted.

Important note: `ActivityAI/codexactivity.md` appeared corrupted with NUL bytes during this run, so this separate recovery note was created instead of appending to that file.

What was verified:

- Old mock GLD process and old bridge instances were stopped before the real-device attempt.
- Local MQTT broker on the deployment-provisioned host and port `1884` was listening.
- GLD real device on COM9 initially responded over serial:
  - `deviceId=F001`
  - firmware `PertaminaGLD-GLD` version `0.8.12`
  - mode `inference`
  - WiFi SSID provisioned from the local secret configuration
  - MQTT host provisioned from the local deployment configuration
  - MQTT port `1884`
  - topic root `gas-leak-detector`
  - `configValid=true`
- Battery status before the failure was low/critical, around `3.2 V`.

Firmware/source work done:

- `firmware/gld/src/GldUnifiedMain.cpp`
  - Temporarily removed the battery-mode boot block that forced `dataset` and `nulling` back to `inference`.
  - Added `MODE_BATTERY_ALLOWED_TEMP mode=...`.
  - Moved TPL5010 keepalive to a shared path for battery modes.
  - Added follow-up keepalive support during setup-heavy paths:
    - `pulseBatteryWakeLatchNow()`
    - `batteryModeTick()`
    - `connectWifi()` now calls `batteryModeTick()`
    - nulling service calls use `batteryModeTick`
    - dataset setup pulses keepalive before/after DAC, nulling profile load, WiFi connect, and MQTT connect.
- `firmware/tests/test_shared_protocol.py`
  - Added assertions for the temporary battery allow path and setup keepalive scaffolding.

Commands already run:

```powershell
python firmware/tests/run_tests.py
pio run -e gld
pio run -e gld -t upload --upload-port COM9
```

Results:

- `python firmware/tests/run_tests.py` passed `31/31`.
- `pio run -e gld` passed after the second keepalive patch.
- First upload to COM9 succeeded, but it only contained the first battery-allow patch.
- After sending `SET_MODE dataset`, COM9 disappeared from Windows. Later COM9 appeared only briefly/phantom; both PlatformIO upload and direct `esptool.py` attempts failed with `FileNotFoundError` because the port vanished before it could be opened.
- The second keepalive patch is compiled but was not uploaded yet.

Next steps when GLD battery is charged or external power is connected:

1. Confirm COM9 is stable:

```powershell
pio device list
```

2. Upload the second keepalive firmware build:

```powershell
cd D:\PertaminaGLD\firmware
pio run -e gld -t upload --upload-port COM9
```

3. Restart the bridge:

```powershell
cd D:\PertaminaGLD
python apps/gld-operator/bridge.py --host 127.0.0.1 --port 5173 --no-open
```

4. Open the website:

```text
http://127.0.0.1:5173/
```

5. Connect COM9 and verify:

```text
APP_PING
GET_INFO
GET_STATUS
SET_MODE dataset
```

Expected after upload: reboot into `mode=dataset` with `MODE_BATTERY_ALLOWED_TEMP mode=dataset`, not fallback to `inference`.

6. Start clear dataset from the website, no mock, with the provisioned MQTT host, port `1884`, topic root `gas-leak-detector`, device `F001`.

7. Completion requires real GLD evidence:

- Website dataset rows increment.
- MQTT monitor receives `cmd/ack`, `dataset/status`, `dataset/data`, and `dataset/summary`.
- CSV is saved under `apps/gld-operator/output/datasets`.
- If MySQL/Node-RED sink is active, verify rows for the test label.
