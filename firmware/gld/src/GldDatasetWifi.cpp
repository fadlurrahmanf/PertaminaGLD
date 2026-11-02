#include "GldDatasetWifi.h"

#if defined(PGL_GLD_DATASET_WIFI) && PGL_GLD_DATASET_WIFI
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
// Make the framework dependency explicit for PlatformIO's library discovery.
#include <WiFiClientSecure.h>
#include <WebSocketsServer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <cstring>
#include "GldDatasetValidator.h"
#include "GldDatasetWifiSecrets.h"

namespace pgl::gld::datasetwifi {
namespace {
constexpr uint32_t INTERVAL_MS = 500;
constexpr size_t QUEUE_CAPACITY = 32;
constexpr size_t JSON_BYTES = 1536;
constexpr const char* PROTOCOL = "gld-dataset-wifi/1";

struct Message {
    char json[JSON_BYTES]{};
    uint32_t connection = 0;
    uint32_t generation = 0;
    bool summary = false;
};
struct Command {
    char cmd[24]{};
    char commandId[65]{};
    char sessionId[65]{};
    char label[32]{};
    uint32_t intervalMs = 0;
    uint32_t connection = 0;
};
struct State {
    char device[17]{};
    char session[65]{};
    char startCommand[65]{};
    char label[32]{};
    char reason[64]{};
    uint8_t profile = 0;
    uint32_t connection = 0;
    uint32_t generation = 0;
    uint32_t total = 0;
    uint32_t overruns = 0;
    uint32_t nextDue = 0;
    int client = -1;
    bool running = false;
    bool incomplete = false;
    bool pendingSummary = false;
    bool completeSummarySent = true;
};
State state;
Ready isReady = nullptr;
Capture captureSample = nullptr;
SemaphoreHandle_t guard = nullptr;
QueueHandle_t outgoing = nullptr;
QueueHandle_t commands = nullptr;
// Installed IDF HTTPD upgrades before its URI handler; this pinned adapter
// checks HTTP Basic credentials before sending 101. Primary API/source:
// https://github.com/Links2004/arduinoWebSockets/tree/2.6.1/src
WebSocketsServer socket(81, "", "gld-dataset-wifi/1");
bool started = false;

struct Lock {
    Lock() { xSemaphoreTake(guard, portMAX_DELAY); }
    ~Lock() { xSemaphoreGive(guard); }
};

template <size_t N>
void copy(char (&target)[N], const char* source) {
    snprintf(target, N, "%s", source != nullptr ? source : "");
}

void featureOrder(JsonDocument& doc) {
    JsonArray order = doc.createNestedArray("feature_order");
    for (const char* feature : GLD_DATASET_CANONICAL_FEATURE_ORDER) order.add(feature);
}

// Called with guard held. A producer never waits for a network consumer.
bool enqueueLocked(const JsonDocument& doc, bool finalSummary = false) {
    if (state.client < 0 || doc.overflowed() || measureJson(doc) >= JSON_BYTES) return false;
    Message message;
    message.connection = state.connection;
    message.generation = state.generation;
    message.summary = finalSummary;
    serializeJson(doc, message.json, sizeof(message.json));
    return xQueueSend(outgoing, &message, 0) == pdTRUE;
}

void stopLocked(const char* reason, bool incomplete) {
    state.running = false;
    state.incomplete = state.incomplete || incomplete;
    state.pendingSummary = state.session[0] != '\0';
    copy(state.reason, reason);
}

void disconnected(int fd) {
    Lock lock;
    if (state.client != fd) return;
    state.client = -1;
    if (state.session[0] && !state.completeSummarySent) stopLocked("disconnected", true);
    xQueueReset(outgoing);
    xQueueReset(commands);
}

void statusLocked() {
    StaticJsonDocument<512> doc;
    doc["type"] = "status";
    doc["session_id"] = state.session;
    doc["state"] = state.running ? "running" : state.incomplete ? "error" : "idle";
    doc["reason"] = state.reason;
    doc["total_samples"] = state.total;
    doc["incomplete"] = state.incomplete;
    doc["overrun_count"] = state.overruns;
    enqueueLocked(doc);
}

bool ackLocked(const Command& command, bool ok, const char* detail) {
    StaticJsonDocument<512> doc;
    doc["type"] = "ack";
    doc["cmd"] = command.cmd;
    doc["command_id"] = command.commandId;
    doc["session_id"] = command.sessionId;
    doc["result"] = ok ? "ok" : "error";
    doc["detail"] = detail;
    return enqueueLocked(doc);
}

bool field(const JsonDocument& doc, const char* name, char* out, size_t capacity) {
    if (!doc[name].is<const char*>()) return false;
    const char* value = doc[name].as<const char*>();
    if (value[0] == '\0' || strlen(value) >= capacity) return false;
    for (const char* cursor = value; *cursor; ++cursor) {
        if (static_cast<unsigned char>(*cursor) < 0x20) return false;
    }
    snprintf(out, capacity, "%s", value);
    return true;
}

void websocket(uint8_t client, WStype_t type, uint8_t* payload, size_t length) {
    if (type == WStype_DISCONNECTED) {
        disconnected(client);
        return;
    }
    if (type == WStype_CONNECTED) {
        // Basic authentication has already passed in the library handshake.
        if (length != strlen("/dataset") || memcmp(payload, "/dataset", length) != 0) {
            socket.disconnect(client);
            return;
        }
        bool accepted = false;
        {
            Lock lock;
            if (state.client < 0) {
                state.client = client;
                ++state.connection;
                StaticJsonDocument<768> hello;
                hello["type"] = "hello";
                hello["protocol"] = PROTOCOL;
                hello["device_id"] = state.device;
                hello["interval_ms"] = INTERVAL_MS;
                const bool ready = isReady != nullptr && isReady();
                hello["ready"] = ready;
                hello["reason"] = ready ? "ready" : "requires_24v_and_saved_valid_nulling_profile";
                featureOrder(hello);
                accepted = enqueueLocked(hello);
            }
        }
        if (!accepted) socket.disconnect(client);
        return;
    }
    if (type != WStype_TEXT) return;
    if (length == 0 || length > 512) {
        socket.disconnect(client);
        return;
    }
    StaticJsonDocument<768> doc;
    if (deserializeJson(doc, payload, length)) {
        socket.disconnect(client);
        return;
    }
    Command command;
    if (!field(doc, "cmd", command.cmd, sizeof(command.cmd)) ||
        !field(doc, "command_id", command.commandId, sizeof(command.commandId)) ||
        !field(doc, "session_id", command.sessionId, sizeof(command.sessionId))) {
        socket.disconnect(client);
        return;
    }
    if (strcmp(command.cmd, "START_DATASET") == 0) {
        if (!field(doc, "label", command.label, sizeof(command.label)) ||
            !doc["sample_interval_ms"].is<uint32_t>()) {
            socket.disconnect(client);
            return;
        }
        command.intervalMs = doc["sample_interval_ms"].as<uint32_t>();
    }
    bool accepted;
    {
        Lock lock;
        if (state.client != client) return;
        command.connection = state.connection;
        accepted = xQueueSend(commands, &command, 0) == pdTRUE;
    }
    if (!accepted) socket.disconnect(client);
}

void transmitter(void*) {
    Message sending;
    for (;;) {
        // All library/socket operations belong to this task. A slow peer may
        // block it; the sampler keeps its schedule and stops on queue overflow.
        socket.loop();
        if (xQueueReceive(outgoing, &sending, 0) == pdTRUE) {
            int client;
            bool current;
            {
                Lock lock;
                client = state.client;
                current = client >= 0 && sending.connection == state.connection;
            }
            if (current) {
                const bool ok = socket.sendTXT(static_cast<uint8_t>(client), sending.json);
                if (!ok) {
                    disconnected(client);
                    socket.disconnect(static_cast<uint8_t>(client));
                } else if (sending.summary) {
                    Lock lock;
                    if (state.connection == sending.connection && state.generation == sending.generation) {
                        state.completeSummarySent = true;
                    }
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }
}

void sampler(void*) {
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(5));
        uint32_t generation;
        {
            Lock lock;
            if (!state.running || static_cast<int32_t>(millis() - state.nextDue) < 0) continue;
            generation = state.generation;
            state.nextDue += INTERVAL_MS;
        }
        Sample sample;
        sample.timestampMs = millis();
        const bool valid = isReady != nullptr && isReady() && captureSample(sample);
        sample.scanEndMs = millis();
        Lock lock;
        if (!state.running || state.generation != generation) continue;
        if (!valid) {
            stopLocked("invalid_sample_or_power", true);
            continue;
        }
        // Skip missed deadlines explicitly, without catching up with burst scans.
        if (static_cast<int32_t>(sample.scanEndMs - state.nextDue) >= 0) {
            const uint32_t missed = (sample.scanEndMs - state.nextDue) / INTERVAL_MS + 1;
            state.overruns += missed;
            state.nextDue += missed * INTERVAL_MS;
        }
        StaticJsonDocument<1536> doc;
        doc["type"] = "sample";
        doc["device_id"] = state.device;
        doc["session_id"] = state.session;
        doc["seq"] = state.total++;
        doc["timestamp_ms"] = sample.timestampMs;
        doc["scan_end_ms"] = sample.scanEndMs;
        doc["mode"] = "DATASET";
        doc["label"] = state.label;
        doc["nulling_profile_id"] = state.profile;
        doc["overrun_count"] = state.overruns;
        JsonArray voltage = doc.createNestedArray("sensor_voltage");
        JsonArray gain = doc.createNestedArray("sensor_gain");
        JsonArray status = doc.createNestedArray("sensor_status");
        for (size_t i = 0; i < GLD_DATASET_FEATURE_COUNT; ++i) {
            voltage.add(sample.voltage[i]);
            gain.add(sample.gain[i]);
            status.add(sample.status[i]);
        }
        featureOrder(doc);
        if (!enqueueLocked(doc)) stopLocked("outbound_queue_full", true);
    }
}

void process(const Command& command) {
    Lock lock;
    if (command.connection != state.connection || state.client < 0) return;
    if (strcmp(command.cmd, "START_DATASET") == 0) {
        if (state.running && strcmp(state.session, command.sessionId) == 0 &&
            strcmp(state.startCommand, command.commandId) == 0) {
            ackLocked(command, true, "already_running");
            statusLocked();
            return;
        }
        if (state.running || state.pendingSummary || !state.completeSummarySent) {
            ackLocked(command, false, "session_active_or_summary_pending");
        } else if (command.intervalMs != INTERVAL_MS) {
            ackLocked(command, false, "sample_interval_ms_must_equal_500");
        } else if (isReady == nullptr || !isReady()) {
            ackLocked(command, false, "requires_24v_and_saved_valid_nulling_profile");
        } else if (uxQueueSpacesAvailable(outgoing) < 3) {
            ackLocked(command, false, "transport_busy");
        } else {
            copy(state.session, command.sessionId);
            copy(state.startCommand, command.commandId);
            copy(state.label, command.label);
            state.total = 0;
            state.overruns = 0;
            state.incomplete = false;
            state.completeSummarySent = false;
            copy(state.reason, "started");
            ++state.generation;
            // FIFO ACK + running status precede every sample of this session.
            if (!ackLocked(command, true, "started")) {
                stopLocked("ack_queue_full", true);
                return;
            }
            state.running = true;
            state.nextDue = millis() + INTERVAL_MS;
            statusLocked();
        }
    } else if (strcmp(command.cmd, "STOP_DATASET") == 0) {
        if (!state.session[0] || strcmp(command.sessionId, state.session) != 0) {
            ackLocked(command, false, "session_id_mismatch");
        } else {
            stopLocked("operator_stop", false);
            if (!ackLocked(command, true, "stopped")) state.incomplete = true;
        }
    } else {
        ackLocked(command, false, "unknown_command");
    }
}
}  // namespace

bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture) {
    if (started || ready == nullptr || capture == nullptr) return false;
    copy(state.device, deviceId);
    state.profile = nullingProfileId;
    isReady = ready;
    captureSample = capture;
    guard = xSemaphoreCreateMutex();
    outgoing = xQueueCreate(QUEUE_CAPACITY, sizeof(Message));
    commands = xQueueCreate(4, sizeof(Command));
    if (!guard || !outgoing || !commands) return false;
    const char* password = GLD_DATASET_WIFI_PRIVATE_PASSWORD;
    char ssid[33]{};
    snprintf(ssid, sizeof(ssid), "GLD-DATASET-%s", state.device);
    const IPAddress address(192, 168, 4, 1);
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAPConfig(address, address, IPAddress(255, 255, 255, 0)) ||
        !WiFi.softAP(ssid, password, 1, false, 1)) return false;
    socket.setAuthorization("gld", password);
    socket.onEvent(websocket);
    socket.enableHeartbeat(5000, 2000, 1);
    socket.begin();
    // Only the sampler accesses ADS after setup; network never calls capture.
    if (xTaskCreate(sampler, "gld_dataset_sample", 6144, nullptr, 2, nullptr) != pdPASS ||
        xTaskCreate(transmitter, "gld_dataset_tx", 8192, nullptr, 1, nullptr) != pdPASS) return false;
    started = true;
    return true;
}

void poll() {
    if (!started || !guard) return;
    Command command;
    while (xQueueReceive(commands, &command, 0) == pdTRUE) process(command);
    Lock lock;
    if (!state.pendingSummary || state.client < 0 || uxQueueSpacesAvailable(outgoing) < 2) return;
    statusLocked();
    StaticJsonDocument<512> doc;
    doc["type"] = "summary";
    doc["session_id"] = state.session;
    doc["total_samples"] = state.total;
    doc["reason"] = state.reason;
    doc["incomplete"] = state.incomplete;
    doc["overrun_count"] = state.overruns;
    if (enqueueLocked(doc, true)) state.pendingSummary = false;
}
}  // namespace pgl::gld::datasetwifi
#endif
