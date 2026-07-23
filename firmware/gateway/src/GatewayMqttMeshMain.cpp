#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "AppFrame.h"
#include "FirmwareConfig.h"
#include "FirmwareVersion.h"
#include "GwConfig.h"
#include "GatewayBoardPins.h"
#include "ProtocolConstants.h"
#include "ServerNodeCommandRoute.h"

namespace {

// WiFi/MQTT site credentials start from the compile-time ServerConfig.h
// defaults (loadDefaultNetConfig) but are overridden at boot by whatever was
// last saved to NVS via SET_WIFI_CONFIG_JSON (loadNetConfig) - the Operator
// can push new credentials without a reflash. GLD/CH have no equivalent; this
// is Gateway-only because its WiFi/MQTT were previously reflash-only.
struct RuntimeNetConfig {
    char wifiSsid[33];
    char wifiPassword[65];
    char mqttHost[65];
    uint16_t mqttPort;
    char mqttUser[33];
    char mqttPassword[65];
    bool mqttEnabled;
};

RuntimeNetConfig netConfig{};
Preferences netPrefs;
constexpr uint32_t NET_CONFIG_MAGIC = 0x47574E31; // "GWN1"
constexpr const char* NET_CONFIG_NAMESPACE = "gwnet";

void copyBounded(char* dest, size_t destSize, const char* src) {
    if (src == nullptr) {
        dest[0] = '\0';
        return;
    }
    strncpy(dest, src, destSize - 1);
    dest[destSize - 1] = '\0';
}

void loadDefaultNetConfig() {
    copyBounded(netConfig.wifiSsid, sizeof(netConfig.wifiSsid), pgl::config::gw::WIFI_SSID);
    copyBounded(netConfig.wifiPassword, sizeof(netConfig.wifiPassword), pgl::config::gw::WIFI_PASSWORD);
    copyBounded(netConfig.mqttHost, sizeof(netConfig.mqttHost), pgl::config::gw::MQTT_HOST);
    netConfig.mqttPort = pgl::config::gw::MQTT_PORT;
    copyBounded(netConfig.mqttUser, sizeof(netConfig.mqttUser), pgl::config::gw::MQTT_USER);
    copyBounded(netConfig.mqttPassword, sizeof(netConfig.mqttPassword), pgl::config::gw::MQTT_PASSWORD);
    netConfig.mqttEnabled = true;
}

void loadNetConfig() {
    loadDefaultNetConfig();
    netPrefs.begin(NET_CONFIG_NAMESPACE, true);
    const uint32_t magic = netPrefs.getUInt("magic", 0);
    if (magic == NET_CONFIG_MAGIC) {
        const String ssid = netPrefs.getString("ssid", "");
        const String pass = netPrefs.getString("pass", "");
        const String host = netPrefs.getString("host", "");
        const uint16_t port = netPrefs.getUShort("port", 0);
        const String user = netPrefs.getString("user", "");
        const String mqttPass = netPrefs.getString("mqttPass", "");
        if (ssid.length() > 0) {
            copyBounded(netConfig.wifiSsid, sizeof(netConfig.wifiSsid), ssid.c_str());
            copyBounded(netConfig.wifiPassword, sizeof(netConfig.wifiPassword), pass.c_str());
            copyBounded(netConfig.mqttHost, sizeof(netConfig.mqttHost), host.c_str());
            if (port > 0) {
                netConfig.mqttPort = port;
            }
            copyBounded(netConfig.mqttUser, sizeof(netConfig.mqttUser), user.c_str());
            copyBounded(netConfig.mqttPassword, sizeof(netConfig.mqttPassword), mqttPass.c_str());
            netConfig.mqttEnabled = netPrefs.getBool("mqttOn", true);
        }
    }
    netPrefs.end();
}

bool saveNetConfig() {
    if (!netPrefs.begin(NET_CONFIG_NAMESPACE, false)) {
        return false;
    }
    netPrefs.putUInt("magic", NET_CONFIG_MAGIC);
    netPrefs.putString("ssid", netConfig.wifiSsid);
    netPrefs.putString("pass", netConfig.wifiPassword);
    netPrefs.putString("host", netConfig.mqttHost);
    netPrefs.putUShort("port", netConfig.mqttPort);
    netPrefs.putString("user", netConfig.mqttUser);
    netPrefs.putString("mqttPass", netConfig.mqttPassword);
    netPrefs.putBool("mqttOn", netConfig.mqttEnabled);
    netPrefs.end();
    return true;
}

struct RuntimeMeshConfig {
    float freqMHz;
    float bwKHz;
    uint8_t sf;
    uint8_t cr;
    uint8_t syncWord;
    int8_t txPowerDbm;
};

constexpr uint32_t MESH_CONFIG_MAGIC = 0x47574D31; // "GWM1"
constexpr const char* MESH_CONFIG_NAMESPACE = "gwmesh";

bool isSupportedMeshBandwidth(float value) {
    constexpr float supported[] = {7.8f, 10.4f, 15.6f, 20.8f, 31.25f,
                                   41.7f, 62.5f, 125.0f, 250.0f, 500.0f};
    for (const float candidate : supported) {
        const float delta = value > candidate ? value - candidate : candidate - value;
        if (delta < 0.02f) return true;
    }
    return false;
}

bool isValidMeshConfig(const RuntimeMeshConfig& cfg) {
    return cfg.freqMHz >= 900.0f && cfg.freqMHz <= 930.0f &&
           isSupportedMeshBandwidth(cfg.bwKHz) &&
           cfg.sf >= 5 && cfg.sf <= 12 &&
           cfg.cr >= 5 && cfg.cr <= 8 &&
           cfg.txPowerDbm >= -9 && cfg.txPowerDbm <= 22;
}

constexpr uint16_t DEFAULT_GATEWAY_ID = pgl::config::gw::GATEWAY_ID;
constexpr uint32_t GATEWAY_ID_CONFIG_MAGIC = 0x47574931; // "GWI1"
constexpr const char* GATEWAY_ID_CONFIG_NAMESPACE = "gw-cfg";
uint16_t gatewayId = DEFAULT_GATEWAY_ID;
bool gatewayIdentityLoadedFromNvs = false;

constexpr const char* TOPIC_UPLINK = pgl::config::gw::TOPIC_UPLINK;
constexpr const char* TOPIC_STATUS = pgl::config::gw::TOPIC_STATUS;
constexpr const char* TOPIC_TOPOLOGY = pgl::config::gw::TOPIC_TOPOLOGY;
constexpr const char* TOPIC_COMMANDS = pgl::config::gw::TOPIC_COMMANDS;
constexpr const char* TOPIC_PULL = pgl::config::gw::TOPIC_PULL;
constexpr const char* TOPIC_NODE_COMMAND = pgl::config::gw::TOPIC_NODE_COMMAND;

float MESH_FREQ_MHZ = pgl::config::gw::MESH_FREQ_MHZ;
float MESH_BW_KHZ = pgl::config::gw::MESH_BW_KHZ;
uint8_t MESH_SF = pgl::config::gw::MESH_SF;
uint8_t MESH_CR = pgl::config::gw::MESH_CR;
uint8_t MESH_SYNC_WORD = pgl::config::gw::MESH_SYNC_WORD;
int8_t MESH_TX_POWER_DBM = pgl::config::gw::MESH_TX_POWER_DBM;
constexpr uint16_t MESH_PREAMBLE = pgl::config::gw::MESH_PREAMBLE;
constexpr float MESH_TCXO_VOLTAGE = pgl::config::gw::MESH_TCXO_VOLTAGE;
constexpr float MESH_XTAL_TCXO_VOLTAGE = pgl::config::gw::MESH_XTAL_TCXO_VOLTAGE;
constexpr uint32_t MESH_SPI_HZ = pgl::config::gw::MESH_SPI_HZ;
constexpr uint32_t WIFI_RETRY_MS = pgl::config::gw::WIFI_RETRY_MS;
constexpr uint32_t MQTT_RETRY_MS = pgl::config::gw::MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = pgl::config::gw::STATUS_INTERVAL_MS;
constexpr uint8_t MQTT_UPLINK_QUEUE_CAPACITY = pgl::config::gw::MQTT_UPLINK_QUEUE_CAPACITY;
constexpr size_t MQTT_UPLINK_QUEUE_ITEM_BYTES = pgl::config::gw::MQTT_UPLINK_QUEUE_ITEM_BYTES;
constexpr uint8_t CONFIG_RESPONSE_REPEAT_COUNT = pgl::config::gw::CONFIG_RESPONSE_REPEAT_COUNT;
constexpr uint16_t CONFIG_RESPONSE_REPEAT_GAP_MS = pgl::config::gw::CONFIG_RESPONSE_REPEAT_GAP_MS;

void logPrintln(const char* text);
void logPrintf(const char* fmt, ...);

void loadMeshConfig() {
    RuntimeMeshConfig fallback{MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR,
                               MESH_SYNC_WORD, MESH_TX_POWER_DBM};
    Preferences prefs;
    if (!prefs.begin(MESH_CONFIG_NAMESPACE, true)) return;
    const uint32_t magic = prefs.getUInt("magic", 0);
    RuntimeMeshConfig stored{
        prefs.getFloat("freq", fallback.freqMHz),
        prefs.getFloat("bw", fallback.bwKHz),
        prefs.getUChar("sf", fallback.sf),
        prefs.getUChar("cr", fallback.cr),
        prefs.getUChar("sync", fallback.syncWord),
        static_cast<int8_t>(prefs.getChar("tx", fallback.txPowerDbm)),
    };
    prefs.end();
    if (magic != MESH_CONFIG_MAGIC) return;
    if (!isValidMeshConfig(stored)) {
        logPrintln("GW_NVS_MESH_LORA_INVALID fallback=build-time");
        return;
    }
    MESH_FREQ_MHZ = stored.freqMHz;
    MESH_BW_KHZ = stored.bwKHz;
    MESH_SF = stored.sf;
    MESH_CR = stored.cr;
    MESH_SYNC_WORD = stored.syncWord;
    MESH_TX_POWER_DBM = stored.txPowerDbm;
    logPrintf("GW_NVS_MESH_LORA_LOAD freq=%.3f bw=%.2f sf=%u cr=%u sync=0x%02X tx=%d\n",
              MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR,
              MESH_SYNC_WORD, MESH_TX_POWER_DBM);
}

bool saveMeshConfig(const RuntimeMeshConfig& cfg) {
    if (!isValidMeshConfig(cfg)) return false;
    Preferences prefs;
    if (!prefs.begin(MESH_CONFIG_NAMESPACE, false)) return false;
    bool ok = true;
    ok = ok && prefs.putUInt("magic", MESH_CONFIG_MAGIC) == sizeof(uint32_t);
    ok = ok && prefs.putFloat("freq", cfg.freqMHz) == sizeof(float);
    ok = ok && prefs.putFloat("bw", cfg.bwKHz) == sizeof(float);
    ok = ok && prefs.putUChar("sf", cfg.sf) == sizeof(uint8_t);
    ok = ok && prefs.putUChar("cr", cfg.cr) == sizeof(uint8_t);
    ok = ok && prefs.putUChar("sync", cfg.syncWord) == sizeof(uint8_t);
    ok = ok && prefs.putChar("tx", cfg.txPowerDbm) == sizeof(int8_t);
    prefs.end();
    if (!ok) return false;

    Preferences verify;
    if (!verify.begin(MESH_CONFIG_NAMESPACE, true)) return false;
    const bool match =
        verify.getUInt("magic", 0) == MESH_CONFIG_MAGIC &&
        verify.getFloat("freq", -1.0f) == cfg.freqMHz &&
        verify.getFloat("bw", -1.0f) == cfg.bwKHz &&
        verify.getUChar("sf", 0) == cfg.sf &&
        verify.getUChar("cr", 0) == cfg.cr &&
        verify.getUChar("sync", 0) == cfg.syncWord &&
        verify.getChar("tx", -128) == cfg.txPowerDbm;
    verify.end();
    return match;
}

Module* meshModule = nullptr;
SX1262* meshRadio = nullptr;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

uint8_t meshSeq = 0;
uint16_t requestId = 1;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastMqttAttemptMs = 0;
uint32_t lastStatusMs = 0;
bool meshReady = false;
bool mqttSubCommands = false;
bool mqttSubPull = false;
bool mqttSubNodeCommand = false;
char mqttClientId[48]{};

struct PendingMqttPublish {
    bool used;
    char topic[96];
    char payload[MQTT_UPLINK_QUEUE_ITEM_BYTES];
    size_t len;
    uint32_t enqueuedAtMs;
    uint8_t attempts;
};

PendingMqttPublish mqttQueue[MQTT_UPLINK_QUEUE_CAPACITY]{};
uint32_t mqttQueuePublished = 0;
uint32_t mqttQueueDropped = 0;

struct RecentHello {
    bool active;
    uint16_t origin;
    uint16_t token;
    uint8_t seq;
    uint32_t seenAtMs;
};

constexpr size_t RECENT_HELLO_CAPACITY = 16;
constexpr uint32_t RECENT_HELLO_TTL_MS = 60000;
RecentHello recentHellos[RECENT_HELLO_CAPACITY]{};

void logPrint(const char* text) {
    Serial.print(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(text);
#endif
}

void logPrintln(const char* text) {
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

void logPrintf(const char* fmt, ...) {
    char buffer[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    logPrint(buffer);
}

size_t mqttQueueDepth() {
    size_t depth = 0;
    for (const auto& item : mqttQueue) {
        if (item.used) {
            depth++;
        }
    }
    return depth;
}

int findFreeMqttQueueSlot() {
    for (size_t i = 0; i < MQTT_UPLINK_QUEUE_CAPACITY; ++i) {
        if (!mqttQueue[i].used) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

bool publishMqttNow(const char* topic, const char* payload, size_t len, const char* reason) {
    const bool ok = mqtt.connected() &&
                    topic != nullptr &&
                    payload != nullptr &&
                    len > 0 &&
                    mqtt.publish(topic, reinterpret_cast<const uint8_t*>(payload), len);
    logPrintf("GW_MQTT_PUBLISH_NOW reason=%s topic=%s ok=%u len=%u queueDepth=%u\n",
              reason,
              topic != nullptr ? topic : "(null)",
              ok ? 1 : 0,
              static_cast<unsigned>(len),
              static_cast<unsigned>(mqttQueueDepth()));
    return ok;
}

bool enqueueMqttPublish(const char* topic, const char* payload, size_t len, const char* reason) {
    if (topic == nullptr || payload == nullptr || len == 0 || len >= MQTT_UPLINK_QUEUE_ITEM_BYTES) {
        mqttQueueDropped++;
        logPrintf("GW_MQTT_QUEUE_DROP reason=%s topic=%s len=%u capacityBytes=%u dropped=%lu\n",
                  reason,
                  topic != nullptr ? topic : "(null)",
                  static_cast<unsigned>(len),
                  static_cast<unsigned>(MQTT_UPLINK_QUEUE_ITEM_BYTES),
                  static_cast<unsigned long>(mqttQueueDropped));
        return false;
    }

    const int slot = findFreeMqttQueueSlot();
    if (slot < 0) {
        mqttQueueDropped++;
        logPrintf("GW_MQTT_QUEUE_DROP reason=%s topic=%s len=%u queueFull=1 depth=%u dropped=%lu\n",
                  reason,
                  topic,
                  static_cast<unsigned>(len),
                  static_cast<unsigned>(mqttQueueDepth()),
                  static_cast<unsigned long>(mqttQueueDropped));
        return false;
    }

    PendingMqttPublish& item = mqttQueue[slot];
    item.used = true;
    strncpy(item.topic, topic, sizeof(item.topic) - 1);
    item.topic[sizeof(item.topic) - 1] = '\0';
    memcpy(item.payload, payload, len);
    item.payload[len] = '\0';
    item.len = len;
    item.enqueuedAtMs = millis();
    item.attempts = 0;
    logPrintf("GW_MQTT_QUEUE_ENQUEUE reason=%s topic=%s len=%u depth=%u dropped=%lu\n",
              reason,
              item.topic,
              static_cast<unsigned>(len),
              static_cast<unsigned>(mqttQueueDepth()),
              static_cast<unsigned long>(mqttQueueDropped));
    return true;
}

enum class PublishDisposition : uint8_t {
    Rejected,
    PublishedImmediately,
    QueuedVolatile,
};

const char* publishDispositionName(PublishDisposition disposition) {
    switch (disposition) {
        case PublishDisposition::Rejected:             return "rejected";
        case PublishDisposition::PublishedImmediately: return "published-immediately";
        case PublishDisposition::QueuedVolatile:       return "queued-volatile";
    }
    return "unknown";
}

PublishDisposition publishOrQueueMqttDisposition(
    const char* topic, const char* payload, size_t len, const char* reason) {
    if (publishMqttNow(topic, payload, len, reason)) {
        return PublishDisposition::PublishedImmediately;
    }
    return enqueueMqttPublish(topic, payload, len, reason)
        ? PublishDisposition::QueuedVolatile
        : PublishDisposition::Rejected;
}

bool publishOrQueueMqtt(const char* topic, const char* payload, size_t len, const char* reason) {
    return publishOrQueueMqttDisposition(topic, payload, len, reason) !=
           PublishDisposition::Rejected;
}

void drainMqttQueue() {
    if (!mqtt.connected()) {
        return;
    }
    for (size_t i = 0; i < MQTT_UPLINK_QUEUE_CAPACITY; ++i) {
        PendingMqttPublish& item = mqttQueue[i];
        if (!item.used) {
            continue;
        }
        item.attempts++;
        const bool ok = mqtt.publish(item.topic, reinterpret_cast<const uint8_t*>(item.payload), item.len);
        logPrintf("GW_MQTT_QUEUE_DRAIN topic=%s ok=%u len=%u attempts=%u ageMs=%lu depth=%u\n",
                  item.topic,
                  ok ? 1 : 0,
                  static_cast<unsigned>(item.len),
                  item.attempts,
                  static_cast<unsigned long>(millis() - item.enqueuedAtMs),
                  static_cast<unsigned>(mqttQueueDepth()));
        if (!ok) {
            return;
        }
        item.used = false;
        item.len = 0;
        mqttQueuePublished++;
        return;
    }
}

int8_t clampToI8(float value) {
    if (value < -128.0f) return -128;
    if (value > 127.0f) return 127;
    return static_cast<int8_t>(value);
}

void bytesToHex(const uint8_t* data, size_t len, char* out, size_t outCapacity) {
    constexpr char HEX_DIGITS[] = "0123456789ABCDEF";
    if (outCapacity == 0) {
        return;
    }
    const size_t maxBytes = (outCapacity - 1) / 2;
    const size_t bytes = len < maxBytes ? len : maxBytes;
    for (size_t i = 0; i < bytes; ++i) {
        out[i * 2] = HEX_DIGITS[(data[i] >> 4) & 0x0F];
        out[i * 2 + 1] = HEX_DIGITS[data[i] & 0x0F];
    }
    out[bytes * 2] = '\0';
}

uint16_t parseU16Value(JsonVariantConst value, uint16_t fallback) {
    if (value.isNull()) {
        return fallback;
    }
    if (value.is<unsigned int>() || value.is<int>()) {
        return static_cast<uint16_t>(value.as<unsigned int>() & 0xFFFF);
    }
    const char* text = value.as<const char*>();
    if (text == nullptr || text[0] == '\0') {
        return fallback;
    }
    char* end = nullptr;
    const int base = (strlen(text) > 2 && text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) ? 16 : 10;
    const unsigned long parsed = strtoul(text, &end, base);
    return end == text ? fallback : static_cast<uint16_t>(parsed & 0xFFFF);
}

bool parseRequiredU16(JsonVariantConst value, uint16_t& out) {
    if (value.isNull()) {
        return false;
    }
    const uint16_t parsed = parseU16Value(value, 0);
    if (parsed == 0) {
        return false;
    }
    out = parsed;
    return true;
}

JsonVariantConst explicitHopListValue(const JsonDocument& doc) {
    JsonVariantConst hopListValue = doc["hopList"];
    if (hopListValue.isNull()) {
        hopListValue = doc["hop_list"];
    }
    if (hopListValue.isNull()) {
        hopListValue = doc["hops"];
    }
    return hopListValue;
}

size_t parseHopList(const JsonDocument& doc, uint16_t* out, size_t outCapacity) {
    if (out == nullptr || outCapacity == 0) {
        return 0;
    }

    const JsonVariantConst hopListValue = explicitHopListValue(doc);

    if (hopListValue.is<JsonArrayConst>()) {
        size_t count = 0;
        for (JsonVariantConst hop : hopListValue.as<JsonArrayConst>()) {
            if (count >= outCapacity) {
                break;
            }
            const uint16_t hopId = parseU16Value(hop, 0);
            if (hopId == 0) {
                return 0;
            }
            out[count++] = hopId;
        }
        return count;
    }

    uint16_t chId = 0;
    if (!parseRequiredU16(doc["cluster"], chId)) {
        return 0;
    }
    out[0] = chId;
    return 1;
}

uint16_t readU16Be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) | in[1]);
}

void writeU16Be(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

void writeHexId(JsonDocument& doc, const char* key, uint16_t value) {
    char hex[7];
    snprintf(hex, sizeof(hex), "0x%04X", value);
    doc[key] = hex;
}

void setupPinsSafe() {
    pinMode(pgl::gateway::board::PIN_STATUS_LED, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_STATUS_LED, LOW);

    pinMode(pgl::gateway::board::PIN_RADIO_UNUSED_A_CS, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_UNUSED_A_CS, HIGH);
    pinMode(pgl::gateway::board::PIN_RADIO_UNUSED_A_RST, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_UNUSED_A_RST, LOW);
    pinMode(pgl::gateway::board::PIN_RADIO_UNUSED_A_RXEN, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_UNUSED_A_RXEN, LOW);
    pinMode(pgl::gateway::board::PIN_RADIO_UNUSED_A_TXEN, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_UNUSED_A_TXEN, LOW);

    pinMode(pgl::gateway::board::PIN_RADIO_B_CS, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_CS, HIGH);
    pinMode(pgl::gateway::board::PIN_RADIO_B_RST, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_RST, LOW);
    pinMode(pgl::gateway::board::PIN_RADIO_B_RXEN, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_RXEN, LOW);
    pinMode(pgl::gateway::board::PIN_RADIO_B_TXEN, OUTPUT);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_TXEN, LOW);
}

void releaseRadioReset() {
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_RST, LOW);
    delay(50);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_RST, HIGH);
    delay(500);
}

bool beginMeshRadio() {
    SPI.begin(
        pgl::gateway::board::PIN_SPI_SCK,
        pgl::gateway::board::PIN_SPI_MISO,
        pgl::gateway::board::PIN_SPI_MOSI);
    releaseRadioReset();

    meshModule = new Module(
        pgl::gateway::board::PIN_RADIO_B_CS,
        pgl::gateway::board::PIN_RADIO_B_DIO1,
        pgl::gateway::board::PIN_RADIO_B_RST,
        pgl::gateway::board::PIN_RADIO_B_BUSY,
        SPI,
        SPISettings(MESH_SPI_HZ, MSBFIRST, SPI_MODE0));
    meshRadio = new SX1262(meshModule);

    int16_t beginState = meshRadio->begin(
        MESH_FREQ_MHZ,
        MESH_BW_KHZ,
        MESH_SF,
        MESH_CR,
        MESH_SYNC_WORD,
        MESH_TX_POWER_DBM,
        MESH_PREAMBLE,
        MESH_TCXO_VOLTAGE,
        false);
    logPrintf("GW_MESH_BEGIN_TCXO16_STATE=%d\n", beginState);
    if (beginState == RADIOLIB_ERR_SPI_CMD_FAILED) {
        beginState = meshRadio->begin(
            MESH_FREQ_MHZ,
            MESH_BW_KHZ,
            MESH_SF,
            MESH_CR,
            MESH_SYNC_WORD,
            MESH_TX_POWER_DBM,
            MESH_PREAMBLE,
            MESH_XTAL_TCXO_VOLTAGE,
            false);
        logPrintf("GW_MESH_BEGIN_XTAL_STATE=%d\n", beginState);
    }
    logPrintf("GW_MESH_BEGIN_STATE=%d\n", beginState);

    if (beginState != RADIOLIB_ERR_NONE) {
        logPrintln("GW_MESH_READY=0");
        return false;
    }

    meshRadio->setRfSwitchPins(pgl::gateway::board::PIN_RADIO_B_RXEN, pgl::gateway::board::PIN_RADIO_B_TXEN);
    logPrintln("GW_MESH_READY=1");
    return true;
}

void beginWifi() {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(netConfig.wifiSsid, netConfig.wifiPassword);
    lastWifiAttemptMs = millis();
    logPrintf("GW_WIFI_CONNECT ssid=%s\n", netConfig.wifiSsid);
}

void ensureWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    const uint32_t now = millis();
    if (now - lastWifiAttemptMs < WIFI_RETRY_MS) {
        return;
    }
    lastWifiAttemptMs = now;
    WiFi.disconnect();
    WiFi.begin(netConfig.wifiSsid, netConfig.wifiPassword);
    logPrintf("GW_WIFI_RETRY ssid=%s\n", netConfig.wifiSsid);
}

