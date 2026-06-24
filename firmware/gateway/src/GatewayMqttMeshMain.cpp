#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "AppFrame.h"
#include "FirmwareVersion.h"
#include "GwConfig.h"
#include "GatewayBoardPins.h"
#include "ProtocolConstants.h"

namespace {

constexpr const char* WIFI_SSID = pgl::config::gw::WIFI_SSID;
constexpr const char* WIFI_PASSWORD = pgl::config::gw::WIFI_PASSWORD;
constexpr const char* MQTT_HOST = pgl::config::gw::MQTT_HOST;
constexpr uint16_t MQTT_PORT = pgl::config::gw::MQTT_PORT;
constexpr const char* MQTT_USER = pgl::config::gw::MQTT_USER;
constexpr const char* MQTT_PASSWORD = pgl::config::gw::MQTT_PASSWORD;

constexpr uint16_t GATEWAY_ID = pgl::config::gw::GATEWAY_ID;

constexpr const char* TOPIC_UPLINK = pgl::config::gw::TOPIC_UPLINK;
constexpr const char* TOPIC_STATUS = pgl::config::gw::TOPIC_STATUS;
constexpr const char* TOPIC_TOPOLOGY = pgl::config::gw::TOPIC_TOPOLOGY;
constexpr const char* TOPIC_COMMANDS = pgl::config::gw::TOPIC_COMMANDS;
constexpr const char* TOPIC_PULL = pgl::config::gw::TOPIC_PULL;
constexpr const char* TOPIC_NODE_COMMAND = pgl::config::gw::TOPIC_NODE_COMMAND;

constexpr float MESH_FREQ_MHZ = pgl::config::gw::MESH_FREQ_MHZ;
constexpr float MESH_BW_KHZ = pgl::config::gw::MESH_BW_KHZ;
constexpr uint8_t MESH_SF = pgl::config::gw::MESH_SF;
constexpr uint8_t MESH_CR = pgl::config::gw::MESH_CR;
constexpr uint8_t MESH_SYNC_WORD = pgl::config::gw::MESH_SYNC_WORD;
constexpr int8_t MESH_TX_POWER_DBM = pgl::config::gw::MESH_TX_POWER_DBM;
constexpr uint16_t MESH_PREAMBLE = pgl::config::gw::MESH_PREAMBLE;
constexpr float MESH_TCXO_VOLTAGE = pgl::config::gw::MESH_TCXO_VOLTAGE;
constexpr float MESH_XTAL_TCXO_VOLTAGE = pgl::config::gw::MESH_XTAL_TCXO_VOLTAGE;
constexpr uint32_t MESH_SPI_HZ = pgl::config::gw::MESH_SPI_HZ;
constexpr uint32_t WIFI_RETRY_MS = pgl::config::gw::WIFI_RETRY_MS;
constexpr uint32_t MQTT_RETRY_MS = pgl::config::gw::MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = pgl::config::gw::STATUS_INTERVAL_MS;
constexpr uint8_t CONFIG_RESPONSE_REPEAT_COUNT = pgl::config::gw::CONFIG_RESPONSE_REPEAT_COUNT;
constexpr uint16_t CONFIG_RESPONSE_REPEAT_GAP_MS = pgl::config::gw::CONFIG_RESPONSE_REPEAT_GAP_MS;

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

size_t parseHopList(const JsonDocument& doc, uint16_t* out, size_t outCapacity) {
    if (out == nullptr || outCapacity == 0) {
        return 0;
    }

    JsonVariantConst hopListValue = doc["hopList"];
    if (hopListValue.isNull()) {
        hopListValue = doc["hop_list"];
    }
    if (hopListValue.isNull()) {
        hopListValue = doc["hops"];
    }

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
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiAttemptMs = millis();
    logPrintf("GW_WIFI_CONNECT ssid=%s\n", WIFI_SSID);
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
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    logPrintf("GW_WIFI_RETRY ssid=%s\n", WIFI_SSID);
}

void mqttCallback(char* topic, uint8_t* payload, unsigned int length);

void beginMqtt() {
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    mqtt.setBufferSize(1024);
}

void ensureMqtt() {
    if (WiFi.status() != WL_CONNECTED || mqtt.connected()) {
        return;
    }
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) {
        return;
    }
    lastMqttAttemptMs = now;

