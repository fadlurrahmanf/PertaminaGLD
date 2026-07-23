#pragma once

#include <cstdint>

namespace pgl::gld::model {

// CNN dual-branch + datasheet-evidence gas model (cnn_gas_datasheet.zip,
// INT8 TFLite Micro). It has no field validation against the Pertamina GLD
// taxonomy or nulling-profile binding yet, so production inference must fail
// closed until this is explicitly approved together with model_data.cpp,
// cnn_gas_datasheet_normalize_params.h, and cnn_gas_sensitivity_table.h.
constexpr const char* PROFILE_ID = "cnn-dualbranch-datasheet-v1-unbound";
constexpr const char* SCALER_PROFILE_ID = "cnn-dualbranch-datasheet-v1-unbound";
constexpr uint8_t BOUND_NULLING_PROFILE_ID = 0;
constexpr bool PRODUCTION_APPROVED = false;

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
