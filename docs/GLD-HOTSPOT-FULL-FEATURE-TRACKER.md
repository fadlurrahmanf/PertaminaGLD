# Hotspot: fitur normal dan tiga pilihan final

Last tracker heartbeat: 2026-11-03 15:49:49 Asia/Jakarta
Last evidence update: 2026-11-03 15:49:49 Asia/Jakarta

## Progress dashboard

|Scope|Progress|Status|Next gate|
|---|---:|---|---|
|**Overall**|**93%**|Waiting for physical evidence|Packages and backend active; new firmware not flashed|
|1. Catalog cleanup|100%|Complete|3finalhotspotchoices,legacy packages/APIs preserved|
|2. Firmware compatibility|100%|Complete (source only)|Actualnormalbaseline+safeownershipsource+tests|
|3. Build/device validation|70%|Waiting for physical evidence|Build40/package20/activation10 complete; physical30 pending|
|4. Current illustrated manual|100%|Complete|14-page PDF rendered and visually inspected; pending firmware clearly marked|

Weights 15/45/25/15%; equal items in source phase. Phase 3 weights build40/package20/physical30/activation10. Overall = 15%*100 + 45%*100 + 25%*70 + 15%*100 = 92.5%, displayed93%.

|ID|Work item|Progress|Status|Next gate|Last update|
|---|---|---:|---|---|---|
|1.1|Hide6obsoletehotspotUIchoices|100%|Complete|Expert+SimpleUItests andread-onlybrowser|Authorized|
|2.1|Audit actualnormalbaseline/featurematrix|100%|Complete|Exactshippedpackage/sourcecomparison|Agentsrunning|
|2.2|Safe additivefirmwaresource|100%|Complete (source only)|Sensor/SPI/modelownership;normalCOMidlecontrols;alarm;profile/AP|Auditfirst|
|2.3|Capability-gated COM upload routing|100%|Complete (source/tests)|95Hub tests plus actual action JS tests|Native and legacy paths preserved|
|3.1|Parallel builds (40% in phase)|100%|Complete|Three success receipts; overlap8.858949s|0warnings/errors|
|3.2|Final Hub packages (20% in phase)|100%|Complete|Exact manifests/served bytes and preserved archives|Three packages installed|
|3.3|Physical validation (30% in phase)|0%|Deferred|Explicit upload/device test authorization required|No hardware in this turn|
|3.4|Backend activation (10% in phase)|100%|Complete|Live PID21584 accepts capabilities for all3models; UI selectedModel2 checkPASS|User closedstaleprocesses; standardstart-onlylaunch succeeded|
|4.1|Manualscreenshots/annotations|100%|Complete|Final PDF hash/report|14 pages, original screenshots plus vector callouts|

## Issue register

|ID|Status|Issue|Gate|
|---|---|---|---|
|H01|Solved|9hotspotchoices confusednormalvsDatasetupload|3finalchoices only|
|H02|Solved|Dedicatedworkflowbypassesnormalserial/nulling/radio/alarmloop|Additivecapabilitywithsafehardwareownership|
|H03|Solved|ADS/LoRa shareSPI;samplerinflightpersistsPause/Stop|Explicitlease/quiescence andregressions|
|H04|Solved|NormalWiFiSTA/OFFcalls cantearAPdown|AdditiveAPpolicy|
|H05|Solved|Cachednullingprofile andoptionalCSVpredictionnotenoughfornormalAUTOalarm|Idleprofilerefresh+runtimeinference/alarmcontract|

|H06|Solved|Native router reconnect can starve standalone AP Start|Final source fix review and device gate|
|H07|Solved|Disabled CSV prediction emitted inconsistent wire status|Final serializer projection regression|

|H08|Solved|Host skipped COM even for new capable workflow packages|Flag-gated reconnect and fresh version/ID tests PASS|
|H09|Solved|Running backend still previous validator/upload routing|Manual restart required; automatic review rejected attempted restart|

|H10|Solved|OldGLD13240 and new2164 coexist; probe8/8 reachesoldvalidator|Exclusive listener + childreuse tests; manual oldprocessstop|

|H11|Solved|GLD1002 Model2 unapproved; binding model mismatch and boundprofile1 vs active2|Verify intended model/hardware; only approved model can explicitly bind active profile. Read-only audit complete; no NVS mutation|

## Current work / agent state

Tidak ada agent aktif saat ini. Backend baru dan tiga paket final aktif. Upload serta uji GLD baru belum dilakukan.

## Evidence log

- UserconfirmsnormalCOMcontrol+DatasetWiFi,notallcontrolsoverWiFi. ActualnormalModel1manifest0.8.36/Oct21,notstalereleaseguide0.8.38. No compile/upload authorizedfornewfirmwarechange.

- Heartbeat SLA breach: 227s duringcatalog/auditwork;notbackdated.

- 2026-11-03 13:58:18 Asia/Jakarta: UIcatalog source+testsPASS,exact3finalhotspotExpert/Simple,normalchoicesandlegacyAPI retained.90Hubtests+workflowUI+RunninggoldenPASS. No firmwarebuild/flash; GLDagentimplementingmainthreadownership/nativeidlecompatibility,Integrationaudit complete. Rootmanualpreparation/capturependingfinalcontract.

- 2026-11-03 14:10:29 Asia/Jakarta: Heartbeat SLA breach observed 12 minutes since prior heartbeat, including context recovery. No timestamps backdated. Source implementation exists, final review identified alarm continuity, router reconnect admission, and disabled-prediction projection issues; still open. Manual 14-page PDF rendered and inspected; firmware readiness disclaimer explicit. No compile/hardware.


