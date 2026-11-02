# GLD Wireless Dataset — Stage 2 replay

Last tracker heartbeat: 2026-11-02 17:11:46 Asia/Jakarta
Last evidence update: 2026-11-02 17:11:46 Asia/Jakarta

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall Stage 2** | **100%** | Complete for agreed scope | Three parallel builds; Model 1 actual replay/expiry/CSV; ten-page PDF visually checked. |
| 1. Contract and protection |100%|Complete|Frozen protocol2 contract; Stage1 fingerprints captured. |
| 2. Firmware RAM replay |100%|Complete|Three C++ builds PASS; Model 1 runtime verified in phase 4.|
| 3. Collector and UI |100%|Source and PC E2E passed|22collector fault cases;8chart/2downloads/608replayed/sameCSV.|
| 4. Verification |100%|Complete|260s: 528 replay / 559 complete. 305s: 600 replay / 613 retention_limit. All 1,172 rows/downloads validated.|
| 5. Illustrated PDF manual |100%|Complete|Ten pages, eight views, numbered boxes; all pages visually checked. Three archive views explicitly labelled.|

## Protected scope

Stage1 Model1 realbench PASS29rows/8sensor/500ms +9rowphysicaldrop, existing3Stage1 binaries/packages, serial/MQTT/LoRa/Running/nulling/pins/NVS/model bindings. RAM retention only while powered; external24V,1GLD,500ms. Router mode remains deferred. Initial source phase avoidedhardware. User now explicitly authorizes3parallelcompiles thenModel1COM7upload/realreplaytest;NVSreset remains prohibited.

## Progress calculation

Scope expanded by user-requested manual: phase weights 14.25/28.5/33.25/19/5%; equal items within phases. All items now 100%; overall 14.25+28.5+33.25+19+5=100%. Physical closure is Model 1 only; Model 2/3 board tests, router mode and soak/range tests remain outside agreed closure.

### 1. Contract and protection

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|1.1|Replay wire contract and failure semantics|100%|Complete|Implementation consistency|Protocol2/640RAM/ACKfsync/Resume/300s stickyterminal agreed|
|1.2|Protected baseline and variant isolation|100%|Complete|Maintain source/package fingerprints|Stage1 sourcehashes and separate targets/collector/API agreed|

### 2. Firmware RAM replay

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|2.1|Bounded ring, ACK retention, replay protocol|100%|Source/host checks passed|Build/runtime belongs4.2|16source gates;640x64bytes,ACKwindow8;atomicTXracefound/fixed/peerreviewed|
|2.2|Separate Model1/2/3 replay build targets|100%|Build/package validation passed|Closed|Three first-attempt builds overlapped 15:53:57-16:01:52 WIB; old variants/packages preserved.|

### 3. Collector and UI

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|3.1|Reconnect/resume/dedup and persistent CSV|100%|Host fault tests passed|Real-wire E2E4.1|20deterministicfaulttests;Stage1collectorhashunchanged|
|3.2|Recovery/buffer status and API integration|100%|Host and Model 1 passed|Closed|Recovery/replay UI and same CSV proven; two actual downloads matched; API/catalog guards PASS.|

### 4. Verification

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|4.1|Host E2E, boundary/overflow and regression|100%|Host E2E passed|Physical4.2|ActualvendoredWS2+large/overflowwire2;PCbrowser814clean/660overflow;all1474rows/ACKdurability verified;5negativecontrolsPASS|
|4.2|Three approved builds and actual bench|100%|Complete|Closed; Model 2/3 physical deferred|Model 1 upload once, NVS OFF/profile 1; positive 559 complete / expiry 613 retention_limit independently verified.|

### 5. Illustrated PDF manual

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|5.1|Actual screenshots with numbered annotation boxes|100%|Complete|Closed|Five direct UI views plus three unchanged actual-log views; archive banners/captions and privacy checked.|
|5.2|PDF authoring and rendered visual QA|100%|Complete|Closed|Ten-page PDF rendered and all pages visually checked; final-qa.json retained.|

## Issue register

