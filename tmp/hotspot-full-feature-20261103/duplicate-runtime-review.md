# Duplicate runtime review — revision 4

Date: 2026-11-03. Owner: Integration_Agent. Read-only diagnosis. This worker did not restart, signal, stop or launch a bridge; bind or probe a socket; use COM; invoke an upload; or change Wi-Fi/network/service configuration. The only file changed by this task is this report. Root owns any separate safe invalid-manifest API probe and its evidence.

## Finding

The current source accepts the new capabilities field, but a fresh Hub window does not prove every request is served by that source. The startup code permits an older child bridge to survive and a second instance to be launched on the same Windows address/port. This is a concrete startup defect. Whether the old process served the particular screenshot's request remains an inference until the root's runtime validation probe identifies the active behavior.

Root-provided process inventory: old GLD PID 13240 (13:35), new Hub PID 21160 (15:07), new child GLD PID 2164, CH PID 19356 and Gateway PID 18412. These observations were supplied to this reviewer, not independently recollected or altered. A TCP ownership snapshot naming PID 2164 alone does not prove every response came from PID 2164 when address reuse and another live listener are possible.

## Confirmed source evidence

1. **HTTP servers use address reuse on this Windows runtime.** GLD calls imported stdlib `ThreadingHTTPServer` directly at `apps/gld-operator/bridge.py:1764`; Hub uses the same class at `apps/operator-hub/bridge.py:1769`. CH and Gateway also use it directly. There is no application subclass or `SO_EXCLUSIVEADDRUSE` guard in those paths.

   Read-only introspection of the bundled Python reported Python 3.12.7, `HTTPServer.allow_reuse_address=1`, `ThreadingHTTPServer.allow_reuse_address=1`, `allow_reuse_port=False`. Disassembly of the actual imported `socketserver.TCPServer.server_bind` confirms it calls `setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)` before `bind` when reuse is enabled. Its code references no exclusive-address option. No server instance/socket was created by the introspection.

   Windows permits an active TCP address to be rebound using SO_REUSEADDR; which bound socket receives traffic is then indeterminate. Setting SO_EXCLUSIVEADDRUSE before bind prevents this second binding. This is Windows behavior, not an assumption about Linux reuse semantics. [Microsoft Winsock documentation](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse).

2. **Preflight cannot reliably reject this duplicate.** `_port_available` at `apps/operator-hub/preflight.py:116` itself sets SO_REUSEADDR before a bind test. It can report a conflicting active address as available on Windows. Child-port conflicts are only warnings (`:231`–`:234`); `main` rejects only an error for the Hub port (`apps/operator-hub/bridge.py:1764`). A warning does not stop child launch.

3. **Children are spawned without an existing-runtime guard.** `launch_children` (`apps/operator-hub/bridge.py:983`) always starts each configured bridge and records only its newly spawned Popen. There is no prior child health/PID/source-revision ownership decision. `_wait_for_children_health` (`:1718`) accepts any responder with the expected appId; it does not compare the response against `proc.pid`, check `proc.poll()`, or confirm loaded validator revision.

4. **Shutdown can leave the older process behind.** `shutdown_children` (`apps/operator-hub/bridge.py:1029`) stops only Popen objects stored in the current Hub's `child_processes`. An independently started or previously orphaned GLD is outside that list. GLD startup starts its optional embedded MQTT broker before binding HTTP (`apps/gld-operator/bridge.py:1747`–`:1764`), further allowing broker and HTTP lifecycle ownership to differ. The broker also explicitly sets SO_REUSEADDR (`apps/gld-operator/local_mqtt_broker.py:246`).

5. **Health is too coarse to diagnose this stale validator.** GLD health reports a stable appId and stable bridge version (`0.4.0-lite-bridge`), plus general features, but no PID, runtime generation or loaded source revision (`apps/gld-operator/bridge.py:1533`). These fields cannot distinguish the old and new validators. Current on-disk validation accepts an optional capabilities dictionary only for the three final workflow environments and requires exactly two true booleans (`apps/gld-operator/bridge.py:1049`–`:1063`).

6. **Duplicate responders can cause more than stale validation.** Hub `child_request` fetches the CSRF token from health and performs the API call in a separate HTTP connection (`apps/operator-hub/bridge.py:563`–`:576`). A duplicate listener could answer those two connections with different process-local tokens. The existing token rejection is correct; this report does not propose weakening authentication or retrying state-changing uploads.

## Smallest preventive patch to consider

No preventive patch was applied by this reviewer.

1. Use a local HTTP server subclass with address reuse disabled and, on Windows, SO_EXCLUSIVEADDRUSE set before the real bind. Bind HTTP successfully before creating the optional MQTT broker or any child/background resource. A competing instance should fail visibly before side effects. Preserve the non-Windows policy deliberately rather than assuming Windows/Linux socket options are interchangeable.
2. Make the preflight occupied-port check consistent with exclusive Windows binding; do not use SO_REUSEADDR to establish that a live service port is free. The final exclusive bind remains the authoritative race-safe check.
3. Before launching children, detect an already-running child and report an actionable conflict. Do not automatically kill it, silently reuse an unverified old revision, or spawn a competing copy. The existing explicit `--no-children` mode can remain for deliberate externally managed bridges.
4. For accurate readiness, expose PID plus a startup-captured runtime revision/generation in health, and require the expected launched PID to answer while its Popen remains alive. Capture the revision at startup; hashing the disk file on each health request would misrepresent old already-loaded Python code after a source edit. This extra identity is diagnostic/readiness metadata and must not replace the CSRF token.