    char clientId[48];
    snprintf(clientId, sizeof(clientId), "pgl-gateway-%04X-%08lX", GATEWAY_ID, static_cast<unsigned long>(ESP.getEfuseMac()));
    const bool ok = mqtt.connect(clientId, MQTT_USER, MQTT_PASSWORD);
    logPrintf("GW_MQTT_CONNECT host=%s port=%u ok=%u\n", MQTT_HOST, MQTT_PORT, ok ? 1 : 0);
    if (!ok) {
        return;
    }
    const bool subCommands = mqtt.subscribe(TOPIC_COMMANDS);
    const bool subPull = mqtt.subscribe(TOPIC_PULL);
    const bool subNodeCommand = mqtt.subscribe(TOPIC_NODE_COMMAND);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_COMMANDS, subCommands ? 1 : 0);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_PULL, subPull ? 1 : 0);
    logPrintf("GW_MQTT_SUB topic=%s ok=%u\n", TOPIC_NODE_COMMAND, subNodeCommand ? 1 : 0);
    for (uint8_t i = 0; i < 5; ++i) {
        mqtt.loop();
        delay(10);
    }
}

bool publishStatus(const char* state) {
    StaticJsonDocument<256> doc;
    doc["kind"] = "gateway-status";
    doc["gatewayId"] = GATEWAY_ID;
    doc["state"] = state;
    doc["wifi"] = WiFi.status() == WL_CONNECTED;
    doc["mqtt"] = mqtt.connected();
    doc["meshReady"] = meshReady;
    doc["ip"] = WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "";

    char json[256];
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
        GATEWAY_ID,
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
    uint16_t chId = 0;
    uint16_t nodeId = 0;
    if (!parseRequiredU16(doc["cluster"], chId)) {
        logPrintln("GW_NODE_COMMAND_BUILD_FAIL missingCluster=1");
        return;
    }
    if (!parseRequiredU16(doc["node"], nodeId)) {
        logPrintln("GW_NODE_COMMAND_BUILD_FAIL missingNode=1");
        return;
    }
    const uint16_t commandId = parseU16Value(doc["id"], 1);
    const uint16_t ttlSec = parseU16Value(doc["ttl"], 600);
    uint8_t commandBytes[32]{};
    size_t commandLen = 0;
    hexToBytes(doc["hex"] | "", commandBytes, sizeof(commandBytes), commandLen);
    if (commandLen > 32) {
        commandLen = 32;
    }

    uint8_t payload[2 + 2 + 2 + 1 + 32]{};
    writeU16Be(&payload[0], nodeId);
    writeU16Be(&payload[2], commandId);
    writeU16Be(&payload[4], ttlSec);
    payload[6] = static_cast<uint8_t>(commandLen);
    memcpy(&payload[7], commandBytes, commandLen);

    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_SERVER_NODE_COMMAND,
        GATEWAY_ID,
        chId,
        meshSeq++,
        payload,
        static_cast<uint8_t>(7 + commandLen),
        frame,
        sizeof(frame),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status != pgl::protocol::FrameStatus::Ok) {
        logPrintf("GW_NODE_COMMAND_BUILD_FAIL status=%u\n", static_cast<unsigned>(encoded.status));
        return;
    }
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
        handlePullCommand(doc);
    } else if (strcmp(topic, TOPIC_NODE_COMMAND) == 0 || strstr(topic, "/node") != nullptr) {
        handleNodeCommand(doc);
    }
}

