"""Host/source release gates. No firmware compiler, device or NVS operation."""
from __future__ import annotations

import configparser
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


def body(source: str, signature: str) -> str:
    start = source.index('{', source.index(signature))
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ThreeModelSyncPolicy(unittest.TestCase):
    def test_model_two_approval_has_explicit_operator_provenance(self):
        metadata = json.loads((ROOT / 'firmware/gld/models/model_2/model.json').read_text(encoding='utf-8'))
        approval = metadata['productionApproval']
        self.assertEqual(approval['status'], 'approved')
        self.assertEqual(approval['date'], '2026-11-03')
        self.assertEqual(approval['operatorStatement'], 'Sudah divalidasi; setuju aktifkan')
        self.assertIn('operator-reported', approval['validationEvidence'])
        self.assertIs(approval['agentPerformedGasValidation'], False)

    def test_activation_does_not_replace_model_two_weights_scaler_or_sensor_table(self):
        directory = ROOT / 'firmware/gld/models/model_2'
        protected = {
            'cnn_gas_datasheet_model_data.h': '08b1ca9c19d5e0203a3431d67ed137b5f898a23a37432f1d46e2d31955191b7b',
            'cnn_gas_datasheet_normalize_params.h': '9c1e401c2861d940d921e1e083ecd5fe07fd0610b31b890afe3df3cac58fba97',
            'cnn_gas_sensitivity_table.h': '6f8bf32caaff031cf422b42db4889b34a2a9d211977fd47e1ee6eb48f134cefd',
        }
        for filename, checksum in protected.items():
            with self.subTest(filename=filename):
                self.assertEqual(hashlib.sha256((directory / filename).read_bytes()).hexdigest(), checksum)
        header = (directory / 'ModelMetadata.h').read_text(encoding='utf-8')
        for key in ('PROFILE_ID', 'SCALER_PROFILE_ID'):
            self.assertRegex(header, rf'{key}\s*=\s*"cnn-dualbranch-board-2-2class-v2"')
        self.assertRegex(header, r'CLASS_MAP\[EXPECTED_OUTPUT_ELEMENTS\]\s*=\s*\{0, 1\}')

    def test_all_three_use_approved_metadata_and_the_same_inference_engine_and_workflow(self):
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read(ROOT / 'firmware/platformio.ini', encoding='utf-8')
        reference = ROOT / 'firmware/gld/models/model_1'
        for model in (1, 2, 3):
            with self.subTest(model=model):
                directory = ROOT / f'firmware/gld/models/model_{model}'
                header = (directory / 'ModelMetadata.h').read_text(encoding='utf-8')
                self.assertRegex(header, r'PRODUCTION_APPROVED\s*=\s*true\s*;')
                for filename in ('NeuralNetwork.cpp', 'NeuralNetwork.h'):
                    self.assertEqual((directory / filename).read_bytes(), (reference / filename).read_bytes())
                workflow = config[f'env:gld_model_{model}_dataset_workflow_wifi']
                self.assertEqual(workflow['extends'], f'env:gld_model_{model}_dataset_wifi')
                self.assertIn('-DPGL_GLD_DATASET_WORKFLOW=1', workflow['build_flags'])
                self.assertIn('+<gld/src/GldDatasetWorkflowWifi.cpp>', workflow['build_src_filter'])

    def test_shared_explicit_binding_and_production_readiness_gates_remain(self):
        source = (ROOT / 'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf-8')
        bind = body(source, 'void onBindModelToActiveNullingProfile() {')
        for gate in ('!pgl::gld::model::PRODUCTION_APPROVED',
                     'currentMode != pgl::gld::GldMode::INFERENCE',
                     'nullingRetryArmed || !nullingProfileApplied || nullingProfileId == 0',
                     'profile.profileId != nullingProfileId'):
            self.assertIn(gate, bind)
            self.assertLess(bind.index(gate), bind.index('saveModelBinding(updated)'))
        # Only the command declaration and ordinary dispatch may invoke binding;
        # approval must never introduce startup, Wi-Fi or scan auto-binding.
        self.assertEqual(len(re.findall(r'\bonBindModelToActiveNullingProfile\s*\(', source)), 2)
        for forbidden in ('dac.', 'runNulling', 'writeGldMode', 'ESP.restart', 'updateAlarmOutputs'):
            self.assertNotIn(forbidden, bind)
        ready = body(source, 'bool modelProfileMatchesActiveNulling() {')
        for gate in ('pgl::gld::model::PRODUCTION_APPROVED', 'isModelBindingValid(modelBinding)',
                     'modelBinding.modelFingerprint == compiledFingerprint',
                     'modelBinding.nullingProfileId == nullingProfileId'):
            self.assertIn(gate, ready)
        workflow = body(source, 'bool datasetWorkflowPredictionReady() {')
        for gate in ('PRODUCTION_APPROVED', 'isModelBindingValid(modelBinding)',
                     'modelBinding.modelFingerprint == fingerprint',
                     'modelBinding.nullingProfileId == nullingProfileId', 'runtimeDacVerificationReady()'):
            self.assertIn(gate, workflow)


if __name__ == '__main__':
    unittest.main()
