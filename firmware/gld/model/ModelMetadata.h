#pragma once

#include <cstdint>

namespace pgl::gld::model {

// CNN dual-branch + datasheet-evidence gas model (cnn_gas_datasheet.zip,
// INT8 TFLite Micro). User explicitly approved production use on 2026-07-24
// (COM3 board, deviceId 1001) after the fail-closed default (always
// reporting CO2/ANOMALY, confidence 0) was diagnosed as the intended
// behavior while this stayed false. BOUND_NULLING_PROFILE_ID=1 matches the
// profileId the *next* nulling calibration run produces on that board: its
// NVS was wiped by a Reset-NVS firmware upload earlier in this session, so
// GldUnifiedMain.cpp's save-profile path (no prior valid profile in NVS)
// assigns profileId=1. If nulling is instead run on a board whose NVS was
// never reset (existing profileId > 0), the saved profileId increments from
// that value instead and this bound ID must be updated to match — check
// GET_STATUS's model.activeNullingProfileId after nulling completes.
constexpr const char* PROFILE_ID = "cnn-dualbranch-datasheet-v1-unbound";
constexpr const char* SCALER_PROFILE_ID = "cnn-dualbranch-datasheet-v1-unbound";
constexpr bool PRODUCTION_APPROVED = true;

// Model is dual-input: Branch A (Conv1D) takes the 8 raw ADC channels,
// Branch B (Dense) takes 7 "evidence" features derived from the ADC via
// cnn_gas_sensitivity_table.h. See NeuralNetwork::predict().
constexpr int EXPECTED_ADC_INPUT_ELEMENTS = 8;
constexpr int EXPECTED_EVIDENCE_INPUT_ELEMENTS = 7;

#if defined(PGL_GLD_FIELDTEST_4CLASS)
// Legacy ApplyGasleak 4-class contract. The CNN dual-branch model has 3
// outputs, so this mismatch is intentional: env:gldFieldtest's contract
// check will fail closed (mlReady=false) rather than silently reinterpret
// CNN output indices as the old 4-class taxonomy.
constexpr int EXPECTED_OUTPUT_ELEMENTS = 4;
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {
    0,  // clear (only class with a known safe semantic)
    6,  // unverified -> GLD_GAS_ANOMALY
    6,  // unverified -> GLD_GAS_ANOMALY
    6,  // unverified -> GLD_GAS_ANOMALY
};
#else
constexpr int EXPECTED_OUTPUT_ELEMENTS = 3;

// CNN_GAS_CLASS_NAMES order (cnn_gas_datasheet_normalize_params.h): CO2,
// Clean_Air, LPG. This model cannot distinguish methane/propane/butane, so
// CO2 -> GLD_GAS_ANOMALY (no dedicated GLD gas-class slot exists for CO2).
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {
    6,  // CO2 -> GLD_GAS_ANOMALY
    0,  // Clean_Air -> GLD_GAS_CLEAR
    1,  // LPG -> GLD_GAS_LPG
};
#endif

}  // namespace pgl::gld::model
