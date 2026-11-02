#include "GldDatasetReplayWifi.h"

#if defined(PGL_GLD_DATASET_REPLAY) && PGL_GLD_DATASET_REPLAY
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WebSocketsServer.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <cstring>
#include <atomic>
#include "GldDatasetReplayBuffer.h"
#include "GldDatasetValidator.h"
#include "GldDatasetReplayWifiSecrets.h"

namespace pgl::gld::datasetreplaywifi {
namespace {
constexpr uint32_t INTERVAL_MS = 500;
constexpr size_t CONTROL_CAPACITY = 8;
constexpr size_t JSON_BYTES = 1536;
constexpr const char* PROTOCOL = "gld-dataset-wifi/2";

struct ControlMessage {
    char json[JSON_BYTES]{};
    uint32_t connection = 0;
    uint32_t generation = 0;
    bool summary = false;
};
struct Command {
    char cmd[24]{};
    char commandId[65]{};
    char sessionId[65]{};
    char bootId[33]{};
    char label[32]{};
    uint32_t intervalMs = 0;
    uint32_t nextSequence = 0;
    uint32_t connection = 0;
};
struct State {
    char device[17]{};
    char boot[33]{};
    char session[65]{};
    char startCommand[65]{};
    char stopCommand[65]{};
    char label[32]{};
    char reason[64]{};
    uint8_t profile = 0;
    uint32_t connection = 0;
    uint32_t generation = 0;
    uint32_t nextDue = 0;
    uint32_t overruns = 0;
    uint32_t offerNext = 0;
    uint32_t offeredNext = 0;
    uint32_t lastStatusMs = 0;
    int client = -1;
    bool sampling = false;
    bool incomplete = false;
    bool streamEnabled = false;
    bool summaryPending = false;
    bool summarySent = true;
    bool closeRequested = false;
};

// WebSocketsServer.begin() is void. Inspect the framework listener instead of
// treating an advertised AP as proof that bind/listen succeeded.
class CheckedServer : public WebSocketsServer {
public:
    CheckedServer() : WebSocketsServer(81, "", PROTOCOL) {}
    bool beginChecked() {
        if (_server == nullptr) return false;
        WebSocketsServer::begin();
        return static_cast<bool>(*_server);
    }
    void closeChecked() { if (_server != nullptr) WebSocketsServer::close(); }
};

State state;
ReplayBuffer retained;
AckProgressClock ackClock;
Ready isReady = nullptr;
Capture captureSample = nullptr;
SemaphoreHandle_t guard = nullptr;
QueueHandle_t controls = nullptr;
QueueHandle_t commands = nullptr;
TaskHandle_t samplerHandle = nullptr;
TaskHandle_t transportHandle = nullptr;
CheckedServer socket;
std::atomic<bool> initialized{false};

struct Lock {
    Lock() { xSemaphoreTake(guard, portMAX_DELAY); }
    ~Lock() { xSemaphoreGive(guard); }
};
template <size_t N> void copy(char (&target)[N], const char* value) {
    snprintf(target, N, "%s", value != nullptr ? value : "");
}

const char* stateName() {
    return state.sampling ? "running" : state.incomplete ? "error" : "stopped";
}

void featureOrder(JsonDocument& doc) {
    JsonArray order = doc.createNestedArray("feature_order");
    for (const char* feature : GLD_DATASET_CANONICAL_FEATURE_ORDER) order.add(feature);
}

void sessionFields(JsonDocument& doc) {
    doc["device_id"] = state.device;
    doc["boot_id"] = state.boot;
    doc["session_id"] = state.session;
    doc["label"] = state.label;
    doc["nulling_profile_id"] = state.profile;
    doc["sampling"] = state.sampling;
    doc["incomplete"] = state.incomplete;
    doc["reason"] = state.reason;
    doc["total_samples"] = retained.nextSequence();
    doc["oldest_seq"] = retained.oldestSequence();
    doc["acked_next_seq"] = retained.acknowledgedNext();
    doc["buffered_samples"] = retained.size();
    doc["overrun_count"] = state.overruns;
}

void stopLocked(const char* reason, bool incomplete) {
    // Retention/overflow/quality failure is sticky. A later operator Stop can
    // acknowledge the stopped state but cannot certify a terminal failure.
    if (!state.incomplete) copy(state.reason, reason);
    state.incomplete = state.incomplete || incomplete;
    state.sampling = false;
    state.summaryPending = state.session[0] != '\0';
    state.summarySent = false;
}

void checkLimitLocked(uint32_t now) {
    if (state.sampling && ackClock.expired(now)) stopLocked("retention_limit", true);
    if (state.sampling && retained.full()) stopLocked("buffer_full", true);
}

void requestCloseLocked() {
    state.closeRequested = true;
    state.streamEnabled = false;
    if (state.sampling) ackClock.arm(millis());
}

bool enqueueLocked(const JsonDocument& doc, bool summary = false) {
    if (state.client < 0 || doc.overflowed() || measureJson(doc) >= JSON_BYTES) return false;
    ControlMessage message;
    message.connection = state.connection;
    message.generation = state.generation;
    message.summary = summary;
    serializeJson(doc, message.json, sizeof(message.json));
    return xQueueSend(controls, &message, 0) == pdTRUE;
}

bool statusLocked() {
    StaticJsonDocument<1024> doc;
    doc["type"] = "status";
    doc["state"] = stateName();
    sessionFields(doc);
    state.lastStatusMs = millis();
    return enqueueLocked(doc);
}

bool ackLocked(const Command& command, bool ok, const char* detail) {
    StaticJsonDocument<768> doc;
    doc["type"] = "ack";
    doc["cmd"] = command.cmd;
    doc["command_id"] = command.commandId;
    doc["session_id"] = command.sessionId;
    doc["boot_id"] = state.boot;
    doc["result"] = ok ? "ok" : "error";
    doc["detail"] = detail;
    if (!enqueueLocked(doc)) { requestCloseLocked(); return false; }
    return true;
}

void disconnected(int client) {
    Lock lock;
    if (state.client != client) return;
    checkLimitLocked(millis());
    state.client = -1;
    state.streamEnabled = false;
    state.offerNext = state.offeredNext = retained.acknowledgedNext();
    if (state.sampling) ackClock.arm(millis());
    if (state.session[0] && !state.sampling) state.summaryPending = true;
    // Only disposable control messages are cleared, never retained samples.
    xQueueReset(controls);
    xQueueReset(commands);
}

bool field(const JsonDocument& doc, const char* name, char* target, size_t capacity) {
    if (!doc[name].is<const char*>()) return false;
    const char* value = doc[name].as<const char*>();
    if (!value[0] || strlen(value) >= capacity) return false;
    for (const char* cursor = value; *cursor; ++cursor) {
        if (static_cast<unsigned char>(*cursor) < 0x20) return false;
    }
    snprintf(target, capacity, "%s", value);
    return true;
}

// This path bypasses the short command queue so a replay burst's ACKs cannot
// displace a Stop/Resume. No socket send or sample acquisition belongs here.
bool acknowledgeLocked(const Command& command) {
    checkLimitLocked(millis());
    if (strcmp(command.bootId, state.boot) || strcmp(command.sessionId, state.session) ||
        !state.session[0] || command.nextSequence > retained.nextSequence()) return false;
    if (command.nextSequence <= retained.acknowledgedNext()) return true;
    if (!state.streamEnabled || command.nextSequence > state.offeredNext) return false;
    if (!retained.acknowledgePrefix(command.nextSequence)) return false;
    ackClock.progress(millis(), retained.size() != 0);
    if (!state.sampling && retained.size() == 0 && !state.summarySent) state.summaryPending = true;
    return true;
}

void websocket(uint8_t client, WStype_t type, uint8_t* payload, size_t length) {
    if (type == WStype_DISCONNECTED) { disconnected(client); return; }
    if (type == WStype_CONNECTED) {
        if (length != strlen("/dataset") || memcmp(payload, "/dataset", length)) {
            socket.disconnect(client); return;
        }
        bool accepted = false;
        {
            Lock lock;
            checkLimitLocked(millis());
            if (state.client < 0) {
                state.client = client;
                ++state.connection;
                state.streamEnabled = false;  // Resume or Start must reconcile first.
                state.offerNext = state.offeredNext = retained.acknowledgedNext();
                if (state.session[0] && !state.sampling) state.summaryPending = true;
                StaticJsonDocument<1536> hello;
                hello["type"] = "hello";
                hello["protocol"] = PROTOCOL;
                hello["interval_ms"] = INTERVAL_MS;
                hello["retention_ms"] = REPLAY_RETENTION_MS;
                hello["capacity"] = REPLAY_CAPACITY;
                const bool ready = isReady != nullptr && isReady();
                hello["ready"] = ready;
                sessionFields(hello);
                if (!state.reason[0]) hello["reason"] = ready ? "ready" : "requires_24v_and_saved_valid_nulling_profile";
                featureOrder(hello);
                accepted = enqueueLocked(hello);
            }
        }
        if (!accepted) socket.disconnect(client);
        return;
    }
    if (type != WStype_TEXT) return;
    if (length == 0 || length > 512) { socket.disconnect(client); return; }
    StaticJsonDocument<1024> doc;
    if (deserializeJson(doc, payload, length)) { socket.disconnect(client); return; }
    Command command;
    if (!field(doc, "cmd", command.cmd, sizeof(command.cmd)) ||
        !field(doc, "session_id", command.sessionId, sizeof(command.sessionId))) {
        socket.disconnect(client); return;
    }
    const bool ack = strcmp(command.cmd, "ACK_SAMPLES") == 0;
    const bool resume = strcmp(command.cmd, "RESUME_DATASET") == 0;
    if (ack || resume) {
        if (!field(doc, "boot_id", command.bootId, sizeof(command.bootId)) ||
            !doc["next_seq"].is<uint32_t>()) { socket.disconnect(client); return; }
        command.nextSequence = doc["next_seq"].as<uint32_t>();
    }
    if (ack) {
        bool accepted;
        { Lock lock; accepted = state.client == client && acknowledgeLocked(command); }
        if (!accepted) socket.disconnect(client);
        return;
    }
    if (!field(doc, "command_id", command.commandId, sizeof(command.commandId))) {
        socket.disconnect(client); return;
    }
    if (resume || strcmp(command.cmd, "START_DATASET") == 0) {
        if (!field(doc, "label", command.label, sizeof(command.label))) {
            socket.disconnect(client); return;
        }
    }
    if (strcmp(command.cmd, "START_DATASET") == 0) {
        if (!doc["sample_interval_ms"].is<uint32_t>()) { socket.disconnect(client); return; }
        command.intervalMs = doc["sample_interval_ms"].as<uint32_t>();
    }
    bool accepted;
    {
        Lock lock;
        if (state.client != client) return;
        command.connection = state.connection;
        if (resume) state.streamEnabled = false;
        accepted = xQueueSend(commands, &command, 0) == pdTRUE;
    }
    if (!accepted) socket.disconnect(client);
}

void process(const Command& command) {
    Lock lock;
    if (command.connection != state.connection || state.client < 0) return;
    checkLimitLocked(millis());  // At exactly 300 s, Resume cannot undo the stop.
    if (strcmp(command.cmd, "START_DATASET") == 0) {
        if (state.session[0] && !strcmp(state.session, command.sessionId) &&
            !strcmp(state.startCommand, command.commandId)) {
            const bool identical = !strcmp(state.label, command.label) && command.intervalMs == INTERVAL_MS;
            if (ackLocked(command, identical, identical ? "already_registered" : "idempotency_mismatch")) statusLocked();
            return;
        }
        if (state.sampling || retained.size() || !state.summarySent) {
            ackLocked(command, false, "session_or_retained_data_pending");
        } else if (state.session[0] && !strcmp(state.session, command.sessionId)) {
            ackLocked(command, false, "session_id_reused");
        } else if (command.intervalMs != INTERVAL_MS || isReady == nullptr || !isReady()) {
            ackLocked(command, false, "requires_500ms_24v_and_saved_valid_profile");
        } else if (uxQueueSpacesAvailable(controls) < 2) {
            ackLocked(command, false, "transport_busy");
        } else {
            // The only buffer reset belongs to a genuinely new, admitted Start.
            retained.clear();
            ackClock.clear();
            copy(state.session, command.sessionId);
            copy(state.startCommand, command.commandId);
            state.stopCommand[0] = '\0';
            copy(state.label, command.label);
            copy(state.reason, "started");
            ++state.generation;
            state.overruns = 0;
            state.incomplete = false;
            state.summaryPending = false;
            state.summarySent = false;
            state.offerNext = state.offeredNext = 0;
            if (!ackLocked(command, true, "started")) { stopLocked("control_queue_full", true); return; }
            state.sampling = true;
            state.nextDue = millis() + INTERVAL_MS;
            if (!statusLocked()) requestCloseLocked();
            state.streamEnabled = !state.closeRequested;
        }
    } else if (strcmp(command.cmd, "RESUME_DATASET") == 0) {
        if (!state.session[0] || strcmp(command.bootId, state.boot) ||
            strcmp(command.sessionId, state.session) || strcmp(command.label, state.label)) {
            ackLocked(command, false, "resume_identity_mismatch");
        } else if (!retained.prefixAvailable(command.nextSequence)) {
            ackLocked(command, false, "resume_prefix_unavailable_or_rollback");
        } else if (uxQueueSpacesAvailable(controls) < 2) {
            ackLocked(command, false, "transport_busy");
        } else {
            const bool advanced = command.nextSequence > retained.acknowledgedNext();
            retained.acknowledgePrefix(command.nextSequence);
            if (advanced || retained.size() == 0) ackClock.progress(millis(), retained.size() != 0);
            state.offerNext = state.offeredNext = command.nextSequence;
            if (!state.sampling) state.summaryPending = true;
            if (!ackLocked(command, true, "resumed")) return;
            if (!statusLocked()) requestCloseLocked();
            state.streamEnabled = !state.closeRequested;
        }
    } else if (strcmp(command.cmd, "STOP_DATASET") == 0) {
        if (!state.session[0] || strcmp(command.sessionId, state.session)) {
            ackLocked(command, false, "session_id_mismatch");
        } else if (state.stopCommand[0] && strcmp(command.commandId, state.stopCommand)) {
            ackLocked(command, false, "stop_already_registered");
        } else {
            const bool duplicate = state.stopCommand[0] != '\0';
            if (!duplicate) {
                copy(state.stopCommand, command.commandId);
                if (state.sampling) stopLocked("operator_stop", false);
            }
            if (ackLocked(command, true, "stopped")) statusLocked();
            if (!state.sampling && !state.summarySent) state.summaryPending = true;
        }
    } else {
        ackLocked(command, false, "unknown_command");
    }
}

void sampler(void*) {
    while (!initialized) vTaskDelay(pdMS_TO_TICKS(5));
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(5));
        uint32_t generation;
        {
            Lock lock;
            checkLimitLocked(millis());
            if (!state.sampling || static_cast<int32_t>(millis() - state.nextDue) < 0) continue;
            generation = state.generation;
            state.nextDue += INTERVAL_MS;
        }
        Sample sample;
        sample.timestampMs = millis();
        const bool valid = isReady != nullptr && isReady() && captureSample(sample);
        sample.scanEndMs = millis();
        Lock lock;
        checkLimitLocked(sample.scanEndMs);
        if (!state.sampling || generation != state.generation) continue;
        if (!valid) { stopLocked("invalid_sample_or_power", true); continue; }
        if (static_cast<int32_t>(sample.scanEndMs - state.nextDue) >= 0) {
            const uint32_t missed = (sample.scanEndMs - state.nextDue) / INTERVAL_MS + 1;
            state.overruns += missed;
            state.nextDue += missed * INTERVAL_MS;
        }
        if (!retained.append(sample, state.overruns)) {
            stopLocked(retained.full() ? "buffer_full" : "sequence_limit", true);
        } else {
            ackClock.arm(sample.scanEndMs);
            checkLimitLocked(sample.scanEndMs);
        }
    }
}

