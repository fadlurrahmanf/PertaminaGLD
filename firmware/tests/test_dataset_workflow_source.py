"""Source isolation gates ONLY. No compiler, board, socket or runtime proof."""
from __future__ import annotations
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'firmware/gld/src/GldDatasetWorkflowWifi.cpp'
BUFFER = ROOT / 'firmware/gld/include/GldDatasetWorkflowBuffer.h'
BASELINE = ROOT / 'firmware/tests/fixtures/workflow-baseline.json'
# Verified pre-workflow HEAD, decoded explicitly UTF-8. Windows' default
# cp1252 decoding produces another digest of identical comment bytes.
OLD_UNIFIED = '9ca66d309fe90e327458ac377a8ca8d9b81d5e3cee7600b0a957228cc931dbbe'
OLD_ENVIRONMENTS = 'fe1c34e2087a57c7b654d0ab484387bee5fee50d3a73ff2fea1a2a8e0ee3f8ed'
spec = importlib.util.spec_from_file_location('workflow_old_isolation', Path(__file__).with_name('test_dataset_replay_source.py'))
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


class WorkflowIsolation(unittest.TestCase):
    def test_existing_modules_packages_and_csv_match_parent_baseline(self):
        baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(baseline['hashes']), 233)
        for relative, checksum in baseline['hashes'].items():
            self.assertNotIn('credentials.local.json', relative, 'Never inspect real private credentials')
            with self.subTest(path=relative):
                data = (ROOT / relative.replace('\\', '/')).read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != checksum and Path(relative).suffix in {'.cpp', '.h', '.py'}:
                    # Git may check out text files with CRLF on another Windows PC.
                    # Only newline conversion is tolerated; source bytes stay pinned.
                    actual = hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
                self.assertEqual(actual, checksum)
        previous_csv = Path(baseline['previousCsv'])
        self.assertFalse(previous_csv.is_absolute(), 'Baseline must be portable')
        self.assertNotIn('..', previous_csv.parts)
        self.assertEqual(hashlib.sha256((ROOT / previous_csv).read_bytes()).hexdigest(), baseline['previousCsvSha256'])

    def test_workflow_disabled_preserves_all_old_unified_source(self):
        source = (ROOT / 'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf-8')
        selected = old.absent_workflow(source)
        meaningful = '\n'.join(line for line in selected.splitlines() if line.strip())
        self.assertEqual(hashlib.sha256(meaningful.encode()).hexdigest(), OLD_UNIFIED)
        self.assertNotIn('datasetworkflowwifi', selected)

    def test_isolation_selector_keeps_old_replay_and_plain_branches(self):
        source = '#if PGL_GLD_DATASET_WORKFLOW\nnew\n#elif PGL_GLD_DATASET_REPLAY\noldreplay\n#else\noldplain\n#endif\n'
        self.assertEqual(old.absent_workflow(source), '#if PGL_GLD_DATASET_REPLAY\noldreplay\n#else\noldplain\n#endif\n')
        self.assertEqual(old.absent_workflow('#if OLD\nold\n#elif PGL_GLD_DATASET_WORKFLOW\nnew\n#else\nplain\n#endif\n'),
                         '#if OLD\nold\n#else\nplain\n#endif\n')

    def test_exact_three_environments_inherit_matching_stage_one(self):
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read(ROOT / 'firmware/platformio.ini', encoding='utf-8')
        new = {f'env:gld_model_{model}_dataset_workflow_wifi' for model in (1, 2, 3)}
        selected = {name for name in config.sections() if '-DPGL_GLD_DATASET_WORKFLOW=1' in config[name].get('build_flags', '')}
        self.assertEqual(selected, new)
        previous = {name: dict(config[name]) for name in config.sections() if name not in new}
        self.assertEqual(hashlib.sha256(json.dumps(previous, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), OLD_ENVIRONMENTS)
        for model in (1, 2, 3):
            env = config[f'env:gld_model_{model}_dataset_workflow_wifi']
            self.assertEqual(env['extends'], f'env:gld_model_{model}_dataset_wifi')
            self.assertEqual(env['extra_scripts'], 'pre:tools/prepare_dataset_workflow_wifi.py')
            self.assertNotIn('PGL_GLD_DATASET_REPLAY', env.get('build_flags', ''))
            self.assertIn('-<gld/src/GldDatasetWifi.cpp>', env['build_src_filter'])
            self.assertIn('+<gld/src/GldDatasetWorkflowWifi.cpp>', env['build_src_filter'])
            self.assertNotIn('+<gld/src/GldDatasetReplayWifi.cpp>', env['build_src_filter'])


class WorkflowSourceShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding='utf-8')
        cls.buffer = BUFFER.read_text(encoding='utf-8')
        cls.header = (ROOT / 'firmware/gld/include/GldDatasetWorkflowWifi.h').read_text(encoding='utf-8')
        cls.unified = (ROOT / 'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf-8')

    def test_distinct_acquisition_commands_and_no_secret_logging(self):
        for command in ('START_DATASET', 'PAUSE_DATASET', 'CONTINUE_DATASET', 'RESUME_DATASET', 'STOP_DATASET', 'ACK_SAMPLES'):
            self.assertIn('"' + command + '"', self.source)
        self.assertIn('gld-dataset-wifi/3', self.source)
        self.assertNotRegex(self.source, r'Serial\.|logPrintf\(|printf\(.*password|Preferences')

    def test_ap_loss_restarts_ap_and_listener_without_dropping_retained_samples(self):
        transport = old.body(self.source, 'void transmitter(void*)')
        self.assertIn('!nativeBusy.load()', transport)
        self.assertIn('WiFi.getMode() & WIFI_MODE_AP', transport)
        self.assertIn('WiFi.softAPIP() == address', transport)
        self.assertIn('socket.listening()', transport)
        self.assertIn('nextApCheckMs = now + AP_RECOVERY_RETRY_MS', transport)
        self.assertIn('WiFi.softAP(ssid, GLD_DATASET_WORKFLOW_PRIVATE_PASSWORD', transport)
        self.assertIn('socket.beginChecked()', transport)
        self.assertNotIn('retained.clear(', transport)

    def test_cold_boot_pg24_confirmation_does_not_erase_stored_mode(self):
        setup = old.body(self.unified, 'void setup()')
        self.assertIn('GLD_PG24_COLD_BOOT_CONFIRM', setup)
        self.assertIn('stableHigh >= 3', setup)
        self.assertIn('pgl::gld::readGldExternalPower()', setup)
        workflow_fallback = setup.split(
            '#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW\n'
            '    if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY &&', 1)[1].split('#else', 1)[0]
        self.assertIn('currentMode = pgl::gld::GldMode::INFERENCE', workflow_fallback)
        self.assertNotIn('writeGldMode(', workflow_fallback)
        begin = old.body(self.unified, 'void beginDatasetWorkflowIfNeeded()')
        self.assertIn('nextBeginAtMs = now + 5000', begin)

    def test_deferred_dataset_restart_after_stable_external_power(self):
        setup = old.body(self.unified, 'void setup()')
        self.assertIn('workflowDeferredDatasetRestart = batteryPowerMode &&', setup)
        self.assertIn('currentMode == pgl::gld::GldMode::DATASET', setup)
        self.assertIn('RTC_DATA_ATTR uint8_t workflowPowerRecoveryRestartCount', self.unified)
        transition = old.body(self.unified, 'void applyRuntimePowerReading(')
        self.assertIn('workflowDeferredDatasetRestart &&', transition)
        self.assertIn('workflowPowerRecoveryRestartCount == 0', transition)
        self.assertIn('pgl::gld::readGldMode() == pgl::gld::GldMode::DATASET', transition)
        self.assertIn('workflowPowerRecoveryRestartCount = 1', transition)
        self.assertIn('ESP.restart()', transition)
        workflow_power_loss = transition.split(
            '#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW\n'
            '            // Runtime power loss', 1)[1].split('#else', 1)[0]
        self.assertNotIn('writeGldMode(', workflow_power_loss)
        self.assertIn('writeGldMode(pgl::gld::GldMode::INFERENCE)',
                      transition.split('#else', 1)[1])

    def test_ring_has_no_json_and_stores_prediction_with_raw_scan(self):
        self.assertNotIn('Json', self.buffer)
        sample = old.body(self.header, 'struct Sample')
        self.assertIn('RawSample raw{}', sample)
        self.assertIn('Prediction prediction{}', sample)
        self.assertIn('Sample sample{}', old.body(self.buffer, 'struct RetainedSample'))
        self.assertIn('target.sample = sample', old.body(self.buffer, 'bool append('))
        self.assertRegex(self.buffer, r'static_assert\s*\(\s*sizeof\(')
        self.assertRegex(self.buffer, r'640')

    def test_main_thread_acquisition_has_no_wifi_transport_or_extra_ads(self):
        sampler = old.body(self.source, 'void acquireDueSample()')
        self.assertNotRegex(sampler, r'socket\.|WiFi\.|mqtt\.|Json|state\.client|streamEnabled|ADS|ads\.')
        self.assertEqual(sampler.count('captureSample('), 1)
        self.assertIn('acquisitionEpoch', sampler)
        self.assertNotIn('samplerHandle', self.source)
        self.assertNotIn('xTaskCreate(sampler', self.source)
        poll = old.body(self.source, 'void poll()')
        self.assertIn('acquireDueSample()', poll)
        for signature in ('void websocket(', 'void transmitter(void*)'):
            transport = old.body(self.source, signature)
            self.assertNotRegex(transport, r'\b(?:captureSample|predictSample|resetPrediction|isReady|predictionIsReady)\s*\(')

    def test_pause_continue_preserve_ring_and_are_not_transport_resume(self):
        process = old.body(self.source, 'void process(const Command& command)')
        transition = process.split('} else if (strcmp(command.cmd, "PAUSE_DATASET")', 1)[1].split('} else if (strcmp(command.cmd, "STOP_DATASET")', 1)[0]
        for forbidden in ('retained.clear', 'summaryPending =', '++state.generation', 'acknowledgePrefix'):
            self.assertNotIn(forbidden, transition)
        for required in ('command.transitionSequence != state.transitionSequence + 1',
                         '++state.acquisitionEpoch', 'state.paused = pause', 'state.sampling = !pause',
                         'state.nextDue = millis() + INTERVAL_MS', 'transition_identity_mismatch',
                         '!strcmp(command.cmd, state.transitionCommand)', '!strcmp(command.commandId, state.transitionId)'):
            self.assertIn(required, transition)
        self.assertLess(transition.index('++state.acquisitionEpoch'), transition.index('ackLocked(command, true, pause'))
        resume = process.split('} else if (strcmp(command.cmd, "RESUME_DATASET")', 1)[1].split('} else if (strcmp(command.cmd, "PAUSE_DATASET")', 1)[0]
        self.assertNotIn('state.paused =', resume)
        self.assertNotIn('state.sampling =', resume)

    def test_stop_invalidates_inflight_and_summary_requires_not_paused_and_all_acked(self):
        stop = old.body(self.source, 'void stopLocked(')
        self.assertIn('++state.acquisitionEpoch', stop)
        self.assertIn('state.paused = false', stop)
        self.assertIn('state.incomplete = state.incomplete || incomplete', stop)
        process = old.body(self.source, 'void process(const Command& command)')
        self.assertIn('if (state.sampling || state.paused) stopLocked("operator_stop", false)', process)
        poll = old.body(self.source, 'void poll()')
        self.assertIn('!state.sampling && !state.paused && state.summaryPending && retained.size() == 0', poll)
        self.assertIn('retained.acknowledgedNext() == retained.nextSequence()', poll)
        sampler = old.body(self.source, 'void acquireDueSample()')
        self.assertLess(sampler.index('acquisitionEpoch != state.acquisitionEpoch'), sampler.index('retained.append('))

    def test_durable_ack_bounds_and_control_order_are_explicit(self):
        ack = old.body(self.source, 'bool acknowledgeLocked(')
        self.assertIn('command.nextSequence > state.offeredNext', ack)
        self.assertIn('strcmp(command.bootId, state.boot)', ack)
        sender = old.body(self.source, 'void transmitter(void*)')
        self.assertLess(sender.index('xQueueReceive(controls'), sender.index('sampleMessageLocked'))
        self.assertIn('Lock lock', sender[:sender.index('xQueueReceive(controls')])
        self.assertIn('wire.generation == state.generation', sender)

    def test_prediction_schema_map_validation_and_encoding_fail_closed(self):
        wire = old.body(self.source, 'bool sampleMessageLocked(')
        for field in ('predicted_class', 'gas_class', 'confidence'):
            self.assertIn('prediction["' + field + '"] = nullptr', wire)
        self.assertIn('if (valid)', wire)
        self.assertIn('doc.overflowed()', wire)
        self.assertIn('measureJson(doc) >= JSON_BYTES', wire)
        self.assertIn('stopLocked("payload_encoding", true)', wire)
        sampler = old.body(self.source, 'void acquireDueSample()')
        self.assertIn('sample.prediction.gasClass != modelInfo.classMap[sample.prediction.predictedClass]', sampler)
        for feature in ('pause', 'continue', 'durable_replay', 'prediction', 'requires_protocol3_client'):
            self.assertIn('capabilities["' + feature + '"]', self.source)

    def test_workflow_only_prediction_uses_current_frame_and_main_thread_warmup(self):
        callback = old.body(self.unified, 'void predictDatasetWorkflow(')
        self.assertIn('sample.voltage[channel]', callback)
        self.assertIn('movingAvg.add(', callback)
        self.assertIn('MIN_PRIMED_COUNT', callback)
        self.assertIn('PredictionStatus::Warmup', callback)
        self.assertIn('network->predict(averaged, confidence)', callback)
        self.assertNotRegex(callback, r'\bads\s*(\.|->)|readChannel\s*\(|captureDatasetWifi\s*\(')
        gate = old.body(self.unified, 'bool datasetWorkflowPredictionReady()')
        for required in ('PRODUCTION_APPROVED', '!FIELDTEST_MODEL_UNVERIFIED', '!SIMULATED_MODEL_OUTPUT',
                         'isModelBindingValid', 'modelFingerprint == fingerprint',
                         'modelBinding.nullingProfileId == nullingProfileId', 'runtimeDacVerificationReady()'):
            self.assertIn(required, gate)
        self.assertIn('resetPrediction()', old.body(self.source, 'void acquireDueSample()'))
        self.assertNotIn('predictDatasetWorkflow', old.absent_workflow(self.unified))

    def test_csv_prediction_option_never_disables_native_inference_or_alarm(self):
        acquisition = old.body(self.source, 'void acquireDueSample()')
        self.assertIn('sample.predictionEnabled = predictionEnabled', acquisition)
        self.assertNotRegex(acquisition, r'if\s*\([^\n]*predictionEnabled')
        self.assertNotIn('predictionIsReady()', acquisition)
        callback = old.body(self.unified, 'void predictDatasetWorkflow(')
        for required in ('latestSensorGain[channel] = sample.gain[channel]',
                         'latestSensorStatus[channel] = sample.status[channel]',
                         'latestSensorVoltage[channel] = averaged[channel]',
                         'lastResult = {result.gasClass', 'lastInferenceValid = true',
                         'sensorFaultActive = false',
                         'updateAlarmOutputs(lastResult.gasClass != pgl::protocol::GLD_GAS_CLEAR)'):
            self.assertIn(required, callback)
        # Successful non-clear frames must keep the physical alarm steady;
        # only failed exits clear AUTO through the native invalid policy.
        invalid = old.body(callback, 'struct InvalidInferenceGuard')
        self.assertIn('if (!lastInferenceValid)', invalid)
        self.assertIn('driveAlarmOutputs(false)', invalid)

    def test_disabled_csv_prediction_projects_disabled_null_protocol_even_after_native_inference(self):
        wire = old.body(self.source, 'bool sampleMessageLocked(')
        self.assertIn('record->sample.predictionEnabled && result.status == PredictionStatus::Valid', wire)
        self.assertIn('switch (record->sample.predictionEnabled ? result.status : PredictionStatus::Disabled)', wire)
        self.assertIn('case PredictionStatus::Disabled: predictionStatus = "disabled"', wire)
        for field in ('predicted_class', 'gas_class', 'confidence'):
            self.assertLess(wire.index('prediction["' + field + '"] = nullptr'), wire.index('if (valid)'))

    def test_session_config_lease_outlives_pause_and_replay_until_final_disconnect(self):
        process = old.body(self.source, 'void process(const Command& command)')
        self.assertIn('state.sessionLease = true', process)
        self.assertNotIn('state.sessionLease = false', process)
        poll = old.body(self.source, 'void poll()')
        self.assertIn('!state.sampling && !state.paused && retained.size() == 0 &&', poll)
        self.assertIn('state.summarySent && state.client < 0) state.sessionLease = false', poll)
        refresh = old.body(self.source, 'void refreshRuntime(')
        self.assertIn('if (!state.sessionLease)', refresh)
        self.assertIn('invalidated = state.profile != nullingProfileId', refresh)
        self.assertIn('state.profile = nullingProfileId', refresh)
        self.assertIn('stopLocked("invalid_sample_or_power", true)', refresh)

    def test_native_busy_admission_precedes_start_and_resume_success(self):
        process = old.body(self.source, 'void process(const Command& command)')
        self.assertIn('command.nativeBusy || nativeBusy.load()', process)
        self.assertLess(process.index('"native_operation_busy"'), process.index('retained.clear()'))
        transition = process.split('} else if (strcmp(command.cmd, "PAUSE_DATASET")', 1)[1].split('} else if (strcmp(command.cmd, "STOP_DATASET")', 1)[0]
        self.assertIn('!pause && (command.nativeBusy || nativeBusy.load())', transition)
        self.assertLess(transition.index('"native_operation_busy"'), transition.index('state.paused = pause'))
        websocket = old.body(self.source, 'void websocket(')
        self.assertIn('command.nativeBusy = nativeBusy.load()', websocket)

    def test_native_serial_priority_paths_and_mutations_respect_session_lease(self):
        reject = old.body(self.unified, 'bool rejectWorkflowMutation(')
        self.assertIn('ownsSession()', reject)
        self.assertIn('workflowReadOnlyCommand(command.type)', reject)
        self.assertIn('"busy"', reject)
        dispatch = old.body(self.unified, 'void handleSerialCommand(')
        self.assertLess(dispatch.index('rejectWorkflowMutation(command)'), dispatch.index('switch (command.type)'))
        parser = old.body(self.unified, 'void checkSerial() {')
        self.assertLess(parser.index('rejectWorkflowMutation(parsed)'), parser.index('restartFromSerialCommand()'))
        self.assertLess(parser.index('rejectWorkflowMutation(parsed)'), parser.index('onCancelFullScaleSweep()'))
        readonly = old.body(self.unified, 'bool workflowReadOnlyCommand(')
        for command in ('GetInfo', 'GetStatus', 'GetTelemetry', 'AppPing', 'GetQcStatus'):
            self.assertIn('Type::' + command, readonly)
        for command in ('Restart', 'RetryNulling', 'SetMode', 'RunBootCheck', 'SetSessionMcpJson', 'ManualLoraTx'):
            self.assertNotIn('Type::' + command, readonly)

    def test_workflow_keeps_native_mode_supervision_and_excludes_second_bus_owner(self):
        setup = old.body(self.unified, 'void setup()')
        self.assertIn('currentMode = pgl::gld::readGldMode()', setup.split('#elif defined(PGL_GLD_DATASET_WIFI)', 1)[0])
        loop = old.body(self.unified, 'void loop()')
        for service in ('firmwareServiceTick()', 'reconcileRuntimePowerMode()',
                        'serviceGld1TxStatusLedFlash(millis())', 'serviceSht40()'):
            self.assertIn(service, loop)
            self.assertLess(loop.index(service), loop.index('if (workflowLease &&'))
        self.assertLess(loop.index('refreshRuntime(nullingProfileId)'), loop.index('reconcileRuntimePowerMode()'))
        self.assertLess(loop.index('if (workflowLease &&'), loop.index('maintainBootReportRecovery()'))
        self.assertLess(loop.index('if (workflowLease &&'), loop.index('runScan()'))
        self.assertLess(loop.index('if (workflowLease &&'), loop.index('runGld1LoraTxAttempt()'))
        self.assertIn('!batteryPowerMode && pgl::gld::readGldExternalPower()', loop)

    def test_transport_ownership_does_not_clear_a_valid_native_alarm_or_mav(self):
        loop = old.body(self.unified, 'void loop()')
        edge = old.body(loop, 'if (workflowLease != workflowHadLease)')
        self.assertNotIn('resetDatasetWorkflowPrediction(', edge)
        self.assertNotIn('movingAvg.reset(', edge)
        self.assertNotIn('driveAlarmOutputs(', edge)
        acquisition = old.body(self.source, 'void acquireDueSample()')
        self.assertNotIn('predictionEpochSeen', acquisition)
        self.assertIn('if (!valid && resetPrediction != nullptr) resetPrediction()', acquisition)
        process = old.body(self.source, 'void process(const Command& command)')
        self.assertNotIn('resetPrediction(', process)

    def test_native_network_operations_preserve_workflow_ap(self):
        offline = old.body(self.unified, 'void disableNetworkForOfflineMode(')
        self.assertIn('datasetworkflowwifi::available()', offline)
        self.assertIn('WiFi.disconnect(false)', offline)
        self.assertIn('WiFi.mode(WIFI_AP)', offline)
        station = old.body(self.unified, 'bool connectWifi()')
        self.assertIn('available() ? WIFI_AP_STA : WIFI_STA', station)
        begin = old.body(self.source, 'bool begin(')
        self.assertIn('WIFI_AP_STA : WIFI_AP', begin)
        initializer = old.body(self.unified, 'void beginDatasetWorkflowIfNeeded()')
        self.assertIn('batteryPowerMode', initializer)
        self.assertIn('!pgl::gld::readGldExternalPower()', initializer)
        self.assertIn('if (network == nullptr)', initializer)

    def test_standalone_ap_client_is_not_starved_by_native_dataset_reconnect(self):
        station = old.body(self.unified, 'bool connectWifi()')
        workflow, normal = station.split('#else', 1)
        self.assertIn('workflowWifiAttemptStartedMs < WIFI_TIMEOUT_MS', workflow)
        self.assertIn('workflowWifiRetryAtMs', workflow)
        self.assertIn('datasetworkflowwifi::clientConnected()', workflow)
        self.assertIn('datasetworkflowwifi::ownsSession()', workflow)
        self.assertIn('WiFi.disconnect(false)', workflow)
        self.assertNotIn('serviceDelay(', workflow)
        self.assertIn('serviceDelay(50)', normal)
        setup = old.body(self.unified, 'void setup()')
        dataset = setup[setup.index('if (currentMode == pgl::gld::GldMode::DATASET)'):]
        self.assertLess(dataset.index('beginDatasetWorkflowIfNeeded();'),
                        dataset.index('connectWifi();'))
        broker = old.body(self.unified, 'bool mqttConnect() {')
        self.assertIn('clientConnected() || WiFi.status() != WL_CONNECTED) return false', broker)
        self.assertLess(broker.index('clientConnected()'), broker.index('mqtt.connect('))
        loop = old.body(self.unified, 'void loop()')
        native_dataset = loop.split('} else if (currentMode == pgl::gld::GldMode::DATASET)', 1)[1]
        background = old.body(native_dataset, 'if (!pgl::gld::datasetworkflowwifi::clientConnected())')
        self.assertIn('maintainWifi()', background)
        self.assertIn('maintainMqtt()', background)
        hello = old.body(self.source, 'void websocket(').split('if (type != WStype_TEXT)', 1)[0]
        self.assertIn('const bool ready = state.ready;', hello)
        self.assertNotIn('!nativeBusy.load()', hello)

    def test_placeholder_router_does_not_start_station_beside_workflow_ap(self):
        configured = old.body(self.unified, 'bool workflowNativeNetworkConfigured()')
        self.assertIn('strcmp(runtimeConfig.wifiSsid, "CHANGE_ME") != 0', configured)
        self.assertIn('strcmp(runtimeConfig.mqttHost, "CHANGE_ME_MQTT_HOST") != 0', configured)
        station = old.body(self.unified, 'bool connectWifi()').split('#else', 1)[0]
        self.assertLess(station.index('if (!workflowNativeNetworkConfigured()) return false;'),
                        station.index('WiFi.mode('))
        self.assertLess(station.index('if (!workflowNativeNetworkConfigured()) return false;'),
                        station.index('WiFi.begin('))
        broker = old.body(self.unified, 'bool mqttConnect() {')
        self.assertLess(broker.index('if (!workflowNativeNetworkConfigured()) return false;'),
                        broker.index('mqtt.connect('))

    def test_workflow_ml_gate_accepts_each_models_actual_dual_input_api(self):
        # Characterize the model API independently from the workflow caller.
        # These source-contract checks do not execute TFLite or replace a
        # compile and real-device prediction check.
        workflow_setup = self.unified.split(
            '// Optional ML allocation cannot disable otherwise valid raw Dataset.', 1)[1]
        gate = re.search(r'mlReady\s*=\s*(.*?);', workflow_setup, re.S).group(1)
        for model in (1, 2, 3):
            with self.subTest(model=model):
                directory = ROOT / f'firmware/gld/models/model_{model}'
                metadata = (directory / 'ModelMetadata.h').read_text(encoding='utf-8')
                network = (directory / 'NeuralNetwork.cpp').read_text(encoding='utf-8')
                constants = dict((name, int(value)) for name, value in re.findall(
                    r'constexpr int\s+(EXPECTED_\w+_ELEMENTS)\s*=\s*(\d+)', metadata))

                def numeric(expression):
                    expression = re.sub(r'pgl::gld::model::(EXPECTED_\w+_ELEMENTS)',
                                        lambda match: str(constants[match[1]]), expression)
                    expression = expression.strip().strip('()').strip()
                    self.assertRegex(expression, r'^\d+(?:\s*\+\s*\d+)*$')
                    return sum(map(int, expression.split('+')))

                getter = old.body(network, 'int NeuralNetwork::getInputSize()')
                self.assertIn('if (!initialized)', getter)
                returned = re.findall(r'return\s+([^;]+);', getter)
                self.assertEqual(numeric(returned[0]), 0)
                actual_inputs = numeric(returned[-1])
                self.assertEqual(actual_inputs, constants['EXPECTED_ADC_INPUT_ELEMENTS'] +
                                 constants['EXPECTED_EVIDENCE_INPUT_ELEMENTS'])
                self.assertGreater(constants['EXPECTED_EVIDENCE_INPUT_ELEMENTS'], 0)
                actual_outputs = constants['EXPECTED_OUTPUT_ELEMENTS']

                def accepts(*, exists=True, initialized=True, inputs=actual_inputs,
                            outputs=actual_outputs):
                    expression = gate.replace('network != nullptr', f'{int(exists)} != 0')
                    expression = expression.replace('network->isInitialized()', str(int(initialized)))
                    expression = expression.replace('network->getInputSize()', str(inputs))
                    expression = expression.replace('network->getOutputSize()', str(outputs))
                    results = []
                    for term in expression.split('&&'):
                        comparison = re.fullmatch(r'\s*(.*?)\s*(==|!=)\s*(.*?)\s*', term, re.S)
                        if comparison:
                            left, operator, right = comparison.groups()
                            equal = numeric(left) == numeric(right)
                            results.append(equal if operator == '==' else not equal)
                        else:
                            results.append(bool(numeric(term)))
                    return all(results)

                self.assertTrue(accepts(), 'Initialized dual-input model rejected by workflow caller')
                self.assertFalse(accepts(exists=False))
                self.assertFalse(accepts(initialized=False, inputs=0, outputs=0))
                self.assertFalse(accepts(inputs=constants['EXPECTED_ADC_INPUT_ELEMENTS']))
                self.assertFalse(accepts(inputs=actual_inputs + 1))
                self.assertFalse(accepts(outputs=actual_outputs + 1))


if __name__ == '__main__':
    unittest.main()
