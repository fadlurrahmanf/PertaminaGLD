#pragma once

// GLD1 baseline 69a493c, with the current GPIO41/J2 alarm contract only.
// Nulling (5 ms, no 30-second warm-up), ADC, DAC and Model 1 stay original.
namespace pgl::firmware {
constexpr const char* GLD1_FIRMWARE_VERSION = "0.8.38";
}
