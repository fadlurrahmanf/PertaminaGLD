#pragma once

#include <cstddef>
#include <cstdint>

namespace pgl::protocol {

constexpr uint8_t APPFRAME_MAGIC = 0xAA;
constexpr size_t APPFRAME_HEADER_SIZE = 8;
constexpr size_t APPFRAME_CRC_SIZE = 2;
constexpr size_t APPFRAME_OVERHEAD = APPFRAME_HEADER_SIZE + APPFRAME_CRC_SIZE;

constexpr size_t STAR_MAX_PAYLOAD = 64;
constexpr size_t MESH_MAX_PAYLOAD = 80;

constexpr uint8_t MSG_TYPE_MASK = 0x3F;
constexpr uint8_t FLAG_ALARM_ACK = 0x40;
constexpr uint8_t FLAG_GLD_EXT_POWER = 0x80;

constexpr uint8_t MSG_SENSOR_DATA = 0x10;
constexpr uint8_t MSG_NODE_DOWNLINK = 0x14;
constexpr uint8_t MSG_SERVER_PULL_REQUEST = 0x30;
constexpr uint8_t MSG_CLUSTER_DATA_RESPONSE = 0x31;
constexpr uint8_t MSG_SERVER_NODE_COMMAND = 0x32;
constexpr uint8_t MSG_CH_HELLO = 0x33;
constexpr uint8_t MSG_CH_CONFIG_REQUEST = 0x34;
constexpr uint8_t MSG_CH_CONFIG_RESPONSE = 0x35;

constexpr uint8_t TYPE_GLD_NORMAL_BATTERY = MSG_SENSOR_DATA;
constexpr uint8_t TYPE_GLD_NORMAL_EXTERNAL = MSG_SENSOR_DATA | FLAG_GLD_EXT_POWER;
constexpr uint8_t TYPE_GLD_ALARM_BATTERY = MSG_SENSOR_DATA | FLAG_ALARM_ACK;
constexpr uint8_t TYPE_GLD_ALARM_EXTERNAL = MSG_SENSOR_DATA | FLAG_ALARM_ACK | FLAG_GLD_EXT_POWER;
constexpr uint8_t TYPE_ALARM_ACK_COMPACT = MSG_SENSOR_DATA | FLAG_ALARM_ACK;

constexpr uint8_t GLD_GAS_CLEAR = 0;
constexpr uint8_t GLD_GAS_LPG = 1;
constexpr uint8_t GLD_GAS_PROPANE = 2;
constexpr uint8_t GLD_GAS_BUTANE = 3;
constexpr uint8_t GLD_GAS_METHANE = 4;
constexpr uint8_t GLD_GAS_RESERVED = 5;
constexpr uint8_t GLD_GAS_ANOMALY = 6;

constexpr uint8_t GLD_LEL_THRESHOLD_PERCENT = 30;
constexpr uint16_t GLD_BATTERY_MV_INVALID = 0xFFFF;

constexpr size_t GLD_PLAINTEXT_PAYLOAD_SIZE = 4;
constexpr size_t GLD_KEY_ID_SIZE = 1;
constexpr size_t GLD_AES_GCM_NONCE_SIZE = 12;
constexpr size_t GLD_AES_GCM_CIPHERTEXT_SIZE = GLD_PLAINTEXT_PAYLOAD_SIZE;
constexpr size_t GLD_AES_GCM_TAG_SIZE = 12;
constexpr size_t GLD_ENCRYPTED_PAYLOAD_SIZE =
    GLD_KEY_ID_SIZE + GLD_AES_GCM_NONCE_SIZE + GLD_AES_GCM_CIPHERTEXT_SIZE + GLD_AES_GCM_TAG_SIZE;

constexpr size_t GLD_AAD_SIZE = 5;

constexpr uint8_t NC_FLAG_ALARM = 0x01;
constexpr uint8_t NC_FLAG_EXT_POWER = 0x10;

constexpr size_t GLD_RECORD_HEADER_SIZE = 5;
constexpr size_t GLD_RECORD_PHASE1_SIZE = GLD_RECORD_HEADER_SIZE + GLD_ENCRYPTED_PAYLOAD_SIZE;

constexpr size_t CLUSTER_DATA_RESPONSE_HEADER_SIZE = 6;

constexpr uint8_t messageType(uint8_t typeFlags) {
    return typeFlags & MSG_TYPE_MASK;
}

constexpr bool hasAlarmAckFlag(uint8_t typeFlags) {
    return (typeFlags & FLAG_ALARM_ACK) != 0;
}

constexpr bool hasGldExternalPowerFlag(uint8_t typeFlags) {
    return (typeFlags & FLAG_GLD_EXT_POWER) != 0;
}

constexpr uint8_t makeGldSensorTypeFlags(bool alarm, bool externalPower) {
    return MSG_SENSOR_DATA |
           (alarm ? FLAG_ALARM_ACK : 0) |
           (externalPower ? FLAG_GLD_EXT_POWER : 0);
}

}  // namespace pgl::protocol
