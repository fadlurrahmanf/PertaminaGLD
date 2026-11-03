# Wireless Dataset - both recording modes on one GLD

Last tracker heartbeat: 2026-11-02 21:40:30 Asia/Jakarta (PC work complete; physical evidence deferred)
Last evidence update: 2026-11-02 21:40:30 Asia/Jakarta

## Progress dashboard

| Scope | Progress | Status | Evidence / next gate |
|---|---:|---|---|
| **Overall** | **88%** | PC complete; physical evidence deferred | Source, fault tests, wire, browser, CSV and local application activation accepted. Real GLD excluded by user. |
| 1. Contract/protection |100%|Complete|One authenticated hello, legacy1 preserved, direct2 cutoff with safe same-session cleanup.|
| 2. Direct compatibility adapter |100%|Source/host/peer complete|Both protocols, clean recording, stop, frozen original CSV after loss, cleanup then next session.|
| 3. Bridge/UI integration |100%|Source/host checks passed|Existing API/event admission/locks and simple names remain; no unsupported option failure.|
| 4. Host and actual verification |50%|PC complete; physical deferred|4.1 complete,4.2 awaiting GLD availability and user continuation.|

## Scope and calculation

Weights15/35/25/25%; equal items within phases. Overall =15%×100 +35%×100 +25%×100 +25%×50 =87.5%, displayed88%. Phase4=(100+0)/2=50%. Both choices must work on currentprotocol2firmware. Direct cuts off originalCSV on loss and stays incomplete; private same-session cleanup may reconnect solely to Stop/drain, never append/replay userCSV. Pulihotomatis unchanged, preserves/replays into sameCSV. Legacyprotocol1direct remains supported. No firmwarecompile/reflash/COM/pin/NVS/nulling/package changes. Root alone owns realnetwork/deviceAPI and idle service restart; user has authorized fixing and verification. Hotspot withoutInternet requires detached localrunner and independentWiFirestorewatchdog.

## Work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|1.1|Freeze protection and contract|100%|Complete|Closed|Old collectors, firmware/packages and user's62-rowCSV hashed; GLD protocolreview accepted.|
|2.1|Protocol-dispatch wrapper and direct2engine|100%|Complete|Closed for source/host|Final adapter b0843ab8…;24fault tests and independent peer review PASS.|
|2.2|Loss cutoff/private cleanup and sequential sessions|100%|Complete|Closed for source/host|603-row private drain, disk/ACK/Start/Stop faults and loopback sequential sessions PASS.|
|3.1|Bridge API/admission integration|100%|Complete on PC|Physical gate4.2|23route tests, actualHTTP mode switching and freshGLD5174 health/directCompatible=true.|
|3.2|Operator UI mode/cleanup guidance|100%|Complete on PC|Physical gate4.2|ActualChrome8sensor traces, mode locks, pause/resumecleanup, fourCSVdownloads verified.|
|4.1|Independent host/wire/regression and PC browser|100%|Complete|Closed|89Python +6Nodefiles;24adapter faults; actualHTTP/WS/SSE and Chrome4downloads/5screenshots; independent117public+28private rows; localHub/GLD ready.|
|4.2|Actual GLD both modes and browser CSV|0%|Deferred by user: no GLD|Real-device direct/drop cleanup and replay/drop on same firmware|No COM7, network-switch or physical test permitted in this continuation.|

## Issue register

| ID | Status | Issue | Closure / next gate |
|---|---|---|---|
|D01|Solved (PC)|Direct rejected protocol2 firmware|Adapter single-handshake protocol1/2; source/host/wire/browser PASS. Physical evidence trackedD05.|
|D02|Solved (PC)|Direct loss must freeze CSV and release owned remote session safely|Private durable drain, immutable original and subsequent sessions PASS; actualradio proofD05.|
|D03|Solved (scope checked)|Protect legacy/replay/previous CSV|231hashes+previous62CSV unchanged; old/new regression and replay browser recovery PASS; broadphysicalretestnotclaimed.|
|D04|Accepted risk|PC/backend restart and GLD powerloss remain outside originalretentionguarantee|No false recovery guarantee; existing scope retained.|
|D05|Deferred|Physical proof of new adapter on GLD|User resumed without GLD/COM7. Require realdirectclean/drop/privatecleanup/nextsession + replaydrop and CSV comparison when available.|
|D06|Solved|Windows urllib early403 close race in route fixture|90-request causal probe; empty POST tests retain403 and no collector calls;89tests PASS; productionauthunchanged.|
|D07|Solved|Old Stop intent locked disconnected idle recorder after reconnect|Ready/not_ready disconnected no longer own admission;23route tests and actualHTTP sequence PASS.|

