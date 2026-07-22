#pragma once

namespace pgl::firmware {

constexpr const char* GLD_FIRMWARE_NAME = "PertaminaGLD-GLD";
constexpr const char* CH_FIRMWARE_NAME = "PertaminaGLD-CH";
constexpr const char* GATEWAY_FIRMWARE_NAME = "PertaminaGLD-Gateway";

constexpr const char* GLD_FIRMWARE_VERSION = "0.8.14";
constexpr const char* CH_FIRMWARE_VERSION = "0.7.3";
constexpr const char* GATEWAY_FIRMWARE_VERSION = "0.1.5";

constexpr const char* PROTOCOL_VERSION = "0.2.0";
constexpr const char* CONFIG_SCHEMA_VERSION = "0.1.0";

// BUILD_DATE_TIME and GIT_COMMIT are injected by the final build system.
constexpr const char* BUILD_DATE_TIME_UNSET = "1970-01-01 00:00:00 Asia/Jakarta";
constexpr const char* GIT_COMMIT_UNSET = "unknown";

}  // namespace pgl::firmware
