# 03 — Security & performance

Continues from `02-high-priority.md` (H1, H2). Findings S1–S4 (security) and
P1 (performance/data-integrity).

The cryptographic core is sound — see `00-summary.md` for what was verified.
The items here are about surrounding hygiene and a data-loss bug in tooling.

---

## S1 — GCM nonce is largely deterministic; the first 4 bytes are a fixed constant

**Severity:** Medium — weakens, but does not immediately break, AES-GCM
confidentiality/integrity for GLD uplinks.

### What breaks

The production nonce provider builds a 12-byte GCM nonce as:

`firmware/gld/src/GldUnifiedMain.cpp:1450`
```cpp
for (size_t i = 0; i < GLD_AES_GCM_NONCE_SIZE; ++i)
    nonce[i] = pgl::gld::selftest::NONCE[i];   // seed all 12 with the self-test constant
const uint32_t r = esp_random();
nonce[4..7]  = r;                              // 4 random bytes
nonce[8..11] = nc->counter;                    // 4 counter bytes
```

Bytes `[0..3]` are left at the compile-time self-test constant
(`GldSelfTestConfig.h:19` → `10 11 12 13`) on every device, forever. Only bytes
`[4..7]` (random) and `[8..11]` (a per-boot counter starting at `txCounter`, not
persisted) vary. GCM's security collapses if a `(key, nonce)` pair ever repeats;
here the effective nonce entropy is ~32 random bits plus a counter that resets to
its boot value after every reboot/battery wake cycle. Two devices share a key
(`GLD_AES128_KEY_HEX` is one key for the fleet per `pertamina-gld-decode.js:76`),
so cross-device nonce collision probability is governed by the 32 random bits
(birthday bound ~2^16 messages). A repeated nonce under the same key allows
forgery of the authentication tag for that key.

This is not catastrophic for a 4-byte gas telemetry payload, but it is a real
weakening of the AEAD guarantee and is easy to fix.

### Root cause

The provider was cloned from the self-test fixed-nonce path and never fully
randomized; the leading 4 bytes are vestigial self-test seeding, and the counter
is RAM-only (`NonceCtx nonceCtx{txCounter}` at `:1584`, and `txCounter` starts at
0 each boot — `:112`).

### Exact fix

Fill all 12 bytes from `esp_random()` (three draws), or use a persisted
monotonic message counter combined with a device-unique field:

```cpp
bool nonceProvider(uint8_t nonce[GLD_AES_GCM_NONCE_SIZE], void* ctx) {
    for (size_t i = 0; i < GLD_AES_GCM_NONCE_SIZE; i += 4) {
        const uint32_t r = esp_random();
        nonce[i+0] = r >> 24; nonce[i+1] = r >> 16;
        nonce[i+2] = r >> 8;  nonce[i+3] = r;
    }
    return true;
}
```

`randomNonceProvider` in `firmware/gld/src/main.cpp:86` already does exactly this
and can be reused. The decoder derives the nonce from the received bytes
(`pertamina-gld-decode.js:269`), so no server change is needed. For defense in
depth, also persist a rollover-safe message counter in NVS and mix it in, so a
reboot cannot rewind the counter half of the nonce.

---

## S2 — Wi-Fi/MQTT credentials and a broker IP are committed in cleartext

**Severity:** Medium — secret leakage via version control.

### What breaks

`firmware/config/ServerConfig.h` commits live-looking credentials:

- `PGL_SERVER_SITE_WIFI_SSID "Fshares"` / `..._WIFI_PASSWORD "kayabiasa"` (`:35`, `:39`)
- `PGL_SERVER_SITE_MQTT_USER "deviot"` / `..._MQTT_PASS "deviot"` (`:49`, `:52`)
- Two hard-coded broker IPs (`10.217.88.180`, `10.158.198.180`) (`:19`, `:43`)

The file's own comments say "Jangan commit credential produksi permanen" / "For
produksi, pindahkan ke provisioning/NVS", so the intent is understood but not
enforced. These compile into every gateway/GLD binary and live in git history.

### Root cause

