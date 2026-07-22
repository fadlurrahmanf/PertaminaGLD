# Operator Hub

Single entry point for the GLD, CH, and Gateway operator consoles. It doesn't
reimplement any of them - it launches each one's existing `bridge.py` as a
child process on its own port and serves a tab switcher that iframes whichever
one you pick.

| App | Port | Folder |
|---|---|---|
| GLD | 5174 | `apps/gld-operator` |
| CH | 5273 | `apps/ch-operator` |
| Gateway | 5373 | `apps/gw-operator` |

## Run

```text
run-operator-hub.bat
```

Open:

```text
http://127.0.0.1:5173/
```

Pick GLD / CH / Gateway from the top tab bar. Each tab's dot turns green once
its bridge answers `/api/health`; the hub polls this for you since the browser
can't check cross-origin (each bridge's CORS allowlist is same-origin only).

Closing the hub window (or Ctrl+C in its console) also stops the three child
bridges it launched.

For child apps without their own `python-embed` folder, the hub reuses the
bundled interpreter from GLD Operator (then CH Operator) before falling back
to system Python. This keeps Gateway serial/MQTT dependencies available.

Each app is still fully usable standalone via its own `run-*-operator.bat` if
you only need one of them.