void mqttCallback(char* topic, uint8_t* payload, unsigned int length);
bool publishStatus(const char* state);

bool mqttHostConfigured() {
    return netConfig.mqttEnabled &&
           netConfig.mqttHost[0] != '\0' &&
           strcmp(netConfig.mqttHost, "CHANGE_ME_MQTT_HOST") != 0;
}

bool parseGatewayCommandTarget(JsonVariantConst value, uint16_t& out) {
    if (value.isNull() || value.is<bool>()) {
        return false;
    }

    unsigned long parsed = 0;
    if (value.is<unsigned int>() || value.is<int>()) {
        const long numeric = value.as<long>();
        if (numeric < 0) {
            return false;
        }
        parsed = static_cast<unsigned long>(numeric);
    } else {
        const char* text = value.as<const char*>();
        if (text == nullptr || text[0] == '\0') {
            return false;
        }
        char* end = nullptr;
        const int base = (strlen(text) > 2 && text[0] == '0' &&
                          (text[1] == 'x' || text[1] == 'X'))
                             ? 16
                             : 10;
        parsed = strtoul(text, &end, base);
        if (end == text || *end != '\0') {
            return false;
        }
    }

    if (parsed > 0xFFFFUL ||
        !pgl::config::isProvisionableGatewayId(static_cast<uint16_t>(parsed))) {
        return false;
    }
    out = static_cast<uint16_t>(parsed);
    return true;
}