Config defaults hold real values rather than placeholders; only the dataset SSID
uses `CHANGE_ME` (`:11`, `:15`). No provisioning path is wired for the *site*
Wi-Fi/MQTT the way GLD app-config is (which is provisioned at runtime via
`SET_APP_CONFIG_JSON`, `GldUnifiedMain.cpp:628`).

### Exact fix

Replace the committed site/broker values with `CHANGE_ME` placeholders (matching
the dataset entries), and supply real values at build time via
`-D` flags or an untracked local header included by `ServerConfig.h`
(add that pattern; `config/gld-crypto.env.example` / `gld-unified.env.example`
already exist as the intended out-of-tree secret source). Rotate the exposed
Wi-Fi and MQTT passwords since they are already in history. This does not block
function; it is a disclosure-hygiene fix.

---

## S3 — Gateway MQTT command endpoints are unauthenticated by design; only mode-switch downlinks are signed

**Severity:** Medium — informational/by-design, documented here so it is a
conscious decision rather than an oversight.

### What breaks / how it stands

The authenticated-downlink path (CMAC-signed `SET_MODE`, verified in
`GldCommandParser.cpp:138`) is correctly protected end-to-end. But the broader
command surface relies on MQTT broker trust:

- The gateway subscribes to `gld/gateway/cmd/#`, `.../cmd/pull`, `.../cmd/node`
  and will build/transmit `MSG_SERVER_PULL_REQUEST` and `MSG_SERVER_NODE_COMMAND`
  frames for anything that arrives (`GatewayMqttMeshMain.cpp:442`, `handlePullCommand`
  `:495`, `handleNodeCommand` `:573`). `MSG_SERVER_NODE_COMMAND` frames are
  *not* authenticated at the CH — a CH stores any node-command payload as a
  pending downlink (`ChStarMeshRuntimeMain.cpp:1254`) with no signature check.
  The **GLD** re-verifies the CMAC before acting (good), so an unsigned node
  command cannot switch a GLD's mode — but it *can* consume the CH's downlink
  store (16 slots, `DOWNLINK_STORE_CAPACITY`) and cause spurious STAR transmits.
- The Aedes broker generated by the flow has no auth configured
  (`apply-pertamina-gld-flow.js:2189`, `usetls:false`, no credentials).

So an attacker with broker access can enqueue junk downlinks and trigger pull
storms, though they cannot forge a GLD mode switch (CMAC stops that).

### Root cause / fix

This appears intentional for a trusted-LAN deployment. To harden without protocol
changes: enable MQTT auth/TLS on the broker (the mqtt-broker node already accepts
credentials at `:2210`; the Aedes node needs auth configured), and consider a
CH-side rate limit on `MSG_SERVER_NODE_COMMAND` storage per source. No code change
is strictly required if the broker is on a trusted segment — flagged so the trust
boundary is explicit.

---

## P1 — Dataset recorder truncates its CSV on every restart and drops half its DB rows on the pymysql path

**Severity:** Medium — silent data loss in the dataset-collection tool
(`server/nodered/gld_dataset_recorder.py`).

### What breaks

**(a) CSV truncation.** `csv_init()` opens the output file in `"w"` mode on every
process start (`gld_dataset_recorder.py:131`) and is called unconditionally from
`__main__` (`:274`). Restarting the recorder — after a crash, a reboot, or just
re-running it — erases all previously captured rows. There is no append/rotate
mode and no timestamped filename.

**(b) Every-other-row DB loss on the pymysql fallback.** `install_as_MySQLdb()`
is called at import (`:49`), and `ensure_db()` connects with `autocommit=True`
via whichever driver imported. With `mysql.connector` that is fine. But note the
connect logic at `:63-71`: `hasattr(_mc, "connect")` is true for pymysql too, so
the first branch runs and `db_conn.is_connected()` at `:62` — a
`mysql.connector`-only method — does not exist on a pymysql connection, raising
`AttributeError` on the *second* insert's liveness check, which is swallowed and
sets `db_conn = None`, forcing a reconnect each call. Combined with per-insert
`cursor()`/no explicit commit on some pymysql builds, inserts become unreliable
on the fallback path. The CSV loss (a) is the certain, primary defect; (b) is
driver-dependent but real on the documented fallback.

