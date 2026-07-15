#pragma once

#include "LoraStarConfig.h"
#include "ServerConfig.h"

// =============================================================================
// GLD Firmware Configuration
// Edit bagian "Editable parameters" saja untuk deploy normal.
// Bagian "Derived / aliases" mengikuti nilai dari parameter di atas atau file
// config domain lain.
// =============================================================================

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

// Node ID GLD dalam format hex tanpa prefix 0x. Nilai ini menjadi sumber tunggal
// untuk GLD_NODE_ID numerik, device ID string, MQTT client ID, dan topic per GLD.
#ifndef GLD_NODE_HEX
#define GLD_NODE_HEX        F010
#endif

// Cluster Head target untuk uplink LoRa STAR dari GLD ini. Harus sama dengan
// CH_ID pada ChConfig.h untuk CH yang menjadi pasangan GLD.
#ifndef GLD_CH_ID
#define GLD_CH_ID           0x006B
#endif

// Interval scan sensor/inference dalam ms. Angka 500 ms adalah titik aman dari
// hasil bench COM9: cukup di atas sweep ADS 8-sensor ~330 ms, tanpa membebani
// pipeline seperti interval sub-350 ms.
#define GLD_SCAN_INTERVAL_MS      500

// Batas bawah interval dataset. Command MQTT yang meminta interval lebih kecil
// tetap dinaikkan ke nilai ini supaya pembacaan ADS 8-sensor tidak overlap.
#define GLD_DATASET_MIN_SAMPLE_INTERVAL_MS 500

// Interval transmit LoRa STAR untuk payload running/inference dalam ms.
// Makin kecil berarti data lebih sering dikirim, tetapi airtime dan baterai naik.
#define GLD_TX_INTERVAL_MS      10000

// Timeout koneksi WiFi GLD dalam ms untuk jalur dataset/nulling MQTT.
// Jika lewat dari nilai ini, firmware menganggap koneksi WiFi gagal.
#define GLD_WIFI_TIMEOUT_MS     15000

// Jeda retry koneksi MQTT GLD dalam ms. Dipakai agar firmware tidak reconnect
// terlalu agresif saat broker/server tidak tersedia.
#define GLD_MQTT_RETRY_MS        3000

// Interval publish status GLD dalam ms untuk mode yang memakai MQTT.
// Jangan terlalu kecil agar broker dan log tidak penuh.
#define GLD_STATUS_INTERVAL_MS  10000

// Lama RX window LoRa GLD dalam ms setelah GLD mengirim SENSOR_DATA.
// Downlink battery-mode dari CH harus masuk dalam window ini.
#define GLD_LORA_RX_WINDOW_MS    2000

// Ukuran buffer MQTT PubSubClient GLD dalam byte. Harus cukup untuk command
// dataset/nulling dan payload JSON yang dipublish.
#define GLD_MQTT_BUFFER_SIZE     1024

// Default produksi: GLD tidak boleh memakai AES self-test key secara diam-diam.
// Untuk bench/selftest runtime sementara, build eksplisit dengan
// -DGLD_ALLOW_SELFTEST_AES_FALLBACK=1.
#ifndef GLD_ALLOW_SELFTEST_AES_FALLBACK
#define GLD_ALLOW_SELFTEST_AES_FALLBACK 0
#endif

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------

#define PGL_CONFIG_STRINGIFY_IMPL(value) #value
#define PGL_CONFIG_STRINGIFY(value) PGL_CONFIG_STRINGIFY_IMPL(value)
#define PGL_CONFIG_HEX16_IMPL(value) 0x##value
#define PGL_CONFIG_HEX16(value) PGL_CONFIG_HEX16_IMPL(value)

#define GLD_NODE_ID         PGL_CONFIG_HEX16(GLD_NODE_HEX)
#define GLD_DEVICE_ID_STR   PGL_CONFIG_STRINGIFY(GLD_NODE_HEX)
#define GLD_MQTT_CLIENT_ID  "gld-unified-" GLD_DEVICE_ID_STR

// Server Dataset WiFi/MQTT
#define GLD_WIFI_SSID       PGL_SERVER_DATASET_WIFI_SSID
#define GLD_WIFI_PASSWORD   PGL_SERVER_DATASET_WIFI_PASSWORD
#define GLD_MQTT_HOST       PGL_SERVER_DATASET_MQTT_HOST
#define GLD_MQTT_PORT       PGL_SERVER_DATASET_MQTT_PORT
#define GLD_MQTT_USER       PGL_SERVER_DATASET_MQTT_USER
#define GLD_MQTT_PASS       PGL_SERVER_DATASET_MQTT_PASS

// Server Dataset topics
#define GLD_TOPIC_CMD           PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/cmd"
#define GLD_TOPIC_DATASET       PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/dataset"
#define GLD_TOPIC_DATA          PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/dataset/data"
#define GLD_TOPIC_STATUS        PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/dataset/status"
#define GLD_TOPIC_SUMMARY       PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/dataset/summary"
#define GLD_TOPIC_ACK           PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/cmd/ack"
#define GLD_TOPIC_NULLING       PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/nulling/result"
#define GLD_TOPIC_NULL_STATUS   PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/nulling/status"

// LoRa STAR (GLD <-> CH)
#define GLD_STAR_FREQ_MHZ       pgl::config::lora::star::FREQ_MHZ
#define GLD_STAR_BW_KHZ         pgl::config::lora::star::BW_KHZ
#define GLD_STAR_SF             pgl::config::lora::star::SF
#define GLD_STAR_CR             pgl::config::lora::star::CR
#define GLD_STAR_SYNC_WORD      pgl::config::lora::star::SYNC_WORD
#define GLD_STAR_TX_POWER_DBM   pgl::config::lora::star::TX_POWER_DBM
#define GLD_STAR_PREAMBLE       pgl::config::lora::star::PREAMBLE
#define GLD_STAR_TCXO_VOLTAGE   pgl::config::lora::star::TCXO_VOLTAGE
#define GLD_STAR_XTAL_VOLTAGE   pgl::config::lora::star::XTAL_TCXO_VOLTAGE