bool commandTargetsThisGateway(const JsonDocument& doc, const char* topic) {
    const JsonVariantConst targetValue = doc["targetGatewayId"];
    const JsonVariantConst gatewayValue = doc["gatewayId"];
    const bool hasTarget = !targetValue.isNull();
    const bool hasGateway = !gatewayValue.isNull();
    if (!hasTarget && !hasGateway) {
        logPrintf("GW_MQTT_CMD_IGNORE topic=%s reason=missing-gateway-target local=0x%04X\n",
                  topic, gatewayId);
        return false;
    }

    uint16_t targetGatewayId = 0;
    uint16_t envelopeGatewayId = 0;
    if (hasTarget && !parseGatewayCommandTarget(targetValue, targetGatewayId)) {
        logPrintf("GW_MQTT_CMD_IGNORE topic=%s reason=invalid-targetGatewayId local=0x%04X\n",
                  topic, gatewayId);
        return false;
    }
    if (hasGateway && !parseGatewayCommandTarget(gatewayValue, envelopeGatewayId)) {
        logPrintf("GW_MQTT_CMD_IGNORE topic=%s reason=invalid-gatewayId local=0x%04X\n",
                  topic, gatewayId);
        return false;
    }
    if (hasTarget && hasGateway && targetGatewayId != envelopeGatewayId) {
        logPrintf("GW_MQTT_CMD_IGNORE topic=%s reason=conflicting-gateway-targets target=0x%04X gateway=0x%04X local=0x%04X\n",
                  topic, targetGatewayId, envelopeGatewayId, gatewayId);
        return false;
    }

    const uint16_t requestedGatewayId = hasTarget ? targetGatewayId : envelopeGatewayId;
    if (requestedGatewayId != gatewayId) {
        logPrintf("GW_MQTT_CMD_IGNORE topic=%s reason=gateway-target-mismatch target=0x%04X local=0x%04X\n",
                  topic, requestedGatewayId, gatewayId);
        return false;
    }
    return true;
}

