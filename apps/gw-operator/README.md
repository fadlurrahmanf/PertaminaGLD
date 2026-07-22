# Gateway Operator

A local desktop console for the Pertamina GLD **Gateway** firmware
(`firmware/gateway/src/GatewayMqttMeshMain.cpp`, PlatformIO env `gw` /
`gw_hello_ack_fieldtest`, chip ESP32-S3).

It follows the same pattern as [`apps/ch-operator`](../ch-operator) and
[`apps/gld-operator`](../gld-operator): a small stdlib-only Python bridge
(`bridge.py`) serves the static UI and exposes native features plain
browser JavaScript cannot reach (COM ports, MQTT, PlatformIO/esptool).

## Required setup order

The Gateway Setup drawer enforces COM connection, Gateway-side Wi-Fi save and
verification, then MQTT configuration. A save ACK is not treated as proof
that Wi-Fi connected. The serial provisioning surface is intentionally
limited to network provisioning plus `GET_MESH_LORA` and
`SET_MESH_LORA_JSON`; operational traffic still uses MQTT. The gateway
bridges LoRa MESH frames to MQTT entirely on its own:

Step 2 can read the active Windows Wi-Fi profile with **Use this PC Wi-Fi**.
The password travels only through the token-protected localhost bridge into a
masked input; it is not logged or stored by the operator app. If Windows does
not expose the saved key, the SSID is still filled and the password remains
manual.

Step 3 has one shared broker form. The Gateway and operator monitor remain two
independent MQTT clients, but both use the same broker credentials; only their
connect actions and statuses are separate.

- It publishes to `{topicRoot}/uplink`, `{topicRoot}/status`, and
  `{topicRoot}/topology` on the site broker.
- It subscribes to `{topicRoot}/cmd/pull` and `{topicRoot}/cmd/node` for
  downlink commands.

See `firmware/config/GwConfig.h` for the topic constants and
`server/nodered/README.md` for the payload contracts. So this app is an
**MQTT dashboard + downlink command composer**, plus staged network
provisioning, a boot-log tail, and a verified firmware flasher.

`GATEWAY_ID` is also a compile-time constant (`GwConfig.h`), unlike the
CH/GLD device ID, which is provisioned at runtime over serial after
flashing. There is no equivalent "set gateway ID" command in this app.

## Run it

```
run-gw-operator.bat
```

This opens `http://127.0.0.1:5373/`. The bridge falls back to a system
`python` install if `python-embed\python.exe` is not present (unlike
`ch-operator`/`gld-operator`, a bundled interpreter is **not** committed
here to avoid duplicating ~30 MB of binaries per app — copy
`python-embed/` from either of those apps into this folder if you want a
zero-install launch, or just `pip install -r requirements.txt` for a
system Python).

## Features

- **Gateway Setup** drawer — enforced COM -> verified Gateway Wi-Fi -> MQTT
  sequence, followed by the independent operator-monitor broker connection;
  its independent MESH LoRa section reads and persists frequency, bandwidth,
  SF, CR, sync word, and TX power through COM with verified NVS readback and reboot.
- **Overview** — gateway status (state, WiFi/MQTT/mesh, uplink queue
  depth/dropped/published, IP), refreshed every ~10 s from `/status`.
- **Uplinks** — live table of every mesh frame the gateway forwarded to
  MQTT (`/uplink`), newest first.
- **Topology** — latest known parent/battery/RSSI per CH derived from
  CH_HELLO / CH_CONFIG_REQUEST / CH_CONFIG_RESPONSE events (`/topology`),
  plus the raw event feed.
- **Commands** — compose and publish a pull request
  (`MSG_SERVER_PULL_REQUEST` via `cmd/pull`) or a node command
  (`MSG_SERVER_NODE_COMMAND` via `cmd/node`), with a log of what was sent.
- **Boot Log** — read-only COM port tail for firmware boot/debug output.
- **Firmware** — schema-v2 manifest-verified `esptool` flash over USB
  (same verification path as `ch-operator`/`gld-operator`), locked behind
  a local PIN.

## MQTT topic reference

| Topic | Direction | Payload |
|---|---|---|
| `{topicRoot}/uplink` | gateway → broker | mesh frame + parse result |
| `{topicRoot}/status` | gateway → broker | health snapshot, every `STATUS_INTERVAL_MS` |
| `{topicRoot}/topology` | gateway → broker | CH_HELLO / CH_CONFIG_* events |
| `{topicRoot}/cmd/pull` | broker → gateway | `{"hopList":[...]}` or `{"cluster":"0064"}` |
| `{topicRoot}/cmd/node` | broker → gateway | `{"cluster","node","id","ttl","hex","hopList"}` |

`topicRoot` defaults to `gld/gateway` (`PGL_SERVER_SITE_TOPIC_ROOT` in
`firmware/config/ServerConfig.h`).
