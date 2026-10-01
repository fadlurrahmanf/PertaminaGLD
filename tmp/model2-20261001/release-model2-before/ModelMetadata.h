#pragma once

#include <cstdint>

namespace pgl::gld::model {
constexpr const char* PROFILE_ID = "cnn-dualbranch-board-2-v1";
constexpr const char* SCALER_PROFILE_ID = "cnn-dualbranch-board-2-v1";
constexpr bool PRODUCTION_APPROVED = true;
constexpr int EXPECTED_ADC_INPUT_ELEMENTS = 8;
constexpr int EXPECTED_EVIDENCE_INPUT_ELEMENTS = 7;
constexpr int EXPECTED_OUTPUT_ELEMENTS = 4;
// Board 2 class order: CO2, Clean_Air, H2, LPG.
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {6, 0, 7, 1};
}  // namespace pgl::gld::model
