# GLD Full Handover - Hub / Node-RED / MQTT / database

> Arsip status 5 November 2026. Angka 55 berkas/89.197 baris dan 100% di
> bawah ini hanya berlaku untuk cakupan software saat itu. Status terbaru,
> termasuk 209 berkas/256.605 baris, paket firmware final, dan gate PC kedua
> serta cold boot fisik, ada di [tracker aktif](DATASET-HANDOVER-GOAL-TRACKER.md).

Last tracker heartbeat: 2026-11-05 10:28:25 Asia/Jakarta
Last evidence update: 2026-11-05 10:28:25 Asia/Jakarta

## Progress dashboard

|Phase|Weight|Progress|Status|Closure gate|
|---|---:|---:|---|---|
|1. Inventory and decisions|20%|100%|Complete|Full scope/history and plaintext approval confirmed|
|2. Portable bundle and launcher|50%|100%|Complete|Final visible BAT24/24PASS; docs/status and byte/ignore checks complete|
|3. Clean checkout acceptance|30%|100%|Complete|Final visible BAT24/24 PASS with canonical AES decode and owned cleanup|
|**Overall software handover bundle**|100%|**100%**|Complete|20+50+30=100%; physical targetPC and owner commit/push explicitly separate|

P2 weighted items: runtime20%*100 + config30%*100 + history30%*100 + launcher20%*100=100%.
P3 equal cases: direct isolated server100%, clean exported-tree100%=100%.

## Work items

|ID|Scope|Progress|Evidence / next gate|
|---|---|---:|---|
|1.1|Runtime/config/history discovery and decisions|100%|User approves plaintext AES/passwords and all history; local project DB not found|
|2.1|Portable Node/Node-RED/MySQL module/MariaDB/driver|100%|Versioned split archives and hashes; signed CH340x64 six-file package|
|2.2|Approved active config and Node-RED state|100%|65 files snapshot, exact pinned plaintext authorization; originals preserved|
|2.3|CSV/ledger history|100%|53CSV+2ledgers; real isolated DB55files/89197rows; byte mismatches0|
|2.4|Visible launcher / verification BAT|100%|Visible finalBAT24/24 PASS with checklist/counter/conclusion; docs/status reconciled|
|3.1|Direct isolated stack|100%|Hub/three bridges/MQTTauth/NodeRED/DB/CSV/AESroundtrip PASS; allownedcleanup|
|3.2|Clean copied tree full acceptance|100%|20261105-102359-971bb2ae/report.json24/24PASS; AES-MQTT-NodeRED,DB,CSV,55files89197rows0byteerrors; owned cleanup|

## Issue register

|ID|Status|Evidence / remaining boundary|
|---|---|---|
|H01|Accepted risk|Owner explicitly chose plaintext active AES/passwords in Git on5Nov; values not echoed to chat|
|H02|Solved for identified history|No source project DB/table orSQLdump found; reconstruct all identified CSV/ledger bytes with provenance, do not call it an old DBdump|
|H03|Deferred|Physical replacement-PC USB/network conditions; signed x64driver package and preflight included, physicalPC not tested|
|H04|Solved (source/tests)|Launcher credential/runtime path now matches existing Hub archive runtime path|
|H05|Solved in handover|Snapshot canonical Hub broker credentials drive restored NodeRED; original sourcefiles unchanged|
|H06|Solved|Checker verifies final3 workflow packages,12flashfiles and portable connection profile|
|H07|Solved|Real initializer refused marker in data directory; reservation moved outside before init|
|H08|Solved|Isolated root TCP account differed fromlocalhost; provision root127 consistently; reconciled own33070 andstopped|
|H09|Deferred unrelated baseline|Global secret guard reports17 marker hits in8 unchanged tracked Esptool vendor fixture/parser files; no new handover hits. This global guard is not claimed PASS; avoid changing vendor fixtures in this handover task.|

Protected: production MySQL3306 and data, original NodeREDprofile/config/CSV, firmware/models/NVS/calibration, existing COM/Dataset/UI flows. No hardware upload or COM open. No commit/push performed.

## Current work / agent state

|Sub-agent / worker|Active work item|Started at|Elapsed|Progress|Activity / state|
|---|---|---|---|---|---|
Tidak ada agent aktif saat ini.