void loadGatewayIdentity() {
    gatewayId = DEFAULT_GATEWAY_ID;
    gatewayIdentityLoadedFromNvs = false;
    Preferences prefs;
    if (!prefs.begin(GATEWAY_ID_CONFIG_NAMESPACE, true)) {
        return;
    }
    const uint32_t magic = prefs.getUInt("magic", 0);
    const uint16_t storedGatewayId = prefs.getUShort("gatewayId", DEFAULT_GATEWAY_ID);
    prefs.end();
    if (magic != GATEWAY_ID_CONFIG_MAGIC) {
        return;
    }
    if (!pgl::config::isProvisionableGatewayId(storedGatewayId)) {
        logPrintf("GW_NVS_ID_INVALID stored=0x%04X fallback=0x%04X\n",
                  storedGatewayId, DEFAULT_GATEWAY_ID);
        return;
    }
    gatewayId = storedGatewayId;
    gatewayIdentityLoadedFromNvs = true;
}

bool saveGatewayIdentity(uint16_t requestedGatewayId) {
    if (!pgl::config::isProvisionableGatewayId(requestedGatewayId)) {
        return false;
    }
    Preferences prefs;
    if (!prefs.begin(GATEWAY_ID_CONFIG_NAMESPACE, false)) {
        return false;
    }
    const bool idSaved = prefs.putUShort("gatewayId", requestedGatewayId) == sizeof(uint16_t);
    const bool magicSaved = prefs.putUInt("magic", GATEWAY_ID_CONFIG_MAGIC) == sizeof(uint32_t);
    prefs.end();
    if (!idSaved || !magicSaved) {
        return false;
    }

    if (!prefs.begin(GATEWAY_ID_CONFIG_NAMESPACE, true)) {
        return false;
    }
    const uint32_t readbackMagic = prefs.getUInt("magic", 0);
    const uint16_t readbackGatewayId = prefs.getUShort("gatewayId", 0);
    prefs.end();
    return readbackMagic == GATEWAY_ID_CONFIG_MAGIC &&
           readbackGatewayId == requestedGatewayId;
}

void beginMqtt() {
    if (!netConfig.mqttEnabled) {
        logPrintln("GW_MQTT_DISABLED waiting=SET_MQTT_CONFIG_JSON");
        return;
    }
    if (!mqttHostConfigured()) {
        logPrintln("GW_CONFIG_ERROR mqttHost=unconfigured action=inject-PGL_SERVER_SITE_MQTT_HOST");
        return;
    }
    mqtt.setServer(netConfig.mqttHost, netConfig.mqttPort);
    mqtt.setCallback(mqttCallback);
    mqtt.setBufferSize(1024);
}

void ensureMqtt() {
    if (!mqttHostConfigured() || WiFi.status() != WL_CONNECTED || mqtt.connected()) {
        return;
    }
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) {
        return;
    }
    lastMqttAttemptMs = now;

    snprintf(mqttClientId, sizeof(mqttClientId), "pgl-gateway-%04X-%08lX", gatewayId, static_cast<unsigned long>(ESP.getEfuseMac()));
    const bool ok = mqtt.connect(mqttClientId, netConfig.mqttUser, netConfig.mqttPassword);
    logPrintf("GW_MQTT_CONNECT host=%s port=%u ok=%u\n", netConfig.mqttHost, netConfig.mqttPort, ok ? 1 : 0);
    if (!ok) {
        return;
    }
    mqttSubCommands = mqtt.subscribe(TOPIC_COMMANDS);
    mqttSubPull = mqtt.subscribe(TOPIC_PULL);
    mqttSubNodeCommand = mqtt.subscribe(TOPIC_NODE_COMMAND);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_COMMANDS, mqttSubCommands ? 1 : 0);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_PULL, mqttSubPull ? 1 : 0);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_NODE_COMMAND, mqttSubNodeCommand ? 1 : 0);
    for (uint8_t i = 0; i < 5; ++i) {
        mqtt.loop();
        delay(10);
    }
    publishStatus("online");
}

bool publishStatus(const char* state) {
    StaticJsonDocument<1024> doc;
    const bool wifiConnected = WiFi.status() == WL_CONNECTED;
    const bool mqttConnected = mqtt.connected();
    doc["kind"] = "gateway-status";
    doc["gatewayId"] = gatewayId;
    doc["state"] = state;
    doc["firmwareVersion"] = pgl::firmware::GATEWAY_FIRMWARE_VERSION;
    doc["protocolVersion"] = pgl::firmware::PROTOCOL_VERSION;
    doc["uptimeMs"] = millis();
    doc["wifi"] = wifiConnected;
    doc["wifiSsid"] = netConfig.wifiSsid;
    doc["wifiRssi"] = wifiConnected ? WiFi.RSSI() : 0;
    doc["wifiChannel"] = wifiConnected ? WiFi.channel() : 0;
    doc["wifiMac"] = WiFi.macAddress();
    doc["mqtt"] = mqttConnected;
    doc["mqttHost"] = netConfig.mqttHost;
    doc["mqttPort"] = netConfig.mqttPort;
    doc["mqttAuthConfigured"] = netConfig.mqttUser[0] != '\0' || netConfig.mqttPassword[0] != '\0';
    doc["mqttState"] = mqtt.state();
    doc["mqttClientId"] = mqttClientId;
    doc["mqttSubscriptionsReady"] = mqttConnected && mqttSubCommands && mqttSubPull && mqttSubNodeCommand;
    doc["topicRoot"] = PGL_SERVER_SITE_TOPIC_ROOT;
    doc["meshReady"] = meshReady;
    doc["meshFreqMhz"] = MESH_FREQ_MHZ;
    doc["meshBandwidthKhz"] = MESH_BW_KHZ;
    doc["meshSpreadingFactor"] = MESH_SF;
    doc["meshCodingRate"] = MESH_CR;
    doc["meshSyncWord"] = MESH_SYNC_WORD;
    doc["meshTxPowerDbm"] = MESH_TX_POWER_DBM;
    doc["meshPreamble"] = MESH_PREAMBLE;
    doc["mqttQueueDepth"] = mqttQueueDepth();
    doc["mqttQueueDropped"] = mqttQueueDropped;
    doc["mqttQueuePublished"] = mqttQueuePublished;
    doc["mqttQueueCapacity"] = MQTT_UPLINK_QUEUE_CAPACITY;
    doc["ip"] = wifiConnected ? WiFi.localIP().toString() : "";

    char json[1024];
    const size_t len = serializeJson(doc, json, sizeof(json));
    const bool ok = mqtt.connected() && mqtt.publish(TOPIC_STATUS, reinterpret_cast<const uint8_t*>(json), len);
    logPrintf("GW_MQTT_STATUS state=%s ok=%u\n", state, ok ? 1 : 0);
    return ok;
}

void publishStatusPeriodic() {
    const uint32_t now = millis();
    if (now - lastStatusMs < STATUS_INTERVAL_MS) {
        return;
    }
    lastStatusMs = now;
    publishStatus("alive");
}

bool transmitMeshFrame(const uint8_t* frame, size_t frameSize, const char* reason) {
    if (!meshReady || meshRadio == nullptr) {
        logPrintf("GW_MESH_TX_SKIP reason=%s meshReady=0\n", reason);
        return false;
    }
    const int16_t txState = meshRadio->transmit(frame, frameSize);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_RXEN, LOW);
    digitalWrite(pgl::gateway::board::PIN_RADIO_B_TXEN, LOW);
    logPrintf("GW_MESH_TX reason=%s state=%d len=%u\n", reason, txState, static_cast<unsigned>(frameSize));
    return txState == RADIOLIB_ERR_NONE;
}

void handlePullCommand(const JsonDocument& doc) {
    constexpr size_t MAX_PULL_HOPS = (pgl::protocol::MESH_MAX_PAYLOAD - 2) / 2;
    uint16_t hopList[MAX_PULL_HOPS]{};
    const size_t hopCount = parseHopList(doc, hopList, MAX_PULL_HOPS);
    if (hopCount == 0 || hopList[0] == 0) {
        logPrintln("GW_PULL_BUILD_FAIL invalidHopList=1");
        return;
    }

    const uint16_t nextHop = hopList[0];
    uint16_t pullRequestId = 0;
    if (!doc["requestId"].isNull()) {
        pullRequestId = parseU16Value(doc["requestId"], 0);
    } else if (!doc["id"].isNull()) {
        pullRequestId = parseU16Value(doc["id"], 0);
    } else {
        pullRequestId = requestId++;
    }
    if (pullRequestId == 0) {
        logPrintln("GW_PULL_BUILD_FAIL invalidRequestId=1");
        return;
    }
    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD]{};
    writeU16Be(&payload[0], pullRequestId);
    for (size_t i = 0; i < hopCount; ++i) {
        writeU16Be(&payload[2 + (i * 2)], hopList[i]);
    }
    const size_t payloadLen = 2 + (hopCount * 2);

    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_SERVER_PULL_REQUEST,
        gatewayId,
        nextHop,
        meshSeq++,
        payload,
        payloadLen,
        frame,
        sizeof(frame),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status != pgl::protocol::FrameStatus::Ok) {
        logPrintf("GW_PULL_BUILD_FAIL status=%u\n", static_cast<unsigned>(encoded.status));
        return;
    }
    logPrintf("GW_PULL_BUILD requestId=%u hopCount=%u nextHop=0x%04X payloadLen=%u\n",
              static_cast<unsigned>(pullRequestId),
              static_cast<unsigned>(hopCount),
              nextHop,
              static_cast<unsigned>(payloadLen));
    transmitMeshFrame(frame, encoded.size, "server-pull");
}