### Trigger

(a) Any restart of the recorder with an existing CSV. (b) Running on a host where
only `pymysql` is installed (the code advertises this as a supported fallback).

### Root cause

(a) `"w"` + unconditional header write treats every launch as a fresh session.
(b) The connection-liveness check assumes the `mysql.connector` API on all
drivers.

### Exact fix

- (a) Open the CSV in append mode and only write the header when the file is new:
  ```python
  def csv_init():
      new = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
      with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
          if new:
              csv.writer(f).writerow(COLS)
  ```
  and keep `csv_append` as-is. Or write a timestamped filename per run. Reserve
  the destructive reset behind the existing `--reset-db`-style flag.
- (b) Guard the liveness check by driver:
  ```python
  alive = db_conn is not None and (
      not hasattr(db_conn, "is_connected") or db_conn.is_connected())
  if not alive:
      db_conn = _mc.connect(...)
  ```
  Both driver branches at `:63-71` already pass `autocommit=True`, so no commit
  change is needed once the connection is stable.

---

## S4 — Operator bridge sends `Access-Control-Allow-Origin: *`, letting any website read the Wi-Fi password and drive firmware upload / serial writes

**Severity:** Medium — local-network / drive-by exposure via the operator's own
browser (`apps/gld-operator/bridge.py`).

### What breaks

The local bridge adds permissive CORS headers to **every** response:

`apps/gld-operator/bridge.py:523`
```python
def end_headers(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    ...
```

and `do_OPTIONS` (`:530`) answers preflights permissively. Because
`Allow-Origin: *`, `Allow-Methods` includes POST, and `Allow-Headers` includes
`Content-Type`, a JSON preflight from any origin succeeds. That means while the
operator has the bridge running on `127.0.0.1:5173`, **any web page open in the
same browser** can issue cross-origin requests and read the responses:

- `GET /api/network` returns the active Wi-Fi **SSID and cleartext password**
  (`bridge.py:558` → `network_info()` → `wifi_password()` via `netsh ... key=clear`,
  `:325`). A malicious/compromised site can exfiltrate the operator's Wi-Fi
  credentials.
- `POST /api/serial/write` sends arbitrary lines to the connected GLD
  (`:580`), `POST /api/firmware/upload` launches a PlatformIO flash
  (`:590` → `firmware_upload`), `POST /api/mqtt/dataset` publishes to the broker
  (`:582`). None require any auth token or origin check.

The firmware-upload command args are safely passed as an argv list (no shell) and
`env`/`targetDeviceId` are regex-validated (`:474`, `:499`), so this is not RCE —
but credential theft and unwanted device/serial actions are in scope.

### Trigger

Operator runs the bridge (its normal mode) and, in the same browser session,
visits any untrusted page. No user interaction with that page beyond loading it.

### Root cause

CORS is wildcarded to make the static UI reachable when it is *not* served from
the bridge origin (`app.js:5`, `bridgeUrl()` falls back to
`http://127.0.0.1:5173`). Convenience was chosen over origin restriction, and
sensitive endpoints share the same permissive policy as static assets.

### Exact fix

- Restrict `Access-Control-Allow-Origin` to the app's own origin(s) instead of
  `*` — e.g. echo the request `Origin` only if it is in an allowlist
  (`http://127.0.0.1:5173`, `http://localhost:5173`), else omit the header. The
  bundled UI is served from the bridge itself (`Handler` roots at `APP_DIR`,
  `:515`), so same-origin needs no CORS header at all.
- Bind the server to loopback only (already the default `--host 127.0.0.1`, `:627`)
  and additionally require a simple per-session token header on the mutating
  `/api/*` POST routes and on `/api/network`, injected into the page at serve
  time. That defeats blind cross-origin calls even if a wildcard slips back in.
- At minimum, drop `/api/network` from returning the password by default; return
  SSID/IP and fetch the password only on an explicit, same-origin action.