| ID | Status | Issue | Closure / next gate |
|---|---|---|---|
|R01|Solved for source scope|Stage1 stops on transport loss|New isolated sampler must continue while powered|
|R02|Solved for host scope|ACK loss may duplicate or lose samples|Persisted-prefix ACK + sequence validation/replay|
|R03|Solved for host scope|RAM bound and >5min disconnect|Stop safely/retain pending prefix/report incomplete, no silent overwrite|
|R04|Solved for host scope|Restart/wrong device/stale session|Boot/session identity validation; never append another session|
|R05|Solved for Model 1|260s and 305s tests passed; 1,172 rows and both downloads independently validated|Model 2/3 physical proof deferred; not implied by compile.|
|R06|Accepted risk|Initial TCP timeout before Start; exact cause not isolated. Controlled reset then two successful sessions on same boot without reflash|Failure retained in real-device report; wider startup/soak reliability not claimed.|

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---|---|

Tidak ada agent aktif saat ini. Agreed scope complete; no pending execution gate. Owned Hub/GLD services remain running, no active capture/recovery. Temporary archive closed; original Wi-Fi restored.

## Evidence log

- 2026-11-02 15:03:24: Stage2 requested explicitly. Previous requirement RAM-only while powered,5min,500ms,oneGLD retained. Baseline scoped fingerprints saved tmp/wireless-stage2/baseline-hashes.json. Stage1 tracker remains complete and is not reset.

- 2026-11-02 15:14:32: Contract accepted after componentreview: requiredResume label; durableprefixACK, stickyterminal300s, retainedsummary, no arbitraryretrycount, cancelablecappedbackoff. GLD privatecompactring40960bytes; Stage1 module untouched. Integration source tests written/syntaxPASS, notyetexecuted againstpendingAPIs. OneinitialGLDagent capacityerror recovered; agentactive since15:06:21. Heartbeat SLA breach duringcontractauthoring/review; prior15:05:19 gap554s, no backdating.

- Heartbeat SLA breach observed99s during API authoring/review; no backdating.

- Heartbeat SLA breach observed138s during API authoring/review; no backdating.

- Heartbeat SLA breach observed86s during API authoring/review; no backdating.

- Heartbeat SLA breach observed72s during API authoring/review; no backdating.

- 2026-11-02 15:27:10: Accepted16firmwaresource/credentialgates+7Stage1;20newcollectorfaulttests;12API+2newVMUI+18Pythonpackage+NodeStage1/replayall3selectionguards. Existing18collector/6API/model/raceUITestsPASS. IndependentpeerreviewfoundrealTXcontrol/sampleorderingrace; fixedguardedselection and16sourcegatesPASS, networkingoutsideguard. Stage1source/oldenvs/184packagefilesunchanged. No firmwarecompile,CPPexecution,credentials,binarypromotion,COM/servicerestart/networkjoin. Remainingreal-wire/browserhostfixture andapprovedbuild/physicalgate.

- Heartbeat SLA breach observed89s during API authoring/review; no backdating.

- Heartbeat SLA breach observed61s during API authoring/review; no backdating.

- Heartbeat SLA breach observed110s during API authoring/review; no backdating.

- Heartbeat SLA breach observed100s during API authoring/review; no backdating.

- Heartbeat SLA breach observed146s during API authoring/review; no backdating.

- Heartbeat SLA breach observed114s during API authoring/review; no backdating.

- Heartbeat SLA breach observed107s during API authoring/review; no backdating.

- Heartbeat SLA breach observed116s during API authoring/review; no backdating.

- Heartbeat SLA breach observed123s during API authoring/review; no backdating.

- 2026-11-02 15:50:08: FinalPCbrowserE2E PASS independently:608retainedduring299.5svirtualgap,814rowcleancomplete/sameCSV/sameSID;640capacityfault+20persisted=660incompletebufferfull/nooverwrite. All1474rows/all8values/scalars matchoriginalsyntheticdata andbothactualbrowserdownloads. fsync-beforeACK audit and5verifiernegativecontrolsPASS. Browserclose734→backend766→reload813→Stop814. Directconsole recovered iframe-download observer timeout; no productchange forbrowsertoolissue. Frozenvalidated-evidence.json+SHA andverification-report.json retained. FixturePID9264 gracefullyexited; ports52757/52758 closed. ProductionPIDs23664/33740 unchanged; noCOM/networkjoin/compile/upload/NVSerase/newrealcredentials. UnitfakeACKclockfidelitycorrected:603retained/604rows scenario supersedes earlier609claim. Reportdocs/firmware/gld-dataset-wireless-stage2.md.

- Heartbeat SLA breach observed99s during API authoring/review; no backdating.

- 2026-11-02 15:52:23: Explicituserapproval3parallelModel1/2/3Stage2builds plusdeployment/actualGLDtest. No repeatapprovalneededforauthorizedsteps. HardwareRootonly, ResetNVSoff, preserveprofile1.

