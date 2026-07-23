# Operator Hub

Single entry point for the GLD, CH, and Gateway operator consoles. It doesn't
reimplement any of them - it launches each one's existing `bridge.py` as a
child process on its own port and serves a tab switcher that iframes whichever
one you pick.

Only `apps/operator-hub/public/` is served over HTTP. `bridge.py`,
`preflight.py`, `firmware-packages/`, and this README are not web-accessible.
Local MQTT broker credentials live outside `apps/operator-hub` entirely, in
`apps/runtime/operator-hub/credentials.local.json`.

The Hub only binds to loopback (`127.0.0.1`, `localhost`, or `::1`) and refuses
any other `--host` value. The GLD/CH/Gateway bridges it launches accept
unauthenticated serial, MQTT, and firmware-flash requests same-origin, so
binding any of this to a LAN address would expose that to the network. LAN
access would need its own authenticated, HTTPS mode - it does not exist today.

| App | Port | Folder |
|---|---|---|
| GLD | 5174 | `apps/gld-operator` |
| CH | 5273 | `apps/ch-operator` |
| Gateway | 5373 | `apps/gw-operator` |

## Run

```text
run-operator-hub.bat
```

The launcher automatically opens the Hub in your default browser:

```text
http://127.0.0.1:5173/
```

Before launching the child operator apps, the launcher performs a read-only
preflight check for the Hub/CH Python runtimes, a shared Espressif uploader in
`apps/lib/esptool/` or `apps/lib/esptool-master/`,
offline firmware packages and their hashes, the Windows CH340 driver package,
and the required local ports. Missing upload dependencies do not prevent the
dashboard from opening, but firmware flashing remains marked unavailable. The
preflight never downloads software, installs drivers, opens a COM port, or
writes firmware; it only reports what is missing.

Pick GLD / CH / Gateway from the top tab bar. Each tab's dot turns green once
its bridge answers `/api/health` **and** confirms its identity (`appId`); a
different service answering on the same port is treated as down, not ready.
The hub polls this for you since the browser can't check cross-origin (each
bridge's CORS allowlist is same-origin only). Use "Refresh readiness" in the
header to recheck firmware packages, runtimes, and ports on demand - it's not
just a snapshot from when the Hub started. The Hub starts on an
operator-selection page; the three cards are buttons that open the
corresponding console. Running `apps/ch-operator/run-ch-operator.bat` also
opens this Hub entry page instead of entering the CH console directly.

If no LAN connection is available at startup, the Hub still opens and the
GLD/CH serial consoles still work; only Gateway/MQTT features are marked
degraded.

**Closing the browser tab does not stop the Hub or its child bridges.** Only
Ctrl+C (or otherwise terminating) the Hub's own console/process stops it and
the GLD/CH/Gateway bridges it launched.

For child apps without their own `python-embed` folder, the hub reuses the
bundled interpreter from GLD Operator (then CH Operator) before falling back
to system Python. This keeps Gateway serial/MQTT dependencies available.

Each app is still fully usable standalone via its own `run-*-operator.bat` if
you only need one of them.