bool sampleMessageLocked(ControlMessage& wire, uint32_t& sequence) {
    if (!state.streamEnabled || state.client < 0 ||
        state.offerNext - retained.acknowledgedNext() >= REPLAY_WINDOW) return false;
    const RetainedSample* record = retained.find(state.offerNext);
    if (record == nullptr) return false;
    sequence = record->sequence;
    StaticJsonDocument<1536> doc;
    doc["type"] = "sample";
    doc["device_id"] = state.device;
    doc["session_id"] = state.session;
    doc["seq"] = record->sequence;
    doc["timestamp_ms"] = record->sample.timestampMs;
    doc["scan_end_ms"] = record->sample.scanEndMs;
    doc["mode"] = "DATASET";
    doc["label"] = state.label;
    doc["nulling_profile_id"] = state.profile;
    doc["overrun_count"] = record->overruns;
    JsonArray voltage = doc.createNestedArray("sensor_voltage");
    JsonArray gain = doc.createNestedArray("sensor_gain");
    JsonArray status = doc.createNestedArray("sensor_status");
    for (size_t i = 0; i < GLD_DATASET_FEATURE_COUNT; ++i) {
        voltage.add(record->sample.voltage[i]);
        gain.add(record->sample.gain[i]);
        status.add(record->sample.status[i]);
    }
    featureOrder(doc);
    if (doc.overflowed() || measureJson(doc) >= JSON_BYTES) {
        stopLocked("payload_encoding", true); requestCloseLocked(); return false;
    }
    wire.connection = state.connection;
    wire.generation = state.generation;
    wire.summary = false;
    serializeJson(doc, wire.json, sizeof(wire.json));
    return true;
}

