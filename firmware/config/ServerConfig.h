#pragma once

#include <cstdint>

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

// SSID WiFi untuk jalur Server Dataset. Dipakai GLD saat mode dataset/nulling
// perlu publish langsung ke broker dataset.
#define PGL_SERVER_DATASET_WIFI_SSID       "CHANGE_ME"

// Password WiFi untuk jalur Server Dataset. Untuk produksi, pindahkan ke
// provisioning/NVS atau file lokal ignored, bukan commit permanen.
#define PGL_SERVER_DATASET_WIFI_PASSWORD   "CHANGE_ME"

// Host/IP broker MQTT Server Dataset. Dipakai GLD direct MQTT untuk dataset,
// status, summary, command ack, dan hasil nulling.
#define PGL_SERVER_DATASET_MQTT_HOST       "10.217.88.180"

// Port broker MQTT Server Dataset. Bench saat ini memakai 1884.
#define PGL_SERVER_DATASET_MQTT_PORT       1884

// Username MQTT Server Dataset. Kosongkan atau pindah ke provisioning jika broker
// produksi memakai auth berbeda.
#define PGL_SERVER_DATASET_MQTT_USER       ""

// Password MQTT Server Dataset. Jangan commit credential produksi permanen.
#define PGL_SERVER_DATASET_MQTT_PASS       ""

// Root topic untuk GLD direct MQTT. Device ID GLD ditambahkan oleh GldConfig.h.
#define PGL_SERVER_DATASET_TOPIC_ROOT      "gas-leak-detector"

// SSID WiFi untuk jalur Server Site. Dipakai Gateway MQTT bridge ke dashboard/site.
// Jangan commit SSID/password produksi; override lewat -D build flag atau file
// lokal ignored di luar repo ini.
#define PGL_SERVER_SITE_WIFI_SSID          "CHANGE_ME"

// Password WiFi untuk jalur Server Site. Untuk produksi, pindahkan ke provisioning
// atau file lokal ignored.
#define PGL_SERVER_SITE_WIFI_PASSWORD      "CHANGE_ME"

// Host/IP broker MQTT Server Site. Dipakai Gateway untuk publish frame MESH dan
// menerima command dari server/site.
#define PGL_SERVER_SITE_MQTT_HOST          "10.158.198.180"

// Port broker MQTT Server Site. Bench saat ini memakai 1884.
#define PGL_SERVER_SITE_MQTT_PORT          1884

// Username MQTT Server Site. Sesuaikan dengan broker site.
// Jangan commit credential produksi permanen; override lewat -D build flag
// atau file lokal ignored di luar repo ini.
#define PGL_SERVER_SITE_MQTT_USER          "CHANGE_ME"

// Password MQTT Server Site. Jangan commit credential produksi permanen.
#define PGL_SERVER_SITE_MQTT_PASS          "CHANGE_ME"

// Root topic Gateway untuk jalur site. Subtopic command/status/uplink diturunkan
// oleh GwConfig.h.
#define PGL_SERVER_SITE_TOPIC_ROOT         "gld/gateway"

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------

namespace pgl::config::server {

namespace dataset {
constexpr const char* WIFI_SSID = PGL_SERVER_DATASET_WIFI_SSID;
constexpr const char* WIFI_PASSWORD = PGL_SERVER_DATASET_WIFI_PASSWORD;
constexpr const char* MQTT_HOST = PGL_SERVER_DATASET_MQTT_HOST;
constexpr uint16_t MQTT_PORT = PGL_SERVER_DATASET_MQTT_PORT;
constexpr const char* MQTT_USER = PGL_SERVER_DATASET_MQTT_USER;
constexpr const char* MQTT_PASSWORD = PGL_SERVER_DATASET_MQTT_PASS;
constexpr const char* TOPIC_ROOT = PGL_SERVER_DATASET_TOPIC_ROOT;
}  // namespace dataset

namespace site {
constexpr const char* WIFI_SSID = PGL_SERVER_SITE_WIFI_SSID;
constexpr const char* WIFI_PASSWORD = PGL_SERVER_SITE_WIFI_PASSWORD;
constexpr const char* MQTT_HOST = PGL_SERVER_SITE_MQTT_HOST;
constexpr uint16_t MQTT_PORT = PGL_SERVER_SITE_MQTT_PORT;
constexpr const char* MQTT_USER = PGL_SERVER_SITE_MQTT_USER;
constexpr const char* MQTT_PASSWORD = PGL_SERVER_SITE_MQTT_PASS;
constexpr const char* TOPIC_ROOT = PGL_SERVER_SITE_TOPIC_ROOT;
}  // namespace site

}  // namespace pgl::config::server