void hexToBytes(const char* hex, uint8_t* out, size_t outCapacity, size_t& outLen) {
    outLen = 0;
    if (hex == nullptr) {
        return;
    }
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    int high = -1;
    for (const char* p = hex; *p != '\0' && outLen < outCapacity; ++p) {
        const int v = nibble(*p);
        if (v < 0) {
            continue;
        }
        if (high < 0) {
            high = v;
        } else {
            out[outLen++] = static_cast<uint8_t>((high << 4) | v);
            high = -1;
        }
    }
}

void handleNodeCommand(const JsonDocument& doc) {
    constexpr size_t MAX_NODE_COMMAND_HOPS =
        (pgl::protocol::MESH_MAX_PAYLOAD -
         pgl::protocol::SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE -
         pgl::protocol::SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE -
         pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE) / 2;
    uint16_t hopList[MAX_NODE_COMMAND_HOPS]{};
    const JsonVariantConst hopListValue = explicitHopListValue(doc);
    const bool routed = !hopListValue.isNull();
    size_t hopCount = 0;
    uint16_t chId = 0;
    uint16_t nodeId = 0;
    if (routed) {
        if (!hopListValue.is<JsonArrayConst>() ||
            hopListValue.as<JsonArrayConst>().size() == 0 ||
            hopListValue.as<JsonArrayConst>().size() > MAX_NODE_COMMAND_HOPS) {
            logPrintf("GW_NODE_COMMAND_BUILD_FAIL invalidHopList=1 maxHops=%u\n",
                      static_cast<unsigned>(MAX_NODE_COMMAND_HOPS));
            return;
        }
        hopCount = parseHopList(doc, hopList, MAX_NODE_COMMAND_HOPS);
        if (!pgl::protocol::serverNodeCommandRouteIsValid(hopList, hopCount)) {
            logPrintln("GW_NODE_COMMAND_BUILD_FAIL invalidHopList=1");
            return;
        }
        chId = hopList[hopCount - 1];
        if (!doc["cluster"].isNull()) {
            uint16_t requestedChId = 0;
            if (!parseRequiredU16(doc["cluster"], requestedChId) || requestedChId != chId) {
                logPrintf("GW_NODE_COMMAND_BUILD_FAIL clusterRouteMismatch=1 routeTarget=0x%04X\n",
                          chId);
                return;
            }
        }
    } else if (!parseRequiredU16(doc["cluster"], chId)) {
        logPrintln("GW_NODE_COMMAND_BUILD_FAIL missingCluster=1");
        return;
    }
    if (!parseRequiredU16(doc["node"], nodeId)) {
        logPrintln("GW_NODE_COMMAND_BUILD_FAIL missingNode=1");
        return;
    }
    const uint16_t commandId = parseU16Value(doc["id"], 1);
    const uint16_t ttlSec = parseU16Value(doc["ttl"], 600);
    uint8_t commandBytes[pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE + 1]{};
    size_t commandLen = 0;
    hexToBytes(doc["hex"] | "", commandBytes, sizeof(commandBytes), commandLen);
    if (commandLen > pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE) {
        logPrintf("GW_NODE_COMMAND_BUILD_FAIL commandTooLong=%u max=%u\n",
                  static_cast<unsigned>(commandLen),
                  static_cast<unsigned>(pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE));
        return;
    }

    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD]{};
    size_t payloadLen = 0;
    const pgl::protocol::ServerNodeCommandStatus payloadStatus = routed
        ? pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              hopList, hopCount, nodeId, commandId, ttlSec,
              commandBytes, commandLen, payload, sizeof(payload), payloadLen)
        : pgl::protocol::encodeLegacyServerNodeCommandPayload(
              nodeId, commandId, ttlSec, commandBytes, commandLen,
              payload, sizeof(payload), payloadLen);
    if (payloadStatus != pgl::protocol::ServerNodeCommandStatus::Ok) {
        logPrintf("GW_NODE_COMMAND_BUILD_FAIL payloadStatus=%s routed=%u hopCount=%u\n",
                  pgl::protocol::serverNodeCommandStatusName(payloadStatus),
                  routed ? 1 : 0, static_cast<unsigned>(hopCount));
        return;
    }

    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_SERVER_NODE_COMMAND,
        gatewayId,
        routed ? hopList[0] : chId,
        meshSeq++,
        payload,
        static_cast<uint8_t>(payloadLen),
        frame,
        sizeof(frame),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status != pgl::protocol::FrameStatus::Ok) {
        logPrintf("GW_NODE_COMMAND_BUILD_FAIL status=%u\n", static_cast<unsigned>(encoded.status));
        return;
    }
    logPrintf("GW_NODE_COMMAND_BUILD routeVersion=%u hopCount=%u nextHop=0x%04X targetCh=0x%04X node=0x%04X commandId=%u commandLen=%u payloadLen=%u\n",
              routed ? pgl::protocol::SERVER_NODE_COMMAND_ROUTE_VERSION_V1 : 0,
              static_cast<unsigned>(hopCount), routed ? hopList[0] : chId,
              chId, nodeId, commandId, static_cast<unsigned>(commandLen),
              static_cast<unsigned>(payloadLen));
    transmitMeshFrame(frame, encoded.size, "node-command");
}

void mqttCallback(char* topic, uint8_t* payload, unsigned int length) {
    char json[512];
    const size_t copyLen = length < sizeof(json) - 1 ? length : sizeof(json) - 1;
    memcpy(json, payload, copyLen);
    json[copyLen] = '\0';

    StaticJsonDocument<512> doc;
    const DeserializationError err = deserializeJson(doc, json);
    if (err) {
        logPrintf("GW_MQTT_JSON_FAIL topic=%s err=%s\n", topic, err.c_str());
        return;
    }

    logPrintf("GW_MQTT_CMD topic=%s len=%u\n", topic, length);
    if (strcmp(topic, TOPIC_PULL) == 0 || strstr(topic, "/pull") != nullptr) {
        if (!commandTargetsThisGateway(doc, topic)) {
            return;
        }
        handlePullCommand(doc);
    } else if (strcmp(topic, TOPIC_NODE_COMMAND) == 0 || strstr(topic, "/node") != nullptr) {
        if (!commandTargetsThisGateway(doc, topic)) {
            return;
        }
        handleNodeCommand(doc);
    }
}

bool publishTopologyReport(const pgl::protocol::FrameView& decoded, float rssi, float snr) {
    const uint8_t msgType = pgl::protocol::messageType(decoded.typeFlags);
    if (decoded.srcId == gatewayId) {
        return false;
    }
    if (msgType != pgl::protocol::MSG_CH_HELLO &&
        msgType != pgl::protocol::MSG_CH_CONFIG_REQUEST &&
        msgType != pgl::protocol::MSG_CH_CONFIG_RESPONSE) {
        return false;
    }

    StaticJsonDocument<1024> doc;
    doc["kind"] = "gateway-topology";
    doc["source"] = "gateway";
    doc["gatewayId"] = gatewayId;
    doc["rootId"] = gatewayId;
    doc["msgType"] = msgType;
    doc["typeFlags"] = decoded.typeFlags;
    doc["srcId"] = decoded.srcId;
    doc["dstId"] = decoded.dstId;
    doc["seq"] = decoded.seq;
    doc["payloadLen"] = decoded.payloadLen;
    doc["rssi"] = rssi;
    doc["snr"] = snr;
    writeHexId(doc, "gatewayIdHex", gatewayId);
    writeHexId(doc, "rootIdHex", gatewayId);
    writeHexId(doc, "srcIdHex", decoded.srcId);
    writeHexId(doc, "dstIdHex", decoded.dstId);

    uint16_t chId = decoded.srcId;
    uint16_t parentId = 0;
    const char* reportType = "mesh-control";

    if (msgType == pgl::protocol::MSG_CH_HELLO) {
        if (decoded.payloadLen < 8 || decoded.payload == nullptr) {
            logPrintf("GW_TOPOLOGY_SKIP report=ch-hello src=0x%04X reason=short-payload len=%u\n",
                      decoded.srcId, decoded.payloadLen);
            return false;
        }
        reportType = "ch-hello";
        chId = readU16Be(&decoded.payload[0]);
        parentId = readU16Be(&decoded.payload[2]);
        const uint16_t parentAltId = decoded.payloadLen >= 11 ? readU16Be(&decoded.payload[9]) : 0;
        doc["chId"] = chId;
        doc["parentId"] = parentId;
        doc["parentAltId"] = parentAltId;
        doc["edgeFrom"] = chId;
        doc["edgeTo"] = parentId;
        doc["batteryMv"] = readU16Be(&decoded.payload[4]);
        doc["uptimeSec16"] = readU16Be(&decoded.payload[6]);
        doc["parentIsRoot"] = parentId == gatewayId;
        writeHexId(doc, "chIdHex", chId);
        writeHexId(doc, "parentIdHex", parentId);
        writeHexId(doc, "parentAltIdHex", parentAltId);
        writeHexId(doc, "edgeFromHex", chId);
        writeHexId(doc, "edgeToHex", parentId);
    } else if (msgType == pgl::protocol::MSG_CH_CONFIG_RESPONSE) {
        if (decoded.payloadLen < 8 || decoded.payload == nullptr) {
            logPrintf("GW_TOPOLOGY_SKIP report=ch-config-response src=0x%04X reason=short-payload len=%u\n",
                      decoded.srcId, decoded.payloadLen);
            return false;
        }
        reportType = "ch-config-response";
        chId = decoded.srcId;
        const uint16_t requesterId = readU16Be(&decoded.payload[0]);
        parentId = readU16Be(&decoded.payload[2]);
        const uint8_t routeFlags = decoded.payload[7];
        doc["chId"] = chId;
        doc["requesterId"] = requesterId;
        doc["parentId"] = parentId;
        doc["edgeFrom"] = chId;
        doc["edgeTo"] = parentId;
        doc["depth"] = decoded.payload[4];
        doc["batteryMv"] = readU16Be(&decoded.payload[5]);
        doc["routeFlags"] = routeFlags;
        doc["routeToRoot"] = (routeFlags & pgl::protocol::CH_CONFIG_FLAG_ROUTE_TO_ROOT) != 0;
        doc["helloAckV1"] = (routeFlags & pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1) != 0;
        doc["alarmAckNodeIdV1"] =
            (routeFlags & pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1) != 0;
        doc["nodeCommandRouteV1"] =
            (routeFlags & pgl::protocol::CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1) != 0;
        doc["parentIsRoot"] = parentId == gatewayId;
        writeHexId(doc, "chIdHex", chId);
        writeHexId(doc, "requesterIdHex", requesterId);
        writeHexId(doc, "parentIdHex", parentId);
        writeHexId(doc, "edgeFromHex", chId);
        writeHexId(doc, "edgeToHex", parentId);
    } else {
        reportType = "ch-config-request";
        uint16_t requesterId = decoded.srcId;
        if (decoded.payloadLen >= 2 && decoded.payload != nullptr) {
            requesterId = readU16Be(&decoded.payload[0]);
        }
        chId = requesterId;
        doc["chId"] = chId;
        doc["requesterId"] = requesterId;
        writeHexId(doc, "chIdHex", chId);
        writeHexId(doc, "requesterIdHex", requesterId);
    }

    doc["reportType"] = reportType;

    char json[1024];
    const size_t len = serializeJson(doc, json, sizeof(json));
    const bool ok = publishOrQueueMqtt(TOPIC_TOPOLOGY, json, len, "topology");
    if (parentId != 0) {
        logPrintf("GW_TOPOLOGY_PUBLISH topic=%s report=%s ch=0x%04X parent=0x%04X ok=%u\n",
                  TOPIC_TOPOLOGY, reportType, chId, parentId, ok ? 1 : 0);
    } else {
        logPrintf("GW_TOPOLOGY_PUBLISH topic=%s report=%s ch=0x%04X ok=%u\n",
                  TOPIC_TOPOLOGY, reportType, chId, ok ? 1 : 0);
    }
    return ok;
}

