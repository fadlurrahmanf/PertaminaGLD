"""Extracted production hello + ArduinoJson connected to an inert collector peer.

Only hello serialization is firmware code; Wi-Fi, state, retained ring, radio,
and sampling are fakes. No actual board or firmware binary is exercised.
"""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_dataset_workflow as fixture

ROOT = Path(__file__).resolve().parents[3]
COMPILER = Path(os.environ.get("GLD_HOST_CXX", r"C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe"))


def function(source, name):
    start = source.index(name)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{": depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0: return source[start:index + 1]
    raise ValueError("unclosed source function")


def build_serializer(model, directory, status=False):
    workflow = (ROOT / "firmware/gld/src/GldDatasetWorkflowWifi.cpp").read_text(encoding="utf-8")
    begin = workflow.index("                StaticJsonDocument<2304> hello;")
    end = workflow.index("                accepted = enqueueLocked(hello);", begin)
    block = workflow[begin:end]
    if status:
        block = 'StaticJsonDocument<1024> hello; hello["type"]="status"; hello["state"]="recording"; sessionFields(hello);'
    state = workflow[workflow.index("struct State {"):workflow.index("\n};", workflow.index("struct State {")) + 3]
    constants = '\n'.join(line for line in workflow.splitlines() if line.startswith('constexpr uint32_t INTERVAL_MS') or line.startswith('constexpr const char* PROTOCOL'))
    buffer = (ROOT / 'firmware/gld/include/GldDatasetWorkflowBuffer.h').read_text(encoding='utf-8')
    replay_constants = '\n'.join(line for line in buffer.splitlines() if line.startswith('constexpr size_t REPLAY_CAPACITY') or line.startswith('constexpr uint32_t REPLAY_RETENTION_MS'))
    if replay_constants.count('constexpr') != 2: raise ValueError('missing replay constants')
    source = r'''#include <ArduinoJson.h>
#include <iostream>
#include <string>
#include <cstring>
#include "GldDatasetValidator.h"
#include "ModelMetadata.h"
#include "FirmwareVersion.h"
using namespace pgl::gld;
CONSTANTS
REPLAY_CONSTANTS
STATE
State state;
struct Ring { unsigned total, oldest, acked; unsigned nextSequence(){return total;} unsigned oldestSequence(){return oldest;} unsigned acknowledgedNext(){return acked;} unsigned size(){return total-oldest;} } retained;
struct Model { const char* profileId; const char* scalerProfileId; const char* runtimeVersion; bool productionApproved; unsigned outputElements; const uint8_t* classMap; } modelInfo;
void *predictSample = reinterpret_cast<void*>(1);
FEATURE
SESSION
int main(){
 std::string input; std::getline(std::cin,input); StaticJsonDocument<2304> d;
 if(deserializeJson(d,input)) return 2;
 auto cp=[](char* dst,size_t n,const char* val){std::snprintf(dst,n,"%s",val?val:"");};
 cp(state.device,sizeof state.device,d["device_id"]|""); cp(state.boot,sizeof state.boot,d["boot_id"]|"");
 cp(state.session,sizeof state.session,d["session_id"]|""); cp(state.label,sizeof state.label,d["label"]|""); cp(state.reason,sizeof state.reason,d["reason"]|"");
 state.profile=d["nulling_profile_id"]|0; state.sampling=d["sampling"]|false; state.paused=d["paused"]|false;
 state.transitionSequence=d["transition_seq"]|0; state.predictionEnabled=d["prediction_enabled"]|false;
 state.incomplete=d["incomplete"]|false; state.ready=d["ready"]|false; state.predictionReady=d["prediction_ready"]|false;
#if defined(PGL_GLD_BOARD_PROFILE_GLD_ATEX) && PGL_GLD_BOARD_PROFILE_GLD_ATEX
 state.radioAutoTx=d["radio_auto_tx"]|false;
#endif
 retained.total=d["total_samples"]|0; retained.oldest=d["oldest_seq"]|0; retained.acked=d["acked_next_seq"]|0;
 modelInfo={pgl::gld::model::PROFILE_ID,pgl::gld::model::SCALER_PROFILE_ID,pgl::firmware::GLD_FIRMWARE_VERSION,
 pgl::gld::model::PRODUCTION_APPROVED,pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS,pgl::gld::model::CLASS_MAP};
 BLOCK
 if(hello.overflowed()) return 3; serializeJson(hello,std::cout); return 0;
}'''
    source = source.replace('REPLAY_CONSTANTS', replay_constants).replace('CONSTANTS', constants).replace('STATE', state).replace('FEATURE', function(workflow, 'void featureOrder(')).replace('SESSION', function(workflow, 'void sessionFields(')).replace('BLOCK', block)
    cpp = Path(directory) / f'model{model}.cpp'; exe = Path(directory) / f'model{model}.exe'
    cpp.write_text(source, encoding='utf-8')
    # The bundled MinGW supports C++1z but not C++17 nested namespace syntax;
    # expand namespace spelling only, preserving all production constants.
    headers = ((ROOT/'firmware/gld/include/GldDatasetValidator.h', 'pgl::gld'),
               (ROOT/f'firmware/gld/models/model_{model}/ModelMetadata.h', 'pgl::gld::model'),
               (ROOT/'firmware/shared/include/FirmwareVersion.h', 'pgl::firmware'))
    for original, ns in headers:
        value = original.read_text(encoding='utf-8')
        opening = 'namespace ' + ns + ' {'
        closing = '}  // namespace ' + ns
        if value.count(opening) != 1 or value.count(closing) != 1: raise ValueError('unexpected namespace')
        value = value.replace(opening, ' '.join('namespace '+part+' {' for part in ns.split('::')))
        value = value.replace(closing, '}' * len(ns.split('::')))
        (Path(directory)/original.name).write_text(value,encoding='utf-8')
    command = [str(COMPILER), '-std=c++1z', '-I'+str(directory), '-static', '-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1',
               '-I'+str(ROOT/'firmware/lib/ArduinoJson/src'), '-I'+str(ROOT/'firmware/gld/include'),
               '-I'+str(ROOT/f'firmware/gld/models/model_{model}'), '-I'+str(ROOT/'firmware/shared/include'), str(cpp), '-o', str(exe)]
    env = dict(os.environ); env['PATH'] = str(COMPILER.parent) + os.pathsep + env.get('PATH', '')
    subprocess.run(command, check=True, env=env, timeout=60)
    return exe, env


class SerializedHelloWorkflow(unittest.TestCase):
    def test_production_hello_serializes_both_radio_states(self):
        if not COMPILER.is_file(): self.skipTest('host compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='atex-radio-host-') as temporary:
            exe, env = build_serializer(1, temporary)
            data = fixture.Device(fixture.Clock()).hello()
            for value in (False, True):
                data['radio_auto_tx'] = value
                result = subprocess.run([str(exe)], input=json.dumps(data), text=True,
                                        capture_output=True, check=True, env=env, timeout=5)
                self.assertIs(json.loads(result.stdout)['radio_auto_tx'], value)

    def test_maximum_length_status_fits_json_capacity(self):
        if not COMPILER.is_file(): self.skipTest('host compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='atex-status-host-') as temporary:
            exe, env = build_serializer(1, temporary, status=True)
            data = fixture.Device(fixture.Clock()).hello()
            for name in ('device_id', 'boot_id', 'session_id', 'label', 'reason'):
                data[name] = 'x' * 120  # copy helper truncates at actual firmware buffer length
            data['radio_auto_tx'] = True
            result = subprocess.run([str(exe)], input=json.dumps(data), text=True,
                                    capture_output=True, check=True, env=env, timeout=5)
            self.assertIs(json.loads(result.stdout)['radio_auto_tx'], True)

    def test_candidate_hello_connect_record_stop_and_radio_fault(self):
        if not COMPILER.is_file(): self.skipTest('host compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='atex-hello-host-') as temporary:
            for model in (1, 2, 3):
                with self.subTest(model=model):
                    exe, env = build_serializer(model, temporary)
                    for scenario in ("stop", "radio_fault", "wrong_id"):
                        with self.subTest(scenario=scenario):
                            harness = fixture.WorkflowTests('test_export_matches_verified_csv_bytes_including_line_endings')
                            harness.setUp()
                            try:
                                device = fixture.Device(harness.clock)
                                original_hello = device.hello
                                def serialized_hello():
                                    data = original_hello()
                                    output = subprocess.run([str(exe)], input=json.dumps(data), text=True, capture_output=True, check=True, env=env, timeout=5)
                                    return json.loads(output.stdout)
                                device.hello = serialized_hello
                                harness.device = device
                                harness.service._factory = device.factory
                                if scenario == "wrong_id":
                                    device.device_id = '1003'
                                    harness.service.scan(); harness.service.select('1002')
                                    with self.assertRaises(RuntimeError):
                                        harness.service.connect('1002', fixture.PASSWORD)
                                    self.assertFalse(any(command['cmd'] == 'START_DATASET' for command in device.commands))
                                    continue
                                harness.begin(prediction=False)
                                state = harness.service.snapshot()
                                self.assertTrue(state['connected'])
                                self.assertEqual(state['device_id'], '1002')
                                expected = re.search(r'PROFILE_ID\s*=\s*"([^"]+)"', (ROOT/f'firmware/gld/models/model_{model}/ModelMetadata.h').read_text()).group(1)
                                self.assertEqual(harness.service._engine.model['profile_id'], expected)
                                if scenario == "stop":
                                    harness.capture(2)
                                    stopped = harness.service.stop()
                                    self.assertTrue(stopped['verification']['verified'])
                                    self.assertEqual(len(harness.rows()), 2)
                                else:
                                    device.acquire(4)
                                    device.transition_fault = "ack_lost"
                                    harness.service.pause()
                                    device.terminal("radio_fault")
                                    harness.recover()
                                    state = harness.service.snapshot()
                                    self.assertEqual(state['state'], 'incomplete')
                                    self.assertEqual(state['cause']['code'], 'radio_fault')
                                    self.assertTrue(state['verification']['verified'])
                                    self.assertEqual(state['device_final_total'], dict(status='reconciled', count=4))
                            finally:
                                harness.tearDown()


if __name__ == '__main__': unittest.main()

