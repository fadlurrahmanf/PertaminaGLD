#pragma once

#include <cstdint>

namespace pgl::gld::model {
constexpr const char* PROFILE_ID = "cnn-dualbranch-board-2-2class-v2";
constexpr const char* SCALER_PROFILE_ID = "cnn-dualbranch-board-2-2class-v2";
// BOARD GLD1 Model 2.zip was aligned on 2026-10-01. On 2026-11-03 the
// operator reported completed board/gas validation and explicitly approved
// activation. This records operator evidence, not agent-performed gas tests.
// Valid applied nulling and an explicit matching model binding remain required.
constexpr bool PRODUCTION_APPROVED = true;
constexpr int EXPECTED_ADC_INPUT_ELEMENTS = 8;
constexpr int EXPECTED_EVIDENCE_INPUT_ELEMENTS = 7;
constexpr int EXPECTED_OUTPUT_ELEMENTS = 2;
// BOARD GLD 2.zip: Clean_Air -> CLEAR, LPG -> LPG.
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {0, 1};
}  // namespace pgl::gld::model