PublishDisposition publishMeshFrame(const uint8_t* frame, size_t frameLen, float rssi, float snr) {
    char frameHex[2 * (pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD) + 1]{};
    bytesToHex(frame, frameLen, frameHex, sizeof(frameHex));

    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);

    StaticJsonDocument<1024> doc;
    doc["source"] = "gateway";
    doc["gatewayId"] = gatewayId;
    doc["frameHex"] = frameHex;
    doc["frameLen"] = frameLen;
    doc["rssi"] = rssi;
    doc["snr"] = snr;
    doc["parseStatus"] = static_cast<uint8_t>(parseStatus);
    if (parseStatus == pgl::protocol::FrameStatus::Ok) {
        doc["typeFlags"] = decoded.typeFlags;
        const uint8_t msgType = pgl::protocol::messageType(decoded.typeFlags);
        doc["msgType"] = msgType;
        doc["srcId"] = decoded.srcId;
        doc["dstId"] = decoded.dstId;
        doc["seq"] = decoded.seq;
        doc["payloadLen"] = decoded.payloadLen;
        if (msgType == pgl::protocol::MSG_CH_HELLO &&
            decoded.payload != nullptr &&
            decoded.payloadLen >= 8) {
            JsonObject topology = doc["topology"].to<JsonObject>();
            topology["kind"] = "ch-topology";
            topology["clusterId"] = readU16Be(&decoded.payload[0]);
            topology["parentId"] = readU16Be(&decoded.payload[2]);
            topology["parentAltId"] = decoded.payloadLen >= 11 ? readU16Be(&decoded.payload[9]) : 0;
            topology["batteryMv"] = readU16Be(&decoded.payload[4]);
            topology["uptimeSec16"] = readU16Be(&decoded.payload[6]);
            topology["meshDepth"] = decoded.payloadLen >= 9 ? decoded.payload[8] : 0xFF;
            topology["parentIsRoot"] = readU16Be(&decoded.payload[2]) == gatewayId;
            topology["viaHop"] = decoded.srcId;
            topology["gatewayId"] = gatewayId;
            topology["rssi"] = rssi;
            topology["snr"] = snr;
        }
        publishTopologyReport(decoded, rssi, snr);
    }

    char json[1024];
    const size_t len = serializeJson(doc, json, sizeof(json));
    const PublishDisposition disposition =
        publishOrQueueMqttDisposition(TOPIC_UPLINK, json, len, "uplink");
    logPrintf("GW_MQTT_PUBLISH topic=%s disposition=%s frameLen=%u parseStatus=%u\n",
              TOPIC_UPLINK,
              publishDispositionName(disposition),
              static_cast<unsigned>(frameLen),
              static_cast<unsigned>(parseStatus));
    return disposition;
}

void sendGatewayAckIfNeeded(const uint8_t* frame, size_t frameLen,
                            PublishDisposition disposition) {
    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (parseStatus != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_SENSOR_DATA ||
        !pgl::protocol::hasAlarmAckFlag(decoded.typeFlags) ||
        decoded.payload == nullptr ||
        decoded.payloadLen < pgl::protocol::GLD_RECORD_HEADER_SIZE) {
        return;
    }
    if (disposition != PublishDisposition::PublishedImmediately) {
        logPrintf("GW_ALARM_ACK_WITHHELD src=0x%04X seq=%u disposition=%s reason=no-immediate-mqtt-accept\n",
                  decoded.srcId, decoded.seq, publishDispositionName(disposition));
        return;
    }

    uint8_t ackPayload[pgl::protocol::MESH_ALARM_ACK_V1_PAYLOAD_SIZE]{};
    ackPayload[0] = decoded.payload[0];
    ackPayload[1] = decoded.payload[1];
    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD +
                pgl::protocol::MESH_ALARM_ACK_V1_PAYLOAD_SIZE]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::TYPE_ALARM_ACK_COMPACT,
        gatewayId,
        decoded.srcId,
        decoded.seq,
        ackPayload,
        sizeof(ackPayload),
        ack,
        sizeof(ack),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status == pgl::protocol::FrameStatus::Ok) {
        transmitMeshFrame(ack, encoded.size, "gateway-ack");
    }
}

bool suppressDuplicateHello(const uint8_t* frame, size_t frameLen) {
    pgl::protocol::FrameView decoded{};
    if (pgl::protocol::decodeAppFrame(frame, frameLen, decoded,
                                      pgl::protocol::MESH_MAX_PAYLOAD) != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_CH_HELLO ||
        decoded.payload == nullptr || decoded.payloadLen < 8) {
        return false;
    }

    const uint16_t origin = readU16Be(&decoded.payload[0]);
    const uint16_t token = readU16Be(&decoded.payload[6]);
    const uint32_t now = millis();
    RecentHello* replacement = nullptr;
    for (auto& item : recentHellos) {
        if (item.active && now - item.seenAtMs > RECENT_HELLO_TTL_MS) item.active = false;
        if (item.active && item.origin == origin && item.seq == decoded.seq && item.token == token) {
            item.seenAtMs = now;
            return true;
        }
        if (!item.active || replacement == nullptr || item.seenAtMs < replacement->seenAtMs) {
            replacement = &item;
        }
    }
    if (replacement != nullptr) {
        replacement->active = true;
        replacement->origin = origin;
        replacement->token = token;
        replacement->seq = decoded.seq;
        replacement->seenAtMs = now;
    }
    return false;
}

void sendHelloAckIfNeeded(const uint8_t* frame, size_t frameLen) {
    pgl::protocol::FrameView decoded{};
    const auto parseStatus = pgl::protocol::decodeAppFrame(
        frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (parseStatus != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_CH_HELLO ||
        decoded.dstId != gatewayId || decoded.srcId == gatewayId ||
        decoded.payload == nullptr ||
        decoded.payloadLen < pgl::protocol::CH_HELLO_V1_PAYLOAD_SIZE ||
        readU16Be(&decoded.payload[0]) != decoded.srcId ||
        readU16Be(&decoded.payload[2]) != gatewayId ||
        (decoded.payload[11] & pgl::protocol::CH_HELLO_FLAG_ACK_REQUEST_V1) == 0) {
        return;
    }

    uint8_t ackPayload[pgl::protocol::CH_HELLO_ACK_V1_PAYLOAD_SIZE]{};
    ackPayload[0] = decoded.payload[0];
    ackPayload[1] = decoded.payload[1];
    ackPayload[2] = decoded.payload[6];
    ackPayload[3] = decoded.payload[7];
    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD +
                pgl::protocol::CH_HELLO_ACK_V1_PAYLOAD_SIZE]{};
    const auto encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_HELLO_ACK,
        gatewayId,
        decoded.srcId,
        decoded.seq,
        ackPayload,
        sizeof(ackPayload),
        ack,
        sizeof(ack),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status != pgl::protocol::FrameStatus::Ok) {
        logPrintf("GW_HELLO_ACK_BUILD_FAIL ch=0x%04X seq=%u status=%u\n",
                  decoded.srcId, decoded.seq, static_cast<unsigned>(encoded.status));
        return;
    }
    const bool txOk = transmitMeshFrame(ack, encoded.size, "hello-ack");
    logPrintf("GW_HELLO_ACK_TX ch=0x%04X seq=%u txOk=%u\n",
              decoded.srcId, decoded.seq, txOk ? 1 : 0);
}

