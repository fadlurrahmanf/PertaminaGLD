# GLD Operator Lite

Lightweight GLD operator console. The UI is plain HTML/CSS/JS. Full desktop-like
features are provided by a small local Python bridge instead of Electron.

## Recommended Run

Use the bridge for full features:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
python -m pip install -r requirements.txt
.\run-gld-operator.bat
```

Open:

```text
http://127.0.0.1:5173/
```

Bridge features:

- COM scan and native serial connect at 115200 baud, with manual COM override
  for cases where Windows/pyserial does not enumerate the USB adapter yet.
- Serial command write/read for `APP_PING`, `GET_INFO`, `GET_STATUS`,
  `SET_MODE`, `SET_APP_CONFIG_JSON`, and `SET_DEVICE_ID_JSON`.
- Windows WiFi SSID/password and local IPv4 lookup for `Use this PC`.
- Visual alarm badge plus local sound/mute. Mute is local only and does not send
  an alarm clear command to GLD.
- Local bench MQTT broker on port `1884` from `run-gld-operator.bat`, so
  dataset START/STOP does not require Node-RED. Bind address is `0.0.0.0` so a
  GLD on the same WiFi can connect to this PC's IPv4 address.
- Dataset MQTT command publish when `paho-mqtt` is installed and the local
  broker is reachable.
- Dataset session monitor subscribes to MQTT `cmd/ack`, `dataset/status`,
  `dataset/data`, and `dataset/summary` for the selected GLD. It also shows
  serial fallback events such as `DATASET_START`, `DATASET_RECORD`,
  `DATASET_AUTOSTOP`, and `DATASET_STOP`.
- `Start Dataset` does not run nulling first by default. Use the Dataset tab
  `Run nulling before dataset` option only when the GLD needs a fresh nulling
  profile. With the option off, the app first sends `SET_MODE dataset`, then
  publishes `START_DATASET` with `run_nulling_first=false`.
- Dataset CSV output is saved by default to:

```text
D:\PertaminaGLD\apps\gld-operator\output\datasets
```

  Use the Dataset tab `Save CSV`, `Download CSV`, and `Open Folder` controls.
- For GLD app config, set `mqttHost` to the WiFi IPv4 shown by `Use this PC`
  and keep `mqttPort` as `1884`.
- Firmware upload orchestration through installed PlatformIO:

```powershell
pio run -e gld -t upload --upload-port COM10
```

The UI can start that upload from the Firmware tab via the bridge. If a
manifest is loaded, the UI and bridge validate the selected env, target ID, chip
family, and `flashFiles` shape before starting the upload.

## Fallback HTML-Only Run

If the bridge is not running, the app falls back to browser Web Serial:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
python -m http.server 5173 --bind 127.0.0.1
```

In fallback mode the browser must show a COM permission dialog, cannot read the
Windows WiFi password, cannot publish MQTT TCP directly, and cannot run
PlatformIO/esptool.

## Size Target

The checked-in app files are tiny. Runtime size depends on installed Python,
Chrome/Edge WebView/browser, PlatformIO, and optional Python packages rather
than bundled Electron/Chromium.