## Current work / agent state

Tidak ada agent aktif saat ini. PC scope complete. Waiting for external evidence: GLD physical validation4.2 is deferred by user; no automatic device work is authorized by this checkpoint.

## Evidence log

- User explicitly requires both modes actually work, not aliases only. Contract reviewed by firmware/backend/integration workers. ExistinguserCSV62rowscomplete preserved in baseline; source and package hashes frozen. Root will not stop at source-only claims.

- Heartbeat SLA breach: 85s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 93s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 130s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 94s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 99s while authoring/reviewing package; no backdating.

- 2026-11-02 18:45:45: USER PAUSE / continue tomorrow. Root interrupted Server/Integration workers; GLD worker already complete read-only. No service restart, compile, upload, COM access or actual Wi-Fi/device test occurred for this fix. Production GLD PID36360 remains old runtime; currently deployed both-mode fix is NOT claimed. Source HTML/JS already changed, friendly aliases remain; working Pulih otomatis core and previous62-rowCSV are protected. Root phase3 source/host acceptance updates overall to40%=15+0+25+0; phase2draft is deliberately not accepted.

## Historical pause checkpoint (resumed PC-only below)

- Goal: make Rekam langsung + Pulih otomatis work on currently installed protocol2 firmware without recompiling/reflashing. Rekam langsung freezes original CSV/history/count on first loss; private exact-session cleanup Stop/Resume/drain to fsynced temporary ledger unlocks later sessions; it never replays into original CSV. Pulih otomatis and legacy1 collectors remain byte-identical.
- Server worker draft: `apps/gld-operator/wireless_dataset_direct.py`, class `WirelessDatasetDirectCollector`, public API connect/start/stop/disconnect/export_csv/snapshot. Fields cleanup_pending/active/paused/confirmed/error, cleanup_saved_count/next_seq/stop_acknowledged. DirectDisconnect starts cleanup; another Disconnect pauses; Connect on same wrapper resumes cleanup, never resends Start. Same-device new boot releases old RAM ownership; foreign sameboot/session never stopped. Draft and any worker tests must be reviewed before acceptance.
- Root edits already in source: `apps/gld-operator/bridge.py` optional adapter preferred for direct getter, fallback oldcollector; feature wirelessDirectCompatible; cleanup_pending blocks mode/COM/probe/upload. `js/wireless-dataset.js` direct cleanup locks, Batal menunggu / Selesaikan sesi controls; main/index cache version `20261102-dual-recording`. Root owns these files.
- Tests accepted: 22 route tests including `test_wireless_direct_routes.py`; `test_wireless_direct_ui.cjs`, prior replay UI and direct race checks. Rerun after adapter completion. Commands use bundled Python `C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` and bundled Node corresponding dependencies/node/bin/node.exe.
- Integration-owned helpers: `tmp/wireless-dual-mode/network_context.py`, `test_network_context.py` (6fake tests passed), plus any scenario/real helper drafts written by interrupted worker. Watchdog must stay independent90s, restore original Wi-Fi then remove ONLY own temporary profile. No actual network helper was executed. Root alone may execute real tests; preserve user's Wi-Fi and Internet.
- GLD review refs: START gate/idempotence firmware/gld/src/GldDatasetReplayWifi.cpp:302-308; Resume identity/prefix:337-353; Stop stablecommandID:355-367; ACK durable offered frontier:207-215; final stopped/empty/ACKall summary:542-553. Stop-before-Resume minimizes extra acquisition; baseline Resume-thenStop is also safe if rows go private ledger only. Never Stop unknown boot/session or resend ambiguous Start. Fsyncfailure must not ACK/unlock.
- Protection `tmp/wireless-dual-mode/baseline.json`: old2collectors, firmware/runtime/package hashes; user's previous complete62-row CSV path/hash. Do not modify private credentials or3packages/NVS/nulling. All3short-password firmware packages were already built/validated in previous task.
- Before deployment: finish adapter and independent unit/wire negatives; peer review; verify protected hashes. Then root may restart ONLY owned idle GLD bridge PID36360 (`apps/gld-operator/python-embed/python.exe bridge.py --host127.0.0.1 --port5174` actual args with spaces). Keep Hub PID21752. Recheck live collectors inactive and process identity before restart. Preserve all CSV files. No restart has occurred yet.
- Remaining actual proof: root bounded local runner with independent Wi-Fi restore, same powered GLD1002/profile1/24V/currentprotocol2, sessions directclean8sensorCSV, directactualdrop10s originalCSVfrozen/privatecleanupconfirmed, nextdirectclean then replayactualdrop10s+recoveryStop. No firmwareflash/COM. Browser actual 8sensorchart + CSV downloads for both modes after Internet restored; snapshots/downloads verify exact rows; previous62-row CSV unchanged. Do not claim complete until these gates pass.
- Repo chat/resume docs were NOT updated: user said pause/continue tomorrow, not save.