void sendGatewayConfigResponseIfNeeded(const uint8_t* frame, size_t frameLen,
                                       float requestRssiDbm, float requestSnrDb) {
    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (parseStatus != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_CH_CONFIG_REQUEST ||
        decoded.dstId != 0xFFFF ||
        decoded.srcId == gatewayId) {
        return;
    }

    uint16_t requesterId = decoded.srcId;
    if (decoded.payloadLen >= 2 && decoded.payload != nullptr) {
        requesterId = readU16Be(&decoded.payload[0]);
    }
    if (requesterId != decoded.srcId) {
        logPrintf("GW_CONFIG_REQUEST_WARN src=0x%04X payloadRequester=0x%04X\n",
                  decoded.srcId, requesterId);
        requesterId = decoded.srcId;
    }

    uint8_t payload[10]{};
    writeU16Be(&payload[0], requesterId);
    writeU16Be(&payload[2], 0);
    payload[4] = 0;       // Gateway depth to root.
    payload[5] = 0xFF;    // Battery unknown/not applicable.
    payload[6] = 0xFF;
    payload[7] = pgl::protocol::CH_CONFIG_FLAG_ROUTE_TO_ROOT |
                 pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1 |
                 pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1 |
                 pgl::protocol::CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1;
    payload[8] = static_cast<uint8_t>(clampToI8(requestRssiDbm));  // GW hears CH RSSI.
    payload[9] = static_cast<uint8_t>(clampToI8(requestSnrDb));    // GW hears CH SNR.

    uint8_t response[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_CONFIG_RESPONSE,
        gatewayId,
        requesterId,
        decoded.seq,
        payload,
        sizeof(payload),
        response,
        sizeof(response),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status == pgl::protocol::FrameStatus::Ok) {
        delay(20);
        const uint8_t repeatCount = CONFIG_RESPONSE_REPEAT_COUNT == 0 ? 1 : CONFIG_RESPONSE_REPEAT_COUNT;
        for (uint8_t attempt = 0; attempt < repeatCount; ++attempt) {
            if (attempt > 0) {
                delay(CONFIG_RESPONSE_REPEAT_GAP_MS);
            }
            transmitMeshFrame(response, encoded.size, "gateway-config-response");
            logPrintf("GW_CONFIG_RESPONSE_TX requester=0x%04X parent=0x0000 depth=0 battMv=65535 routeToRoot=1 seq=%u attempt=%u/%u gwRxRssi=%d gwRxSnr=%d\n",
                      requesterId,
                      decoded.seq,
                      static_cast<unsigned>(attempt + 1),
                      static_cast<unsigned>(repeatCount),
                      static_cast<int>(static_cast<int8_t>(payload[8])),
                      static_cast<int>(static_cast<int8_t>(payload[9])));
        }
    } else {
        logPrintf("GW_CONFIG_RESPONSE_BUILD_FAIL requester=0x%04X status=%u\n",
                  requesterId, static_cast<unsigned>(encoded.status));
    }
}

void receiveMeshOnce() {
    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const int16_t state = meshRadio->receive(frame, sizeof(frame));
    if (state == RADIOLIB_ERR_RX_TIMEOUT) {
        return;
    }
    const size_t packetLen = meshRadio->getPacketLength();
    const float rxRssiDbm = meshRadio->getRSSI();
    const float rxSnrDb = meshRadio->getSNR();
    logPrintf("GW_MESH_RX state=%d len=%u rssi=%.2f snr=%.2f\n",
              state,
              static_cast<unsigned>(packetLen),
              rxRssiDbm,
              rxSnrDb);
    if (state != RADIOLIB_ERR_NONE) {
        return;
    }
    pgl::protocol::FrameView addressedFrame{};
    const pgl::protocol::FrameStatus addressedStatus =
        pgl::protocol::decodeAppFrame(frame, packetLen, addressedFrame,
                                      pgl::protocol::MESH_MAX_PAYLOAD);
    if (addressedStatus == pgl::protocol::FrameStatus::Ok &&
        pgl::config::isProvisionableGatewayId(addressedFrame.dstId) &&
        addressedFrame.dstId != gatewayId) {
        logPrintf("GW_MESH_RX_DROP reason=gateway-destination-mismatch src=0x%04X dst=0x%04X local=0x%04X msgType=0x%02X\n",
                  addressedFrame.srcId, addressedFrame.dstId, gatewayId,
                  pgl::protocol::messageType(addressedFrame.typeFlags));
        return;
    }
    sendHelloAckIfNeeded(frame, packetLen);
    const bool duplicateHello = suppressDuplicateHello(frame, packetLen);
    PublishDisposition uplinkDisposition = PublishDisposition::Rejected;
    if (duplicateHello) {
        logPrintf("GW_HELLO_DUPLICATE len=%u publishSkipped=1\n",
                  static_cast<unsigned>(packetLen));
    } else {
        uplinkDisposition = publishMeshFrame(frame, packetLen, rxRssiDbm, rxSnrDb);
    }
    sendGatewayConfigResponseIfNeeded(frame, packetLen, rxRssiDbm, rxSnrDb);
    sendGatewayAckIfNeeded(frame, packetLen, uplinkDisposition);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina Gateway MQTT MESH runtime");
    logPrintf("Firmware name: %s\n", pgl::firmware::GATEWAY_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GATEWAY_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("GW_IDS gateway=0x%04X source=%s\n", gatewayId,
              gatewayIdentityLoadedFromNvs ? "nvs" : "build-default");
    logPrintf("GW_MESH_CONFIG freq=%.1f bw=%.1f sf=%u cr=%u sync=0x%02X\n",
              MESH_FREQ_MHZ,
              MESH_BW_KHZ,
              MESH_SF,
              MESH_CR,
              MESH_SYNC_WORD);
}

// Network provisioning is deliberately staged: WiFi is saved and verified
// first, then MQTT is enabled with a separate command. The legacy combined
// fields remain accepted by SET_WIFI_CONFIG_JSON for older operator builds.
void handleSetWifiConfigJson(const char* payload) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload)) {
        logPrintln("GW_CMD_ACK cmd=SET_WIFI_CONFIG status=error message=invalid_json reboot=0");
        return;
    }
    const char* ssid = doc["ssid"] | netConfig.wifiSsid;
    const char* password = doc["password"] | netConfig.wifiPassword;
    const bool reboot = doc["reboot"] | true;

    if (strlen(ssid) == 0) {
        logPrintln("GW_CMD_ACK cmd=SET_WIFI_CONFIG status=rejected message=ssid_required reboot=0");
        return;
    }

    copyBounded(netConfig.wifiSsid, sizeof(netConfig.wifiSsid), ssid);
    copyBounded(netConfig.wifiPassword, sizeof(netConfig.wifiPassword), password);
    netConfig.mqttEnabled = false;

    // Backward compatibility for the previous combined payload. New clients
    // omit these fields and must use SET_MQTT_CONFIG_JSON after TEST_WIFI.
    if (doc.containsKey("mqttHost")) {
        const char* mqttHost = doc["mqttHost"] | "";
        const uint16_t mqttPort = doc["mqttPort"] | netConfig.mqttPort;
        if (strlen(mqttHost) == 0 || mqttPort == 0) {
            logPrintln("GW_CMD_ACK cmd=SET_WIFI_CONFIG status=rejected message=mqttHost_mqttPort_required reboot=0");
            return;
        }
        copyBounded(netConfig.mqttHost, sizeof(netConfig.mqttHost), mqttHost);
        netConfig.mqttPort = mqttPort;
        copyBounded(netConfig.mqttUser, sizeof(netConfig.mqttUser), doc["mqttUser"] | "");
        copyBounded(netConfig.mqttPassword, sizeof(netConfig.mqttPassword), doc["mqttPass"] | "");
        netConfig.mqttEnabled = true;
    }

    if (!saveNetConfig()) {
        logPrintln("GW_CMD_ACK cmd=SET_WIFI_CONFIG status=error message=nvs_save_failed reboot=0");
        return;
    }
    logPrintf("GW_CMD_ACK cmd=SET_WIFI_CONFIG status=ok message=saved reboot=%u\n", reboot ? 1 : 0);
    if (reboot) {
        Serial.flush();
        delay(200);
        ESP.restart();
    }
}

void handleTestWifi() {
    const bool connected = WiFi.status() == WL_CONNECTED;
    const String ip = connected ? WiFi.localIP().toString() : String("");
    logPrintf("GW_CMD_ACK cmd=TEST_WIFI status=%s connected=%u ip=%s\n",
              connected ? "ok" : "error",
              connected ? 1 : 0,
              connected ? ip.c_str() : "none");
}

void handleTestMqtt() {
    const bool connected = mqtt.connected();
    logPrintf("GW_CMD_ACK cmd=TEST_MQTT status=%s connected=%u state=%d host=%s port=%u auth=%u subscriptions=%u\n",
              connected ? "ok" : "error",
              connected ? 1 : 0,
              mqtt.state(),
              netConfig.mqttHost,
              netConfig.mqttPort,
              (netConfig.mqttUser[0] != '\0' || netConfig.mqttPassword[0] != '\0') ? 1 : 0,
              (connected && mqttSubCommands && mqttSubPull && mqttSubNodeCommand) ? 1 : 0);
}

