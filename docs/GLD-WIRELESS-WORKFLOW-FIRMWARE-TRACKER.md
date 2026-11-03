# GLD wireless workflow firmware



Last tracker heartbeat: 2026-11-02 23:37:50 Asia/Jakarta (build complete; physical deferred)

Last evidence update: 2026-11-02 23:37:50 Asia/Jakarta



## Progress dashboard



|Scope|Progress|Status|Next gate|

|---|---:|---|---|

|**Overall**|**95%**|Builds complete; device deferred|Source/review/threecompilesPASS; physicalgatepending|

|1. Contract and protection|100%|Complete|Workflow semantics and protected hashes|

|2. Isolated firmware source|100%|Implemented source|Independent review phase3; firmwarebuild phase4|

|3. Source checks and review|100%|Complete|37checks+independent source review accepted|

|4. Build and device proof|50%|BuildsPASS; hardwaredeferred|NoGLD/COM7available|



Weights20/50/20/10%; equal items within phases. Scope is source preparation. Compiler success/timing/device proof remain separate; source checks are not firmware runtime proof.



## Work items



|ID|Work item|Progress|Status|Next gate|Last update|

|---|---|---:|---|---|---|

|1.1|Versioned protocol and protected baseline|100%|Complete|Closed|Protocol3 contract and baselinehashes saved; physical/build separate.|

|2.1|Real Pause/ContinueAcquisition and durable replay state|100%|Complete for source scope|Peerreview/compiledevicegates remain separate|Newprotocol3module, epoch/transitionguards, paused Stop/drain source exists.|

|2.2|Optional real prediction and readiness capability|100%|Complete for source scope|Peerreview/compiledevicegates remain separate|Capturedframe inference/MAV/readiness/nullstatus; oldruntime guarded.|

|2.3|Model1/2/3isolated flags/privatepreparer|100%|Complete for source scope|Peerreview/compiledevicegates remain separate|3isolatedtargets;7temporarycredentialtests PASS; realcredentials untouched.|

|3.1|Source/credential regression|100%|Complete for source scope|Peerreview/compiledevicegates remain separate|37dataset source/credential checks PASS; not C++ runtime execution.|

|3.2|Independent protocol/main hook review|100%|Complete|Closed for source scope|Pause/Stop epochs, pauseddrain/summary, transitions, model/nullfields and oldflow isolation reviewed; no blocking source finding.|

|4.1|Three firmware builds|100%|Complete|Closed|Model1/2/3parallelPASS; RAM52.9% flash16.8%, newartifactsseparate.|

|4.2|Realdevice500ms/pause/prediction/replay|0%|Deferred|Device and upload authorization|No COM7|



## Issue register



|ID|Status|Issue|Closure gate|

|---|---|---|---|

|W01|Solved (source)|Protocol2 lacked acquisitionPause|Newprotocol3 Pause/Continue source; execution proof remains4.1/4.2.|

|W02|Solved (source)|Hotspot lacked prediction fields|Optional gated NN/MAV source and per-frame valid/null prediction; actualmodeltiming W04.|

|W03|Solved (checked scope)|Protect workingprotocol1/2/packages|233protectedhashes+prior62CSV unchanged; oldselectedUnified/environment source checksPASS.|

|W04|Deferred|Inference500msCPU/RAMbudget unmeasured|Threebuilds+realdevice timing/overrun|

|W05|Solved (PC)|Hub protocol3 support required|Newwizard+isolatedservice implemented,135appchecks+wire/browserproofPASS; see release tracker.|



## Current work / agent state

Tidak ada agent aktif saat ini. Source, build and newHub PC integration are complete. Physical/nativeoperator evidence awaits device availability and authorized upload; no automatic device work is running.

## Evidence log



- 2026-11-02 22:18:26: User asks firmware ready for acceptedwizard. Existing answers settle truePause, sameCSVlogicalsegments, gainmetadata, optionalprediction. No repeated questions needed. Source-only preparation; no firmwarebuild/flash/COM/network/serviceaction. Existing protocol2packagesremainusable withcurrentHub.