- 2026-11-02 21:21:02: User resumed WITHOUT GLD at COM7. PC-only implementation, protocol simulator, HTTP/SSE/UI/CSV regression authorized. No serial/device APIs, Wi-Fi changes, flash or firmware build. Physical gate deferred explicitly, not claimed by simulation.

- 2026-11-02 21:26:25: Root regression PASS:64 wireless Python tests and all6 Node wireless test files. Protected231source/package hashes match; previous62-row CSV remains protected. Headless Chrome isolated from user browser available for real UI simulation; no hardware access. Peer found negative/undelivered START session ownership and original-CSV disk-error masking; backend repairing with targeted tests.

- 2026-11-02 21:31:39: Accepted adapter b0843ab897abf3856ecda5f98d445a6144d192cfb9445df0fb59fc7ff9a95ab1,24focused fault tests + independent GLD protocol review PASS. Actual loopback HTTP/SSE/WebSocket4sessions PASS; independent41public/49durable rows and legacy1wire8rows PASS. Root browser against this exact loaded revision active. Overall75%=15+35+25+0; phase4 remains0 until full host/browser gate. One existing foreign-origin HTTP fixture currently WinError10053; investigating before acceptance.

- Heartbeat SLA breach: 79s while authoring/reviewing package; no backdating.

- 2026-11-02 21:37:08:89Python tests and6Node testfiles PASS. Browser actualUI/chart12directcomplete,8directdropfrozen+pause/resumeprivatecleanup,8nextdirectcomplete,49replaycompleteincluding40retained;4ChromeCSVdownloads matchAPI/disk after newline normalization. Screenshots visually reviewed. Windows urllib early-auth-close race isolated90requests; test-only empty POST keeps exact403/no-access assertions, productionauth unchanged. Browser found staleStop ready/disconnectedadmissionbug; bridge fix+23route tests and actualHTTP sequence PASS.

- Heartbeat SLA breach: 73s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 89s while authoring/reviewing package; no backdating.

- 2026-11-02 21:40:30: PC SCOPE DONE. Final independent verification8sessions=117public+28private durable rows, allfields exact, oneStart/session. FouractualChrome downloads77rows exact; five screenshots recorded and rootvisuallyreviewed direct/replay. SimulatorHTTP56584/WS56583closed. Started only previouslystopped HubPID33672(no-children) and GLDbridgePID13612, no serial/device/WiFi operation; HubrootHTTP200, GLDhealthOK+wirelessDirectCompatible=true; bothcollectors disconnected0rows. All231protectedhashes and prior62-rowCSV reconfirmed unchanged. Guide/report: docs/firmware/gld-dataset-wireless-dual-mode-pc-20261102.md.

## Current handoff (supersedes historical pause checkpoint)

PC correction is complete and activated. No firmware compile/upload is needed for this application-only change. Open http://127.0.0.1:5173/ or GLD http://127.0.0.1:5174/ . RealGLD validation remains deferred, noCOM7 used. Old firmware/packages/nulling and originalcollectors unchanged. If user resumes physical testing, first read this tracker and the PC report; confirm scope/availability and inactive collectors, then use existing guarded detachednetwork helper, independentWiFirestore and actualdevice identity. Never equate simulator500ms with physicalsampling proof. No repeated implementation/testing is needed absent code changes or new evidence.