void handleSetMqttConfigJson(const char* payload) {
    StaticJsonDocument<384> doc;
    if (deserializeJson(doc, payload)) {
        logPrintln("GW_CMD_ACK cmd=SET_MQTT_CONFIG status=error message=invalid_json");
        return;
    }
    const char* host = doc["host"] | "";
    const uint16_t port = doc["port"] | 0;
    if (strlen(host) == 0 || port == 0) {
        logPrintln("GW_CMD_ACK cmd=SET_MQTT_CONFIG status=rejected message=host_port_required");
        return;
    }

    copyBounded(netConfig.mqttHost, sizeof(netConfig.mqttHost), host);
    netConfig.mqttPort = port;
    copyBounded(netConfig.mqttUser, sizeof(netConfig.mqttUser), doc["username"] | "");
    copyBounded(netConfig.mqttPassword, sizeof(netConfig.mqttPassword), doc["password"] | "");
    netConfig.mqttEnabled = true;
    if (!saveNetConfig()) {
        logPrintln("GW_CMD_ACK cmd=SET_MQTT_CONFIG status=error message=nvs_save_failed");
        return;
    }

    mqtt.disconnect();
    beginMqtt();
    lastMqttAttemptMs = millis() - MQTT_RETRY_MS;
    logPrintln("GW_CMD_ACK cmd=SET_MQTT_CONFIG status=ok message=saved_connecting=1");
}

void handleSetMeshLoraJson(const char* payload) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, payload)) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=invalid_json");
        return;
    }
    const char* required[] = {"freqMHz", "bwKHz", "sf", "cr", "syncWord", "txPowerDbm"};
    for (const char* key : required) {
        if (!doc.containsKey(key) || !doc[key].is<double>()) {
            logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=missing_required_field");
            return;
        }
    }

    const double freq = doc["freqMHz"].as<double>();
    const double bw = doc["bwKHz"].as<double>();
    const double sf = doc["sf"].as<double>();
    const double cr = doc["cr"].as<double>();
    const double sync = doc["syncWord"].as<double>();
    const double tx = doc["txPowerDbm"].as<double>();
    if (!(freq >= 900.0 && freq <= 930.0)) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=freqMHz-out-of-range-900-930");
        return;
    }
    if (!isSupportedMeshBandwidth(static_cast<float>(bw))) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=bwKHz-unsupported");
        return;
    }
    if (!(sf >= 5.0 && sf <= 12.0 && sf == static_cast<uint8_t>(sf))) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=sf-out-of-range-5-12");
        return;
    }
    if (!(cr >= 5.0 && cr <= 8.0 && cr == static_cast<uint8_t>(cr))) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=cr-out-of-range-5-8");
        return;
    }
    if (!(sync >= 0.0 && sync <= 255.0 && sync == static_cast<uint8_t>(sync))) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=syncWord-out-of-range-0-255");
        return;
    }
    if (!(tx >= -9.0 && tx <= 22.0 && tx == static_cast<int8_t>(tx))) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=txPowerDbm-out-of-range-minus9-22");
        return;
    }

    const RuntimeMeshConfig cfg{
        static_cast<float>(freq), static_cast<float>(bw), static_cast<uint8_t>(sf),
        static_cast<uint8_t>(cr), static_cast<uint8_t>(sync), static_cast<int8_t>(tx),
    };
    if (!saveMeshConfig(cfg)) {
        logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=error message=nvs-write-or-readback-failed");
        return;
    }
    logPrintln("GW_CMD_ACK cmd=SET_MESH_LORA_JSON status=ok message=saved-verified-restarting");
    Serial.flush();
    delay(250);
    ESP.restart();
}

void emitMeshLoraJson() {
    logPrintf("GW_MESH_LORA_JSON {\"freqMHz\":%.3f,\"bwKHz\":%.2f,\"sf\":%u,\"cr\":%u,\"syncWord\":%u,\"txPowerDbm\":%d}\n",
              MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR,
              MESH_SYNC_WORD, MESH_TX_POWER_DBM);
}

void emitGatewayAddressJson() {
    logPrintf("GW_GATEWAY_ADDRESS_JSON {\"gatewayId\":\"0x%04X\",\"min\":\"0x%04X\",\"max\":\"0x%04X\"}\n",
              gatewayId, pgl::config::GATEWAY_ID_MIN, pgl::config::GATEWAY_ID_MAX);
}

void handleSetGatewayAddressJson(const char* payload) {
    StaticJsonDocument<192> doc;
    if (deserializeJson(doc, payload)) {
        logPrintln("GW_CMD_ACK cmd=SET_GATEWAY_ADDRESS_JSON status=error message=invalid_json reboot=0");
        return;
    }

    JsonVariantConst requestedValue = doc["gatewayId"];
    if (requestedValue.isNull()) requestedValue = doc["address"];
    if (requestedValue.isNull()) requestedValue = doc["id"];
    uint16_t requestedGatewayId = 0;
    if (!parseGatewayCommandTarget(requestedValue, requestedGatewayId)) {
        logPrintf("GW_CMD_ACK cmd=SET_GATEWAY_ADDRESS_JSON status=rejected message=gatewayId-range-0x%04X-0x%04X reboot=0\n",
                  pgl::config::GATEWAY_ID_MIN, pgl::config::GATEWAY_ID_MAX);
        return;
    }
    if (requestedGatewayId == gatewayId) {
        logPrintf("GW_CMD_ACK cmd=SET_GATEWAY_ADDRESS_JSON status=ok message=unchanged gatewayId=0x%04X reboot=0\n",
                  gatewayId);
        return;
    }
    if (!saveGatewayIdentity(requestedGatewayId)) {
        logPrintln("GW_CMD_ACK cmd=SET_GATEWAY_ADDRESS_JSON status=error message=nvs-write-or-readback-failed reboot=0");
        return;
    }

    logPrintf("GW_CMD_ACK cmd=SET_GATEWAY_ADDRESS_JSON status=ok message=saved-verified-restarting gatewayId=0x%04X reboot=1\n",
              requestedGatewayId);
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    delay(250);
    ESP.restart();
}

void handleSerialLine(const char* line) {
    constexpr size_t kWifiPrefixLen = sizeof("SET_WIFI_CONFIG_JSON ") - 1;
    constexpr size_t kMqttPrefixLen = sizeof("SET_MQTT_CONFIG_JSON ") - 1;
    constexpr size_t kMeshLoraPrefixLen = sizeof("SET_MESH_LORA_JSON ") - 1;
    constexpr size_t kGatewayAddressPrefixLen = sizeof("SET_GATEWAY_ADDRESS_JSON ") - 1;
    if (strncmp(line, "SET_WIFI_CONFIG_JSON ", kWifiPrefixLen) == 0) {
        handleSetWifiConfigJson(line + kWifiPrefixLen);
    } else if (strcmp(line, "TEST_WIFI") == 0) {
        handleTestWifi();
    } else if (strcmp(line, "TEST_MQTT") == 0) {
        handleTestMqtt();
    } else if (strncmp(line, "SET_MQTT_CONFIG_JSON ", kMqttPrefixLen) == 0) {
        handleSetMqttConfigJson(line + kMqttPrefixLen);
    } else if (strncmp(line, "SET_MESH_LORA_JSON ", kMeshLoraPrefixLen) == 0) {
        handleSetMeshLoraJson(line + kMeshLoraPrefixLen);
    } else if (strcmp(line, "GET_MESH_LORA") == 0) {
        emitMeshLoraJson();
    } else if (strncmp(line, "SET_GATEWAY_ADDRESS_JSON ", kGatewayAddressPrefixLen) == 0) {
        handleSetGatewayAddressJson(line + kGatewayAddressPrefixLen);
    } else if (strcmp(line, "GET_GATEWAY_ADDRESS") == 0) {
        emitGatewayAddressJson();
    }
}

// Read from both streams, like GldCommandParser::readCommandFrom does for
// GLD - on ESP32-S3 boards wired through a CH340, the Operator's COM port is
// UART0 (Serial0), not the native USB-CDC (Serial); other boards may expose
// only one. Trying both means the command lands regardless of which the
// board actually routes to the COM port.
void pollSerialStream(Stream& stream, char* buf, size_t& len) {
    while (stream.available() > 0) {
        const char c = static_cast<char>(stream.read());
        if (c == '\n' || c == '\r') {
            if (len > 0) {
                buf[len] = '\0';
                handleSerialLine(buf);
                len = 0;
            }
            continue;
        }
        if (len + 1 < 600) {
            buf[len++] = c;
        }
    }
}

char usbSerialLineBuf[600];
size_t usbSerialLineLen = 0;
#if defined(ARDUINO_ARCH_ESP32)
char uart0SerialLineBuf[600];
size_t uart0SerialLineLen = 0;
#endif

void pollSerialCommands() {
    pollSerialStream(Serial, usbSerialLineBuf, usbSerialLineLen);
#if defined(ARDUINO_ARCH_ESP32)
    pollSerialStream(Serial0, uart0SerialLineBuf, uart0SerialLineLen);
#endif
}

}  // namespace

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    delay(1000);
    setupPinsSafe();
    loadGatewayIdentity();
    loadNetConfig();
    loadMeshConfig();
    printBootHeader();
    meshReady = beginMeshRadio();
    beginWifi();
    beginMqtt();
}

void loop() {
    pollSerialCommands();
    ensureWifi();
    ensureMqtt();
    mqtt.loop();
    publishStatusPeriodic();
    drainMqttQueue();

    if (meshReady && meshRadio != nullptr) {
        receiveMeshOnce();
    } else {
        delay(250);
    }
}