## Evidence log

- Prior inventory identified local Python/ESPtool/WebSocket tracked, Node26.5.0/NodeRED5.0.1 external; sourceIP/userDir and broker path coupling. Default profile has Aedes memory backend, no project DB nodes. Root read-only local MySQL metadata search found no matching project schema/table; noSQLbackups in searched roots.53CSVcandidates located.
- Prior nonsecret runtime snapshot extraction passed9715files; first license staging command was unsupported and its incomplete artifact was archived locally, then exact Node version license retrieved from official tag.
- User subsequently explicitly approved plaintext AES/passwords and all history. State snapshot exported65files/14.9MB,53CSV+2ledgers; source hashes preserved.
- Final Node runtime now includes mysql3.0.4 module and9946files; MariaDB10.4.32 artifact158files/45.9MB; CH340x64 signed package6files.
- Isolated historyDB33070 import55files/89197rows/0byteerrors PASS. Initial init ordering and rootTCPshutdown defects were found and corrected; own testDB reconciled and stopped, original3306 untouched.
- Visible direct full-stack test PID20788 on offset10000 PASS: Hub15173, bridges15174/15273/15373,NodeRED11880,MQTT11884,DB43306; actual NodeRED MQTT ingest persisted DB and CSV. Graceful NodeRED and Hub-owned children/DB shutdown confirmed by logs.
- New handover component suites63testsPASS; secret approval scope5testsPASS; canonical crypto helper synthetic replay/tamper/wrongkey testsPASS. Real encrypted frame/HTTP topology check now added to clean-tree test.
- 2026-11-05 10:02:49 Asia/Jakarta: Tracker write encountered Windows cp1252 UnicodeEncodeError and truncated the working tracker. Rebuilt this record immediately from observed receipts/logs and prior activity evidence; no product/config/data affected. Prior heartbeat deadline breaches (94s,78s,302s,130s,78s,166s,78s and later source-authoring gaps) remain acknowledged, not retroactively marked compliant.

- 2026-11-05 10:11:54 Asia/Jakarta: Clean export2401files/245.8MB fullstackPASS10:05:58, remappedhome/no developer env, no source.env/privatefiles/.pio. MQTTauth,actualAESencryptedframe throughcanonicalNodeREDdecoder/topology,DBinsert/CSV,55historyfiles89197rows0errors,allownedcleanup. Userrequestsper-itemcheckbox/xx-total/finalconclusion; presentation pass underway. NormalNodeREDdashboardbind preserved, loopback enforced onlyisolatedtest.
- Heartbeat SLA breach 545s during outputpresentation/reliability review; no backdating.

- 2026-11-05 10:22:17 Asia/Jakarta: Heartbeat SLA breach 623s during context recovery/source review; no backdating. Existing scanner session ended; final checklist and documentation reconciliation continue.

- 2026-11-05 10:23:58 Asia/Jakarta: Heartbeat SLA breach 101s during documentation and tests; no backdating.

- 2026-11-05 10:23:58 Asia/Jakarta: Final handover helper/verification suite 77 tests PASS. README and GLD portability guide reconciled with approved plaintext snapshot and actual history reconstruction.

- 2026-11-05 10:25:07 Asia/Jakarta: Heartbeat SLA breach 69s during verification polling; no backdating.

- 2026-11-05 10:27:29 Asia/Jakarta: Visible final BAT report output/handover-verification/20261105-102359-971bb2ae/report.json PASS24/24,0failed/0requiredskips; history55files89197rows0mismatch; services stopped.77handover+105Hub+195GLD+5approval testsPASS; nativeuploadall3 and portableprofilecheckPASS.85handover inputs ignored0; largestpart69,386,284bytes; all3firmwareSHA unchanged; gitdiffcheckPASS. Status/README reconciled; targetPC/hardware deferred, commit/push owner step.

- 2026-11-05 10:28:25 Asia/Jakarta: Closure: software bundle complete. Repository guard ended with17 pre-existing vendor marker findings across8 unchanged HEAD-tracked files; no new handover findings, no claim globalguardPASS. Exact file eligibility checked, no firmware/model changes, all test services stopped. TargetPC physical/USB/radio evidence remains deferred; Git commit/push remains owner action. Visible verifier console retained at pause.