- Heartbeat SLA breach observed193s during API authoring/review; no backdating.

- 2026-11-02 15:57:18: ThreeactualPIOcompilesoverlap:Model1started15:52:49.917,Model2 15:53:29.788,Model3 15:53:57.533WIB. Separatebuild/libdeps/log/credentialenvpaths. NewReplay/Unifiedsourcepassesall3sofar; no finalbuildclaim.

- Heartbeat SLA breach observed104s during API authoring/review; no backdating.

- Heartbeat SLA breach observed100s during API authoring/review; no backdating.

- Heartbeat SLA breach observed166s during API authoring/review; no backdating.

- Heartbeat SLA breach observed422s during API authoring/review; no backdating.

- Heartbeat SLA breach observed100s during API authoring/review; no backdating.

- Heartbeat SLA breach observed110s during API authoring/review; no backdating.

- Heartbeat SLA breach observed196s during API authoring/review; no backdating.

- Heartbeat SLA breach observed110s during API authoring/review; no backdating.

- Heartbeat SLA breach observed109s during API authoring/review; no backdating.

- Heartbeat SLA breach observed180s during API authoring/review; no backdating.

- Heartbeat SLA breach observed152s during API authoring/review; no backdating.

- Heartbeat SLA breach observed92s during API authoring/review; no backdating.

- Heartbeat SLA breach observed116s during API authoring/review; no backdating.

- Heartbeat SLA breach observed232s during API authoring/review; no backdating.

- 2026-11-02 16:35:44: All3buildsfirstattemptSUCCESS, overlapping15:53:57–16:01:52WIB; RAM162912/32768049.7%,Flash~16%;strict3packages/image/model/NVSchecksPASS. Rootplacedonly3newReplaypackages,restartedownedHub/GLDnow21752/36360. COM7NVSbackup20480Bprivate;uploadonceModel1APIreturnedok/4files/NVSfalse14.188s16:10:44. FirstnetworkattemptfailedTCP20s beforeStart;controlledENreset/passivebootready1,nopanic;targetARP/ICMP/TCP+hello2/1002/profile1readyprovenafterward. UserwarnsGLDhotspotnoInternet;rootlocalrunner+90srestorewatchdogs andoriginalInternetduring260soutage acknowledged. FirstactualStartissuedonceinlatestpositiveoutput20261102T093208Z-1334ef,13rowsrecovering;notyetreplayPASS. UseraddedclearannotatedPDFmanual;builderready,noPDFauthored.

- Heartbeat SLA breach observed102s during API authoring/review; no backdating.

- Heartbeat SLA breach observed97s during API authoring/review; no backdating.

- Heartbeat SLA breach observed190s during API authoring/review; no backdating.

- Heartbeat SLA breach observed110s during API authoring/review; no backdating.

- Heartbeat SLA breach observed109s during API authoring/review; no backdating.

- Heartbeat SLA breach observed63s during API authoring/review; no backdating.

- Heartbeat SLA breach observed212s during API authoring/review; no backdating.

- Heartbeat SLA breach observed241s during API authoring/review; no backdating.

- Heartbeat SLA breach observed92s during API authoring/review; no backdating.

- Heartbeat SLA breach observed104s during API authoring/review; no backdating.

- Heartbeat SLA breach observed231s during API authoring/review; no backdating.

- Heartbeat SLA breach observed191s during API authoring/review; no backdating.

- Heartbeat SLA breach observed72s during API authoring/review; no backdating.

- Heartbeat SLA breach observed109s during API authoring/review; no backdating.

- 2026-11-02 17:11:46: Final acceptance: three builds truly parallel, strict packages validated, Model 1 upload once/NVS OFF/profile 1. Actual positive 260s -> 528 replay/559 complete; expiry 305s -> 600 replay/613 retention_limit. All 1,172 rows and both downloads independently checked. Ten-page annotated manual rendered/visually inspected, SHA256 155131567631caa228449bc139832dccf3873aa7b6ea8dc18f9980cf9d065545. Evidence: docs/firmware/gld-dataset-wireless-stage2-real-device-20261102.md; tmp/pdfs/gld-wireless-manual/final-qa.json. Archive36860 stopped/57308 closed; Hub21752/GLD36360 kept alive, no active sampling/recovery, Wi-Fi restored. All workers complete.
