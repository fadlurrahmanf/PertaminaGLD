#pragma once

#include <cstdint>

#include "LoraMeshConfig.h"
#include "ServerConfig.h"

namespace pgl::config::gw {

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

// ID Gateway lokal sebagai root MESH dan identity saat publish MQTT.
// Harus cocok dengan ROOT_GATEWAY_ID pada CH yang menuju Gateway ini.
constexpr uint16_t GATEWAY_ID = 0x006F;

// Jeda retry koneksi WiFi Gateway dalam ms. Dipakai saat koneksi site putus agar
// firmware tidak reconnect terlalu agresif.
constexpr uint32_t WIFI_RETRY_MS = 5000;

// Jeda retry koneksi MQTT Gateway dalam ms. Dipakai saat broker site belum siap
// atau koneksi MQTT terputus.
constexpr uint32_t MQTT_RETRY_MS = 3000;

// Interval publish status Gateway dalam ms. Status berisi gatewayId, WiFi/MQTT,
// meshReady, dan IP.
constexpr uint32_t STATUS_INTERVAL_MS = 10000;

// Jumlah pengiriman CH_CONFIG_RESPONSE untuk satu CH_CONFIG_REQUEST. Dua kali
// dipakai agar CH lebih besar peluangnya menerima balasan Gateway saat beberapa
// CH lain ikut merespons discovery pada window yang sama.
constexpr uint8_t CONFIG_RESPONSE_REPEAT_COUNT = 2;

// Jeda antar pengiriman ulang CH_CONFIG_RESPONSE Gateway dalam ms.
constexpr uint16_t CONFIG_RESPONSE_REPEAT_GAP_MS = 70;

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------

// Server Site WiFi/MQTT
constexpr const char* WIFI_SSID = pgl::config::server::site::WIFI_SSID;
constexpr const char* WIFI_PASSWORD = pgl::config::server::site::WIFI_PASSWORD;
constexpr const char* MQTT_HOST = pgl::config::server::site::MQTT_HOST;
constexpr uint16_t MQTT_PORT = pgl::config::server::site::MQTT_PORT;
constexpr const char* MQTT_USER = pgl::config::server::site::MQTT_USER;
constexpr const char* MQTT_PASSWORD = pgl::config::server::site::MQTT_PASSWORD;

// Server Site topics
constexpr const char* TOPIC_UPLINK = PGL_SERVER_SITE_TOPIC_ROOT "/uplink";
constexpr const char* TOPIC_STATUS = PGL_SERVER_SITE_TOPIC_ROOT "/status";
constexpr const char* TOPIC_TOPOLOGY = PGL_SERVER_SITE_TOPIC_ROOT "/topology";
constexpr const char* TOPIC_COMMANDS = PGL_SERVER_SITE_TOPIC_ROOT "/cmd/#";
constexpr const char* TOPIC_PULL = PGL_SERVER_SITE_TOPIC_ROOT "/cmd/pull";
constexpr const char* TOPIC_NODE_COMMAND = PGL_SERVER_SITE_TOPIC_ROOT "/cmd/node";

// LoRa MESH (CH <-> Gateway / CH <-> CH)
constexpr float MESH_FREQ_MHZ = pgl::config::lora::mesh::FREQ_MHZ;
constexpr float MESH_BW_KHZ = pgl::config::lora::mesh::BW_KHZ;
constexpr uint8_t MESH_SF = pgl::config::lora::mesh::SF;
constexpr uint8_t MESH_CR = pgl::config::lora::mesh::CR;
constexpr uint8_t MESH_SYNC_WORD = pgl::config::lora::mesh::SYNC_WORD;
constexpr int8_t MESH_TX_POWER_DBM = pgl::config::lora::mesh::TX_POWER_DBM;
constexpr uint16_t MESH_PREAMBLE = pgl::config::lora::mesh::PREAMBLE;
constexpr float MESH_TCXO_VOLTAGE = pgl::config::lora::mesh::TCXO_VOLTAGE;
constexpr float MESH_XTAL_TCXO_VOLTAGE = pgl::config::lora::mesh::XTAL_TCXO_VOLTAGE;
constexpr uint32_t MESH_SPI_HZ = pgl::config::lora::mesh::SPI_HZ;

}  // namespace pgl::config::gw