The immediate minimum is exclusive HTTP binding before broker startup plus an explicit duplicate-child conflict. PID/revision health is the small additional check that prevents an old process from being falsely labeled freshly launched. Apply equivalent startup protection to Hub and all three child listeners; assess the broker's separate ownership before changing its existing shared configuration.

## Safe practical recovery for the current session

The new source cannot retroactively change socket options or loaded validators in an old process. Browser reload and package rebuild do not resolve that old runtime.

- First establish that no firmware upload, recording, paused retained session or CSV finalization is active. Preserve the current broker configuration and credentials; no broker port, device MQTT setting or Node-RED configuration needs to change.
- Close the newly opened Hub through its normal console Ctrl+C so it closes the children it actually owns. Separately close the old standalone GLD console gracefully. If its window is unavailable, any manual process action should target the identified old bridge PID/path specifically; do not terminate all Python processes.
- Confirm only the intended bridge tree remains, then launch one Hub and validate the loaded validator behavior with the root's deliberately invalid schema/fake COM999 probe. Do not use a valid package upload as a runtime-version probe.
- Because automatic approval rejected process termination twice in this session, this reviewer performed no process action and recommends no alternate API, shell or process technique to bypass that rejection. User-managed graceful closure is the practical recovery unless the automatic reviewer later permits a narrowly justified action.

## Runtime evidence supplied after diagnosis

Root reports eight deliberately invalid schema-0 / fake COM999 API probes all returned the old unsupported-capabilities error. These probes do not flash or open a device. They confirm the active endpoint still executes the old validator behavior despite the new on-disk source. They do not by themselves attribute each response to a particular PID.

## Remaining uncertainty

The source and bundled runtime prove the duplicate-binding vulnerability and insufficient readiness identity. They do not prove which PID handled the screenshot, whether the old process still owns an HTTP listener in addition to MQTT, or which exact code object is loaded in each process. Root's read-only process/listener inspection and safe API validator probe should supply that distinction. Report stale-runtime causation as confirmed only when those observations agree.

## Revision 5 — authorized preventive source repair

The parent subsequently authorized the bounded startup repair. The earlier section describes the diagnosis before that authorization. The following source changes are now implemented; no existing process was stopped, restarted, signaled or reconfigured.

- `apps/gld-operator/bridge.py`: adds `ExclusiveThreadingHTTPServer` with address reuse disabled and SO_EXCLUSIVEADDRUSE set before bind when the platform exposes it; other platforms use the ordinary non-reuse bind. GLD establishes HTTP ownership before optional broker construction and exits clearly with `GLD_BIND_FAILED` if occupied. Health now adds `processId` and `features.firmwarePackageCapabilities=true`. Firmware validation, serial/COM, NVS, Dataset and authentication paths are unchanged by revision 5.
- `apps/operator-hub/bridge.py`: uses the same exclusive HTTP policy. Before spawning each child, it checks for a healthy matching app and reuses it without adding it to this Hub's shutdown ownership. A reused old GLD without the capability marker receives a clear update-required console message. A foreign or unresponsive occupied service is reported as a child-port conflict and is not shadowed by another spawn. Free children launch normally. Conflicts and launch failures are included in startup unavailability; an exited child cannot borrow another listener's health response. Newly launched GLD readiness additionally requires the advertised processId to equal the Popen PID.
- `apps/operator-hub/preflight.py`: the availability probe now uses exclusive binding when available, never SO_REUSEADDR.
- `apps/operator-hub/tests/test_runtime_startup_ownership.py`: ten focused actual-behavior tests added.

Reusing a healthy legacy GLD deliberately does not load the new validator or silently kill its broker. The startup notice identifies that remaining manual update need. Current old running processes remain unaffected until the user closes/relaunches them gracefully. CH/Gateway source and the MQTT broker's independent socket policy were not changed; the Hub now avoids launching duplicate children for all three apps.

### Verification performed

- Entire existing Operator Hub suite plus new tests: **105 tests PASS** (95 existing + 10 startup tests).
- Final startup-focused rerun after strengthening the raw reuse-socket assertion: **10 tests PASS**.
- Existing GLD workflow route/ownership tests: **4 tests PASS**.
- Scoped `git diff --check`: PASS.

The socket tests used only newly allocated loopback ephemeral ports on the current Windows runtime. They prove: an old SO_REUSEADDR listening socket blocks the new exclusive HTTP server; a new exclusive HTTP server blocks both another exclusive server and a raw SO_REUSEADDR socket; an occupied port fails preflight; closing the test listener releases the port and allows replacement. Tests also exercise actual GLD bind-before-broker ordering and actual health serialization with mocks, and mock Hub launch decisions for reuse, conflict, free spawn, exited process and PID mismatch. They did not address or connect to an existing service port, use COM, instantiate a real MQTT broker or flash firmware.

### Revision 5 frozen SHA-256

| File | SHA-256 |
| --- | --- |
| GLD `bridge.py` | `9bc8821a526b79f6538e50242dc42ef853e2e9753ece299839e26fe8a5f0e981` |
| Hub `bridge.py` | `14f5ae5563090bb4456ccd291f48e725a97678ffeadcca45c2c0fee8227a89e5` |
| Hub `preflight.py` | `6d28d067c68ac41fdf47febfa33ca5cf7085ba76850910bf26ff1b72ada82bc1` |
| Startup tests | `cffa966b6616b3cbf01577485495f28ee2468528de9163444c4b2ca138aa23c6` |

Live restart/recovery remains unperformed. The automatic approval rejections described above were not bypassed. No compile or firmware/package replacement is needed for this host startup patch.
