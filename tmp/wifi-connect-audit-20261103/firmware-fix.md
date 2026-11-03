# Workflow HTTP-header timeout repair — source receipt, 3 November 2026

Scope: bounded parent-authorized source repair of the confirmed ESP32 timeout-unit defect. It is **not** a claim that the exact partial-header trigger was observed on the physical GLD. No firmware/native C++ compile, dependency/package mutation, device/COM, network configuration, service or NVS action was performed by this agent.

## Exact source delta

Only `CheckedServer::loop()` was added in `firmware/gld/src/GldDatasetWorkflowWifi.cpp`. The concrete `CheckedServer socket` already used by the transmitter invokes this adapter. It retains the actual WebSockets 2.6.1 server order:

```text
running check → yield → accept new clients → normalize header-client timeout → Core::loop parses headers
```

After the vendor's nonvirtual `handleNewClients()` has initialized accepted clients, the adapter sets header clients' ESP32 WiFiClient timeout to `ceil(WEBSOCKETS_TCP_TIMEOUT / 1000)` **seconds**. For the unchanged 1000-ms library macro, this is one second. A Stream `getTimeout()` comparison makes normalization idempotent. The underlying library's millisecond I/O deadlines remain **1000 ms**; the global macro is not retuned to 1.

This prevents the actual vendor's `setTimeout(1000)` call from leaving a newly accepted ESP32 client's Stream timeout at 1,000 seconds before its first `readStringUntil('\n')`. It does not alter authentication, protocol/session/ACK/replay handling, acquisition timing, native controls, model approval/binding, calibration, pin mapping or NVS.

No vendor cache, PlatformIO environment or preparation script was edited. The adapter is checked-in application code shared by the final Model 1/2/3 workflow targets. Historical stage1/replay and normal targets retain their existing sources.

## Snapshot hashes for independent review/freeze

| Changed file | SHA-256 |
|---|---|
| `firmware/gld/src/GldDatasetWorkflowWifi.cpp` | `fcd4195db2e8f39d15c5b3dd898bc346478c53ea7e55441ffeeda8eec5ef0bfc` |
| `firmware/tests/test_dataset_workflow_header_timeout.py` | `5e1f357f6f4500d86687f733e743d8baa4f39675929997e5e12fe6fe6dc19f8a` |

These are the only firmware/test files changed by this repair. Compared the parent's previous 110-entry `tmp/three-model-sync-20261103/source-freeze.json`: only the authorized workflow module differs; all **109 other source/input files are identical**, including all three models, shared runtime, binding/nulling/power/pin implementations, PlatformIO and preparation hooks. Main runtime SHA remains `2b93d489b873d173faa008474c7d307aa83af21ed80c9dca3e129a93ebd7c0a6`; workflow header SHA remains `b8222a17ffb3bf3b0d39d4b2b5271366bd2b2f1ea88a53891a4c5ff4d8213888`.

## Host/source verification

```text
C:/Users/MSI/.platformio/penv/Scripts/python.exe -m unittest
  firmware.tests.test_dataset_workflow_header_timeout
  firmware.tests.test_three_model_sync_policy
  firmware.tests.test_dataset_workflow_source
  firmware.tests.test_dataset_replay_source
  firmware.tests.test_dataset_workflow_credentials -q

Ran 58 tests in 0.542s — OK
git diff --check — PASS for changed firmware/test paths
```

Seven focused tests cover:

- Production acceptance → normalization → parsing order and concrete adapter invocation; nonvirtual upstream hook assumptions and no second acceptance after normalization.
- Preservation of all three environments' 1000-ms vendor deadline, and conversion at 1/999/1000/1001/2000-ms boundaries.
- Actual installed WebSockets and ESP32 framework API/source contracts: vendor resets accepted-client timeout; WiFiClient setter takes seconds; Stream reads use millisecond timeout and do not shortcut on socket disconnect.
- Deterministic virtual-clock header fixture executing the production adapter's extracted stage order and conversion expression: split header/newline at 50 ms is preserved; abort during a partial line returns after 1000 ms; the next complete client header is processed afterward.
- Explicit red-case controls: omit normalization or place it before the vendor resets accepted-client timeout, and the same fixture reproduces a **1,000,000-ms** wait. Retuning the global macro to 1 also fails the deadline contract.

The fixture is intentionally **not native C++, real sockets, full HTTP authentication/Hello or device execution**. It demonstrates units and scheduling assumptions with actual-source contracts and catches the integration/order regression; physical verification is still mandatory. Installed dependency/framework checks skip explicitly if those optional local source caches are unavailable.

## Remaining release/device gates

**SOURCE FROZEN:** the independent integration reviewer confirmed the module hash above, inspected the actual dependency/framework call order and units, reran all seven focused tests successfully, and found no blocking source issue. After user approval, compile the three final models in parallel, verify artifacts/provenance and preserve unrelated packages. Any authorized Model 2 upload remains Reset NVS OFF. Any subsequent source edit invalidates this freeze and requires refreshed evidence.

On hardware, test a truncated HTTP line and disconnect, then a subsequent healthy authenticated connection/Hello; confirm no long stall. Repeat ordinary graph8/500-ms capture, optional prediction OFF/ON, CSV finalization and dropped-link replay, while native Running/binding/profile 2 remain intact. Existing source evidence cannot certify socket/task recovery on the current device or prove the previously recorded TCP timeout's triggering packet. No device success is claimed here.
