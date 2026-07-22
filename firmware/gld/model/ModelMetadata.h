#pragma once

#include <cstdint>

namespace pgl::gld::model {

// This repository still carries the historical ApplyGasleak placeholder model.
// It has no traceable Pertamina training artifact or nulling-profile binding,
// so production inference must fail closed until these values are replaced
// together with model_data.cpp and scaler_params.cpp.
constexpr const char* PROFILE_ID = "applygasleak-placeholder-unbound";
constexpr const char* SCALER_PROFILE_ID = "applygasleak-placeholder-unbound";
constexpr uint8_t BOUND_NULLING_PROFILE_ID = 0;
constexpr bool PRODUCTION_APPROVED = false;

constexpr int EXPECTED_INPUT_ELEMENTS = 8;
#if defined(PGL_GLD_FIELDTEST_4CLASS)
// Legacy ApplyGasleak artifact has four float outputs.  This contract is
// accepted only by env:gldFieldtest; its non-clear labels are not traceable
// to the GLD gas taxonomy and must never actuate or transmit an alarm.
constexpr int EXPECTED_OUTPUT_ELEMENTS = 4;
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {
    0,  // clear (only class with a known safe semantic)
    6,  // unverified -> GLD_GAS_ANOMALY
    6,  // unverified -> GLD_GAS_ANOMALY
    6,  // unverified -> GLD_GAS_ANOMALY
};
#else
constexpr int EXPECTED_OUTPUT_ELEMENTS = 5;

// TFLite output index -> compact GLD gas-class value. Keeping this beside the
// artifact makes the mapping explicit instead of silently hard-coding it in
// the runtime.
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {
    0,  // clear
    1,  // LPG
    2,  // methane
    3,  // propane
    4,  // butane
};
#endif

}  // namespace pgl::gld::model
