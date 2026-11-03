# Visible connection-test script handoff

Owner: Integration_Agent. Script prepared only; no GLD, COM, real Hub API, Wi-Fi/network configuration, service or credential resolver was exercised by this worker.

File: `tmp/wifi-connect-release-20261103/test_real_connection.py`.

Launch from a visible accessible console after the approved upload, using the bundled interpreter:

```text
apps\gld-operator\python-embed\python.exe tmp\wifi-connect-release-20261103\test_real_connection.py --run-real --hub-connect
```

The script writes an initial waiting stage immediately to `real-connection-result.json`, waits up to 600 s for native Windows association with GLD-DATASET-1002 plus an on-link 192.168.4.0/24 route on that same WLAN adapter, and never joins or changes Wi-Fi itself. Equal/more-specific conflicting routes fail closed. Each GLD socket probe rechecks the association/route and that Workspace, legacy collectors, COM slots and cleanup are idle.

It uses the actual application's `wireless_dataset._transport_factory` to load the vendored WebSocket dependency. Private authentication is resolved only after network guards and stays in memory. Actual `WorkflowCollector._hello()` validates the authenticated Hello without any Start, ACK, acquisition or CSV creation. It requires idle ready device 1002, profile 2, Model 2, production approval and prediction readiness.

After a healthy Hello, it sends one controlled partial HTTP request (GET line, Host line, unfinished final line), closes at approximately 100 ms, then requires another healthy authenticated Hello within five seconds of that abort. No preliminary abandoned TCP probe is added. All script-owned TCP/WebSocket objects close in finally/context-manager paths.

With `--hub-connect`, it calls the existing Workspace Connect API only for the already selected 1002 and no existing session/file. It reads ready/profile/prediction state, then immediately Disconnects and verifies disconnected. A lost Connect response is reconciled before cleanup. If a session becomes active or identity changes during that check, it preserves that session and reports a specific failure rather than stealing/closing it. The console permits return to Internet only after closure is verified; otherwise it asks the user to check Workspace Disconnect first. It does not automatically retry a state-changing API action.

No Hub/process launch/restart is contained in the script. The user-facing console remains open with an input prompt after completion. Errors are fixed allowlisted/script codes; no raw exceptions, HTTP headers, passwords, tokens or credential files are logged in the JSON report.

## Offline verification completed

- `--smoke`: PASS using actual vendored transport against a synthetic authenticated HTTP 101 + WebSocket Hello server on a newly allocated loopback ephemeral port. The synthetic password does not come from the real resolver. The actual protocol-3 validator accepts profile 2/Model 2 Hello.
- The same smoke performs controlled partial-header closure then another HTTP101/Hello and validates route/adapter positive, wrong-adapter and more-specific-conflict fixtures.
- `py_compile`: PASS.

This proves script imports/transport/validation and local harness behavior; it does not prove ESP32 timeout behavior or the real Workspace connection. The root/operator owns the actual visible launch and hardware test. Per-probe guards minimize concurrent-user races, but the user must leave Wi-Fi and recording controls alone during the short probe sequence; no global UI/device lock is introduced.