void transmitter(void*) {
    while (!initialized) vTaskDelay(pdMS_TO_TICKS(5));
    ControlMessage wire;
    for (;;) {
        int closeClient = -1;
        { Lock lock; if (state.closeRequested) { closeClient = state.client; state.closeRequested = false; } }
        if (closeClient >= 0) socket.disconnect(static_cast<uint8_t>(closeClient));
        socket.loop();
        bool sample = false;
        uint32_t sequence = 0;
        bool available = false;
        {
            // One guarded decision preserves control FIFO priority against the
            // poll/sampler tasks. A queued older status must never be overtaken
            // by a sample whose sequence exceeds that status's total_samples.
            Lock lock;
            available = xQueueReceive(controls, &wire, 0) == pdTRUE;
            if (!available) available = sample = sampleMessageLocked(wire, sequence);
        }
        if (available) {
            int client;
            bool current;
            {
                Lock lock;
                client = state.client;
                current = client >= 0 && wire.connection == state.connection && wire.generation == state.generation;
            }
            if (current) {
                const bool ok = socket.sendTXT(static_cast<uint8_t>(client), wire.json);
                if (!ok) {
                    disconnected(client);
                    socket.disconnect(static_cast<uint8_t>(client));
                } else {
                    Lock lock;
                    if (wire.connection == state.connection && wire.generation == state.generation) {
                        if (sample) state.offerNext = state.offeredNext = sequence + 1;
                        if (wire.summary) state.summarySent = true;
                    }
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }
}

void failStartup() {
    if (samplerHandle) { vTaskDelete(samplerHandle); samplerHandle = nullptr; }
    if (transportHandle) { vTaskDelete(transportHandle); transportHandle = nullptr; }
    socket.closeChecked();
    WiFi.softAPdisconnect(true);
    if (controls) { vQueueDelete(controls); controls = nullptr; }
    if (commands) { vQueueDelete(commands); commands = nullptr; }
    if (guard) { vSemaphoreDelete(guard); guard = nullptr; }
}
}  // namespace

bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture) {
    if (initialized || ready == nullptr || capture == nullptr) return false;
    copy(state.device, deviceId);
    state.profile = nullingProfileId;
    isReady = ready;
    captureSample = capture;
    if (!state.boot[0]) {
        uint8_t random[16];
        esp_fill_random(random, sizeof(random));
        for (size_t i = 0; i < sizeof(random); ++i) snprintf(state.boot + i * 2, 3, "%02x", random[i]);
    }
    guard = xSemaphoreCreateMutex();
    controls = xQueueCreate(CONTROL_CAPACITY, sizeof(ControlMessage));
    commands = xQueueCreate(4, sizeof(Command));
    if (!guard || !controls || !commands) { failStartup(); return false; }
    char ssid[33]{};
    snprintf(ssid, sizeof(ssid), "GLD-DATASET-%s", state.device);
    const char* password = GLD_DATASET_REPLAY_PRIVATE_PASSWORD;
    const IPAddress address(192, 168, 4, 1);
    WiFi.persistent(false);
    if (!WiFi.mode(WIFI_AP) ||
        !WiFi.softAPConfig(address, address, IPAddress(255, 255, 255, 0)) ||
        !WiFi.softAP(ssid, password, 1, false, 1)) { failStartup(); return false; }
    socket.setAuthorization("gld", password);
    socket.onEvent(websocket);
    socket.enableHeartbeat(5000, 2000, 1);
    if (!socket.beginChecked()) { failStartup(); return false; }
    if (xTaskCreate(sampler, "gld_replay_sample", 6144, nullptr, 2, &samplerHandle) != pdPASS ||
        xTaskCreate(transmitter, "gld_replay_tx", 8192, nullptr, 1, &transportHandle) != pdPASS) {
        failStartup(); return false;
    }
    initialized = true;
    return true;
}

void poll() {
    if (!initialized || !guard) return;
    Command command;
    while (xQueueReceive(commands, &command, 0) == pdTRUE) process(command);
    Lock lock;
    checkLimitLocked(millis());
    if (state.client < 0 || !state.streamEnabled) return;
    if (!state.sampling && state.summaryPending && retained.size() == 0 &&
        retained.acknowledgedNext() == retained.nextSequence() && uxQueueSpacesAvailable(controls) >= 2) {
        statusLocked();
        StaticJsonDocument<768> doc;
        doc["type"] = "summary";
        doc["boot_id"] = state.boot;
        doc["session_id"] = state.session;
        doc["total_samples"] = retained.nextSequence();
        doc["reason"] = state.reason;
        doc["incomplete"] = state.incomplete;
        doc["overrun_count"] = state.overruns;
        if (enqueueLocked(doc, true)) state.summaryPending = false;
    } else if (state.session[0] && millis() - state.lastStatusMs >= 1000 && uxQueueSpacesAvailable(controls) > 2) {
        statusLocked();
    }
}
}  // namespace pgl::gld::datasetreplaywifi
#endif