bool publishTopologyReport(const pgl::protocol::FrameView& decoded, float rssi, float snr) {
    const uint8_t msgType = pgl::protocol::messageType(decoded.typeFlags);
    if (decoded.srcId == GATEWAY_ID) {
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
    doc["gatewayId"] = GATEWAY_ID;
    doc["rootId"] = GATEWAY_ID;
    doc["msgType"] = msgType;
    doc["typeFlags"] = decoded.typeFlags;
    doc["srcId"] = decoded.srcId;
    doc["dstId"] = decoded.dstId;
    doc["seq"] = decoded.seq;
    doc["payloadLen"] = decoded.payloadLen;
    doc["rssi"] = rssi;
    doc["snr"] = snr;
    writeHexId(doc, "gatewayIdHex", GATEWAY_ID);
    writeHexId(doc, "rootIdHex", GATEWAY_ID);
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
        doc["parentIsRoot"] = parentId == GATEWAY_ID;
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
        doc["routeToRoot"] = (routeFlags & 0x01) != 0;
        doc["parentIsRoot"] = parentId == GATEWAY_ID;
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
    const bool ok = mqtt.connected() && mqtt.publish(TOPIC_TOPOLOGY, reinterpret_cast<const uint8_t*>(json), len);
    if (parentId != 0) {
        logPrintf("GW_TOPOLOGY_PUBLISH topic=%s report=%s ch=0x%04X parent=0x%04X ok=%u\n",
                  TOPIC_TOPOLOGY, reportType, chId, parentId, ok ? 1 : 0);
    } else {
        logPrintf("GW_TOPOLOGY_PUBLISH topic=%s report=%s ch=0x%04X ok=%u\n",
                  TOPIC_TOPOLOGY, reportType, chId, ok ? 1 : 0);
    }
    return ok;
}

void publishMeshFrame(const uint8_t* frame, size_t frameLen, float rssi, float snr) {
    char frameHex[2 * (pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD) + 1]{};
    bytesToHex(frame, frameLen, frameHex, sizeof(frameHex));

    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);

    StaticJsonDocument<1024> doc;
    doc["source"] = "gateway";
    doc["gatewayId"] = GATEWAY_ID;
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
            topology["parentIsRoot"] = readU16Be(&decoded.payload[2]) == GATEWAY_ID;
            topology["viaHop"] = decoded.srcId;
            topology["gatewayId"] = GATEWAY_ID;
            topology["rssi"] = rssi;
            topology["snr"] = snr;
        }
        publishTopologyReport(decoded, rssi, snr);
    }

    char json[1024];
    const size_t len = serializeJson(doc, json, sizeof(json));
    const bool ok = mqtt.connected() && mqtt.publish(TOPIC_UPLINK, reinterpret_cast<const uint8_t*>(json), len);
    logPrintf("GW_MQTT_PUBLISH topic=%s ok=%u frameLen=%u parseStatus=%u\n",
              TOPIC_UPLINK,
              ok ? 1 : 0,
              static_cast<unsigned>(frameLen),
              static_cast<unsigned>(parseStatus));
}

void sendGatewayAckIfNeeded(const uint8_t* frame, size_t frameLen) {
    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (parseStatus != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_SENSOR_DATA ||
        !pgl::protocol::hasAlarmAckFlag(decoded.typeFlags)) {
        return;
    }

    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::TYPE_ALARM_ACK_COMPACT,
        GATEWAY_ID,
        decoded.srcId,
        decoded.seq,
        nullptr,
        0,
        ack,
        sizeof(ack),
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (encoded.status == pgl::protocol::FrameStatus::Ok) {
        transmitMeshFrame(ack, encoded.size, "gateway-ack");
    }
}

void sendGatewayConfigResponseIfNeeded(const uint8_t* frame, size_t frameLen,
                                       float requestRssiDbm, float requestSnrDb) {
    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus parseStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (parseStatus != pgl::protocol::FrameStatus::Ok ||
        pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_CH_CONFIG_REQUEST ||
        decoded.dstId != 0xFFFF ||
        decoded.srcId == GATEWAY_ID) {
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
    payload[7] = 0x01;    // route-to-root capable
    payload[8] = static_cast<uint8_t>(clampToI8(requestRssiDbm));  // GW hears CH RSSI.
    payload[9] = static_cast<uint8_t>(clampToI8(requestSnrDb));    // GW hears CH SNR.

    uint8_t response[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult encoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_CONFIG_RESPONSE,
        GATEWAY_ID,
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
    publishMeshFrame(frame, packetLen, rxRssiDbm, rxSnrDb);
    sendGatewayConfigResponseIfNeeded(frame, packetLen, rxRssiDbm, rxSnrDb);
    sendGatewayAckIfNeeded(frame, packetLen);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina Gateway MQTT MESH runtime");
    logPrintf("Firmware name: %s\n", pgl::firmware::GATEWAY_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GATEWAY_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("GW_IDS gateway=0x%04X\n", GATEWAY_ID);
    logPrintf("GW_MESH_CONFIG freq=%.1f bw=%.1f sf=%u cr=%u sync=0x%02X\n",
              MESH_FREQ_MHZ,
              MESH_BW_KHZ,
              MESH_SF,
              MESH_CR,
              MESH_SYNC_WORD);
}

}  // namespace

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    delay(1000);
    setupPinsSafe();
    printBootHeader();
    meshReady = beginMeshRadio();
    beginWifi();
    beginMqtt();
}

void loop() {
    ensureWifi();
    ensureMqtt();
    mqtt.loop();
    publishStatusPeriodic();

    if (meshReady && meshRadio != nullptr) {
        receiveMeshOnce();
    } else {
        delay(250);
    }
}
