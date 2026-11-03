# Agreed backend/UI contract for release

No COM/device/Wi-Fi actions in development tests. Existing collectors/firmware
packages remain protected. New source files only for protocol3 and logical CSV;
root owns bridge.py/platform/UI, backend worker owns recorder/service/tests.

Implement `DatasetWorkflowService(output_dir, platform, event_callback,
websocket_factory=None, ...)` in `apps/gld-operator/dataset_workflow.py`, with
separate protocol3 engine if useful in `wireless_dataset_workflow.py`.
Methods: `snapshot`, `scan`, `select(device_id)`, `connect(device_id,password)`,
`choose_file`, `configure(payload)`, `lock(locked)`, `start`, `pause`, `resume`,
`stop`, `continue_recording`, `reset`, `disconnect`, `export_csv`.

Root supplies `WindowsWorkflowPlatform` in workflow_platform.py:
`scan()->[{ssid,device_id,name}]`, `join(ssid,password='')`, `choose_file()->path
orNone`, `validate_file(path)->validatedPath`. Passwords only process memory and
native Windows profile; not browser storage/logs/state/commandline/tempXML.
Tests inject inert platform and fake peers. Don't execute the real platform.

Snapshot fields shared with UI: `devices`, `selected_device_id`, `selected_ssid`,
`device_id`, `connected`, `ready`, `prediction_available`, `locked`, `state`,
`csv_path`, `label`, `mode`(direct/replay), `fields`({prediction,gain,status,timing}),
`configured`, `steps`({scan,device,connection,file,fields,mode,label}), `count`,
`history`(raw8channelrows+row_id+segment_id+prediction), `verification`
({verified,count,sha256,message}), `error`, `cleanup_pending`, `can_continue`,
`complete`. All action replies full snapshots. State/error/operator messages
Indonesian. SSE namespace `dataset_workflow` (root forwards browser event).

Root API prefix `/api/dataset-workflow`, GETstate; POSTscan/select/connect/
choose-file/configure/lock/start/pause/resume/stop/continue/reset/disconnect/export.
Select bodydevice_id; connect bodydevice_id/password; configure bodylabel/mode/
fields; lock bodylocked. Caller cannot supply arbitrary filesystempath: destination
comes from native picker injected platform only. Join selectedssid exactlyonce
per explicitConnect, then authenticated hello matching ID+profile+ready; arbitrary
nonGLDSSIDs forbidden. Future recovery may only rejoin exact ownedGLD and must
never start newacquisition or touch anothernetwork/device.

Seven step gates: successfulscan, selection, authenticatedreadyconnection,
writablefiledestination, validfields, validmode, validlabel. Allmustpassbefore
Lock; settingsvisiblebutdisabledwhilelocked. Start/Pause/Stop shownonlylocked.
Resetallowedidle/stopped/confirmedpaused; pausedResetmust firstStop/drain/verify
ownedremote session, preservefiles, thenclearform. Unlockforbiddenwhileactive,
paused/recovering/cleanup/stop_pending. CSVschema/device/profile/model must remain
compatible acrossContinue; changingconfiguration afterStop must require newfile/
Reset or clearlyinvalidateContinue, never silentlyappendincompatibleheaders.

Protocol3 supports realPAUSE_DATASET/CONTINUE_DATASET with transition_seq and
boot/SID/label/profile, acquisitionpaused keptactiveconnection; Resume transport
RESUME_DATASET mustnotunpause. DurableACK afteractualCSV+canonicalledger fsync.
Store canonical data including quality/prediction, project optional publiccolumns
into userselectedCSV. Onpartialwrite/failure neverACK beyonddurableprefix; rollback
uncommittedtails before retry and retainownershipuntilreconciled.

One logicalrecording/file spansGLDsegments: postStopContinue opens NEWGLDSID,
seq0 with separate segment_id/globalrow_id while appending samefile. Verifyexact
previousfilehash/schema/device/profile/modelbeforeappend, rejectexternalmutation.
Keep userpassword onlyRAM throughlogicalrecording toenableoneclickContinue, clear
onReset/Disconnect. NeveroverwriteexistinguserCSV; createexclusivefirstStart.

Stop waitsStopACK+terminalsummary+contiguousprefix, fsync/closes then readsactual
targetCSV and compares ALL rows/fields againstauthoritativebackend ledger (not
last7200UIhistory), thensetsverification. Popup onlyafterverified; incomplete
capturemustsayincomplete, notsuccesscomplete. Export downloadableCSVsamefile.

Directfirsttransportloss freezesPUBLICCSV/count/historypermanently forsegment,
incomplete; private exactownedSIDStop/Resume/drain to durabletemp ledger releases
session for nextStart/Continue. Never publishcleanuprows to publicfile/history.
Recoverymode sameSID/file replay;5min/overflowterminalincompleterecoversretained.
Neither mode stopsforeignidentity/rebootsessions or resendsambiguousStart.

Tests require actual8values+allmetadata, mutablepredictionstatus/nulls, Pause no
newrecorduntilContinue, Stopfrompaused, Continueonefile/newSID, filetamper/disk
fail-beforeACK, Directcutoff/privatecleanup/newsession, Replaydrop, cancel/Reset
ownership, schema/configguards and oldcollectorhashes. RealC++firmwarebuildproof
is separate from synthetic protocolpeer. Root mergesroutes/UIDOM and testsbrowser.