- 2026-11-02 22:21:57: Contract accepted: realPause, ContinueAcquisition vs transportResume, sameCSVpostStop newSIDsegmentsinHub, per-frame realpredictions explicitvalid/null,500ms/640ring/window8/5min. Threeisolatedtargets andnewprivatepreparer written but notcompiled/runagainstrealcredentials. Overall20%=20×100+50×0+20×0+10×0.


- Tracker encoding corrected to UTF-8 after Windows default encoding rejected the multiplication symbol. Earlier initial-contract authoring gap22:18:26–22:21:57 was211s, a Heartbeat SLA breach; no implementation evidence inferred from timing.

- Heartbeat SLA breach: observed66s gap during source authoring/review; no backdating.

- Heartbeat SLA breach: observed83s gap during source authoring/review; no backdating.

- 2026-11-02 22:28:25: Rootacceptedsourceimplementationand37Python dataset source/credential tests PASS. ExistingReplay18testskeepoldhashconstants; addedworkflowremovalguardprovesoldselectedUnifiedbehavior/existingenvconfigsame. InitialnewbaselineCP1252textdigest correctedtoverifiedUTF8gitHEAD9ca66d30…; no firmwarebaselineconstant weakened. Overall80%=20×100+50×100+20×50+10×0. No C++compiler or devicebehavior claim. Peer review active.

- 2026-11-02 22:30:48: SOURCE PREPARATION DONE. Overall90%=20×100+50×100+20×100+10×0. Independentreview accepts frozen source;37Python source/credential tests PASS. Protected233hashes+previous62CSV unchanged. No actualprivatecredentials read/generated, no firmwarecompiler, COM/WiFi/network/service/upload/NVS/package action. Exacthashes+limitations in tmp/wireless-workflow-firmware/verification-report.json; review in samefolder/review.md.

## Handoff

- Newtargets: gld_model_1_dataset_workflow_wifi, gld_model_2_dataset_workflow_wifi, gld_model_3_dataset_workflow_wifi. ExistingHubpackages remain protocol2 and unchanged. No version/releasebinary has been produced.
- Sourcecontract: docs/firmware/gld-dataset-wireless-workflow-contract.md; no-workflow Unified text matches UTF8 baseline9ca66d309fe90e327458ac377a8ca8d9b81d5e3cee7600b0a957228cc931dbbe.
- Source verification: bundledPython `-m unittest discover -s firmware/tests -p 'test_dataset*.py' -q`,37PASS. These tests inspect C++ source and execute credentialpreparer temporaryfixtures; they never execute the C++ device state machine.
- Firstapprovedbuild copies matching protocol2password privately into distinct protocol3config; no rotation of oldpassword. Model/pin/nulling settings inherited from matching oldtarget.
- Sourcefeatures: realPause/ContinueAcquisition preservingSID/seq, transportResume separate; pausedStop/drain; capabilities and optionalper-frame prediction withMAVwarmup/modelbindinggate/nullinvalidfields. Duplicate lasttransition afterStop returns historicalACKpluscurrentterminalstate without mutation; futureHub must reconcile currentstate, notACKalone.
- Compile requires confirmation per user's prior request. Ifapproved, use3independent modelagents in parallel, preserveoldartifacts and inspectactualcompiler/RAMresults beforepackagework. No flash/upload until authorized; GLD is currently unavailableatCOM7.
- NewHubwizard nowimplements protocol3, OSscan/join/filepicker sources, logicalCSVsegments, Lock and verifiedcontrols. Current legacycollectors stillrejectprotocol3 bydesign; the isolatednewserviceaccepts it. PC/browser/CSV gatesPASS; physical/nativeoperator proof remains deferred.

- 2026-11-02 22:54:19: Userauthorizedproceedfinishall; threeactualcompilesPASS. Originalcompilepermissiondeferralresolved; hardwaregate remains. Completewizardrelease now tracked in GLD-WIRELESS-WORKFLOW-RELEASE-TRACKER.md.

- 2026-11-02 23:37:50: FinalreleasePC/build/manual/appactivationcomplete. Authoritativecurrenttracker GLD-WIRELESS-WORKFLOW-RELEASE-TRACKER.md and report firmware/gld-dataset-workflow-release-20261102.md supersede originalsource-onlyhandoff. Compileconfirmationwasresolvedbyuserinstructionfinishall; actualuploadhasnotoccurred.