- 2026-11-03 14:11:01 Asia/Jakarta: Final manual SHA256 69e3c41be39a3235b78a90532b998a527e3320f494dd970b787e0380458946a7; all 14 pages rendered; guide links new PDF. No hardware actions.



- Heartbeat SLA breach: 60s before 14:12:52 during source review.

- 14:12:52: GLD owner reports fixes for alarm continuity, router reconnect admission and disabled prediction projection; Integration reviewing exact final source. Build approval still pending.

- Heartbeat SLA breach: 73s before 14:14:05 during review.

- Heartbeat SLA breach: 118s during final source/manual verification; no backdating.

- 14:16:02: Source frozen at UnifiedMain 2b93d489 and Workflow71493a20; independent source review no blockers, root reran47tests PASS and alarmcontract PASS. 233baselinefiles/226packagefiles unchanged. First embedded-Python module invocation failed import (isolated sys.path), not counted; rerun via PlatformIO Python passed. No compile/upload/COM/WLAN. Waiting user compile confirmation per standing instruction.

- Source issue closures H02-H07 are source-review closures only; build and hardware evidence remain Phase 3. Final PDF hash supersedes earlier hash: ed393da07647591e747b2efddd2fcd27ad41978e9fec3d90369dd2aae97f04de.


- 14:21:12: user approved three parallel compilations and final hotspot package update. Source remains frozen. New build/package/device subitem weights are explicit presentation refinement, no evidence credited yet.

- Heartbeat SLA breach: 129s during compiler dispatch/packager inspection; actual gap recorded.

- 14:23:21: all three real compiler processes concurrently running, starts14:22:02/14:22:14/14:22:29 WIB; no serial uploads.

- Heartbeat SLA breach: 83s before 14:26:31, coordinator checks; no backdating.

- Heartbeat SLA breach: 130s before 14:28:41, coordinator checks; no backdating.

- Heartbeat SLA breach: 77s before 14:29:57, coordinator checks; no backdating.

- Heartbeat SLA breach: 166s before 14:32:43, coordinator checks; no backdating.

- Heartbeat SLA breach: 88s before 14:34:10, coordinator checks; no backdating.

- Heartbeat SLA breach: 77s before 14:35:27, coordinator checks; no backdating.

- Heartbeat SLA breach: 175s during final release verification; actual gap, not backdated.

- 14:38:22: all3builds+strictpackaging+served-byte proofs PASS; three final packages installed, prior dirs archived; automatic approval review rejected service restart before execution. COM7 remains connected and broker running. Source/host/package work complete; backend activation and physical tests still pending. See tmp/hotspot-full-feature-20261103/release-report.md.

- 15:05:31: user screenshot confirms H09 old process13240 rejects capabilities; disk source corrected. Runtime all Dataset transports idle and serial disconnected, MQTT0clients, CH/GW stopped independently. Reduced-risk standard Hub restart also rejected before execution with no detailed reason. No source, package, config or hardware operation in diagnosis; manual end PID12228/13240 + launcher required. No further automatic retry. Heartbeat gap during resumed diagnosis from first observed14:59:48 to this update recorded; earlier interval was waiting external activation.

- 15:13:44: newHub21160/GLD2164 aftermanualrestart, oldGLD13240 persists. Controlled schema0/fakeCOM999 probe rejects8/8 withold capabilitieserror beforehardware. Bounded exclusive-startup/sourceguard authorized. Heartbeat gap in resumeddiagnosis observed since previous update; waitingmanualgate interval excluded.

- Heartbeat SLA breach 91s during duplicate-runtime/source review before 15:15:14; not backdated.

- 15:15:14: Integration implementation underway: exclusive Windows bind, bind-before-broker, child identity reuse/no duplicate ownership, PID/capability health metadata. No process control or actual firmware action.

- Heartbeat SLA breach 335s during diagnostic/source review and user-managed closure before 15:20:48; no backdating.

- 15:20:48: User manually closed stale processes. Start-only standardHub launch succeeded with PID21096, GLD21584, CH19856, GW34548; authenticated broker1884 atGLD21584 running. Live schema0/COM999 probe for3models now accepts capabilities then rejectsinvalidschema BEFOREhardware, packageGEThashesmatch, headlessUIModel2+exact3choices+noJSerrorsPASS. Root105Hub+4capvalidatorPASS. ExclusiveHTTP/startupownershipguard testedactualWindows ephemeralports. H09/H10closed. No actualfirmwareupload/reset.

- 15:49:49: User resumed read-only binding/profile audit. GET_INFO/GET_STATUS on alreadyconnectedCOM7; allwirelessinactive. LiveModel2 unapproved; fingerprintmismatch, bound1/active2; sensorsvalid/primed,ML,nullingapplied,DACready. GLDsource reviewer confirmsBindwouldrejectbeforeNVSwrite. No firmware,calibration,NVS,modelapproval,mode,port/restart change. Preferredcorrectmodel questionpending; audit complete, no activeworker. Reports tmp/binding-audit-20261103/live-snapshot.json and source-review.md. Overall remains93%, no new broadphysicalacceptance claimed.

- 2026-11-03 16:26:31: three-model feature-parity package release complete; see docs/GLD-THREE-MODEL-SYNC-TRACKER.md. Model2 approval nowenabledinnewpackage; sharedbindingUIcomparesbound/activeIDs. H11devicebinding remainsopenuntilmanualnewfirmwareupload+explicitbind; nohardwarewriteorHublaunchperformed.

- 2026-11-03 17:36:01: H11closedbyfreshUSBModel2status: productiontrue,bindingmatches,bound2active2,inferenceValidtrue. WirelessTCP81timeoutisnewseparateissue tracked docs/GLD-DATASET-CONNECTION-TRACKER.md; no calibration/binding mutation performed.
