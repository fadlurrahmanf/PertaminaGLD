#include "GldDatasetWorkflowWifi.h"

#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW
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
#include <cmath>
#include "GldDatasetWorkflowBuffer.h"
#include "GldDatasetValidator.h"
#include "GldDatasetWorkflowWifiSecrets.h"

namespace pgl::gld::datasetworkflowwifi {
namespace {
constexpr uint32_t INTERVAL_MS = 500;
constexpr size_t CONTROL_CAPACITY = 8;
constexpr size_t JSON_BYTES = 2304;
constexpr const char* PROTOCOL = "gld-dataset-wifi/3";

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
    uint32_t transitionSequence = 0;
    uint8_t nullingProfile = 0;
    bool predictionEnabled = false;
    bool nativeBusy = false;
};
struct State {
    char device[17]{};
    char boot[33]{};
    char session[65]{};
    char startCommand[65]{};
    char stopCommand[65]{};
    char label[32]{};
    char reason[64]{};
    char transitionCommand[24]{};
    char transitionId[65]{};
    uint8_t profile = 0;
    uint32_t connection = 0;
    uint32_t generation = 0;
    uint32_t nextDue = 0;
    uint32_t overruns = 0;
    uint32_t offerNext = 0;
    uint32_t offeredNext = 0;
    uint32_t lastStatusMs = 0;
    uint32_t acquisitionEpoch = 0;
    uint32_t transitionSequence = 0;
    int client = -1;
    bool sampling = false;
    bool paused = false;
    bool predictionEnabled = false;
    bool incomplete = false;
    bool streamEnabled = false;
    bool summaryPending = false;
    bool summarySent = true;
    bool closeRequested = false;
    bool sessionLease = false;
    bool ready = false;
    bool predictionReady = false;
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
    void loop() {
        if (!_runnning) return;
        WEBSOCKETS_YIELD();
        handleNewClients();
        // WebSockets 2.6.1 passes its millisecond timeout to ESP32
        // WiFiClient::setTimeout(seconds). Normalize newly accepted header
        // clients before Core::loop can call readStringUntil() on them.
        // Keep WEBSOCKETS_TCP_TIMEOUT in milliseconds for vendor I/O loops.
        static_assert(WEBSOCKETS_TCP_TIMEOUT > 0, "A positive TCP timeout is required");
        constexpr uint32_t timeoutSeconds = (WEBSOCKETS_TCP_TIMEOUT + 999u) / 1000u;
        for (auto& client : _clients) {
            if (client.tcp != nullptr && client.status == WSC_HEADER &&
                client.tcp->getTimeout() != timeoutSeconds * 1000u) {
                client.tcp->setTimeout(timeoutSeconds);
            }
        }
        WebSocketsServerCore::loop();
    }
    void closeChecked() { if (_server != nullptr) WebSocketsServer::close(); }
};

State state;
ReplayBuffer retained;
AckProgressClock ackClock;
Ready isReady = nullptr;
Capture captureSample = nullptr;
Ready predictionIsReady = nullptr;
Predict predictSample = nullptr;
ResetPrediction resetPrediction = nullptr;
ModelInfo modelInfo;
SemaphoreHandle_t guard = nullptr;
QueueHandle_t controls = nullptr;
QueueHandle_t commands = nullptr;
TaskHandle_t transportHandle = nullptr;
CheckedServer socket;
std::atomic<bool> initialized{false};
std::atomic<bool> nativeBusy{false};

struct Lock {
    Lock() { xSemaphoreTake(guard, portMAX_DELAY); }
    ~Lock() { xSemaphoreGive(guard); }
};
template <size_t N> void copy(char (&target)[N], const char* value) {
    snprintf(target, N, "%s", value != nullptr ? value : "");
}

const char* stateName() {
    return state.sampling ? "running" : state.paused ? "paused" : state.incomplete ? "error" : "stopped";
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
    doc["paused"] = state.paused;
    doc["transition_seq"] = state.transitionSequence;
    doc["prediction_enabled"] = state.predictionEnabled;
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
    state.paused = false;
    ++state.acquisitionEpoch;  // Invalidates a capture/inference already in flight.
    state.summaryPending = state.session[0] != '\0';
    state.summarySent = false;
}

void checkLimitLocked(uint32_t now) {
    if ((state.sampling || (state.paused && retained.size())) && ackClock.expired(now)) stopLocked("retention_limit", true);
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
    doc["transition_seq"] = state.transitionSequence;
    doc["paused"] = state.paused;
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
    if (state.session[0] && !state.sampling && !state.paused) state.summaryPending = true;
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
    if (!state.sampling && !state.paused && retained.size() == 0 && !state.summarySent) state.summaryPending = true;
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
                if (state.session[0] && !state.sampling && !state.paused) state.summaryPending = true;
                StaticJsonDocument<2304> hello;
                hello["type"] = "hello";
                hello["protocol"] = PROTOCOL;
                hello["interval_ms"] = INTERVAL_MS;
                hello["retention_ms"] = REPLAY_RETENTION_MS;
                hello["capacity"] = REPLAY_CAPACITY;
                JsonObject capabilities = hello.createNestedObject("capabilities");
                capabilities["pause"] = true;
                capabilities["continue"] = true;
                capabilities["durable_replay"] = true;
                capabilities["prediction"] = predictSample != nullptr;
                capabilities["requires_protocol3_client"] = true;
                hello["prediction_ready"] = state.predictionReady;
                JsonObject model = hello.createNestedObject("model");
                model["profile_id"] = modelInfo.profileId;
                model["scaler_profile_id"] = modelInfo.scalerProfileId;
                model["runtime_version"] = modelInfo.runtimeVersion;
                model["production_approved"] = modelInfo.productionApproved;
                model["output_elements"] = modelInfo.outputElements;
                JsonArray classMap = model.createNestedArray("class_map");
                for (uint8_t i = 0; modelInfo.classMap && i < modelInfo.outputElements; ++i) classMap.add(modelInfo.classMap[i]);
                const bool ready = state.ready;
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
    command.nativeBusy = nativeBusy.load();
    if (!field(doc, "cmd", command.cmd, sizeof(command.cmd)) ||
        !field(doc, "session_id", command.sessionId, sizeof(command.sessionId))) {
        socket.disconnect(client); return;
    }
    const bool ack = strcmp(command.cmd, "ACK_SAMPLES") == 0;
    const bool resume = strcmp(command.cmd, "RESUME_DATASET") == 0;
    const bool transition = strcmp(command.cmd, "PAUSE_DATASET") == 0 || strcmp(command.cmd, "CONTINUE_DATASET") == 0;
    if (ack || resume || transition) {
        if (!field(doc, "boot_id", command.bootId, sizeof(command.bootId)) ||
            ((!transition) && !doc["next_seq"].is<uint32_t>())) { socket.disconnect(client); return; }
        if (!transition) command.nextSequence = doc["next_seq"].as<uint32_t>();
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
    if (resume || transition || strcmp(command.cmd, "START_DATASET") == 0) {
        if (!field(doc, "label", command.label, sizeof(command.label))) {
            socket.disconnect(client); return;
        }
    }
    if (strcmp(command.cmd, "START_DATASET") == 0) {
        if (!doc["sample_interval_ms"].is<uint32_t>()) { socket.disconnect(client); return; }
        command.intervalMs = doc["sample_interval_ms"].as<uint32_t>();
        if (doc.containsKey("prediction_enabled") && !doc["prediction_enabled"].is<bool>()) { socket.disconnect(client); return; }
        command.predictionEnabled = doc["prediction_enabled"] | false;
    }
    if (transition) {
        if (!doc["transition_seq"].is<uint32_t>() || !doc["nulling_profile_id"].is<uint8_t>()) { socket.disconnect(client); return; }
        command.transitionSequence = doc["transition_seq"].as<uint32_t>();
        command.nullingProfile = doc["nulling_profile_id"].as<uint8_t>();
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
            const bool identical = !strcmp(state.label, command.label) && command.intervalMs == INTERVAL_MS && command.predictionEnabled == state.predictionEnabled;
            if (ackLocked(command, identical, identical ? "already_registered" : "idempotency_mismatch")) statusLocked();
            return;
        }
        if (state.sampling || state.paused || retained.size() || !state.summarySent) {
            ackLocked(command, false, "session_or_retained_data_pending");
        } else if (state.session[0] && !strcmp(state.session, command.sessionId)) {
            ackLocked(command, false, "session_id_reused");
        } else if (command.nativeBusy || nativeBusy.load()) {
            ackLocked(command, false, "native_operation_busy");
        } else if (command.intervalMs != INTERVAL_MS || isReady == nullptr || !isReady()) {
            ackLocked(command, false, "requires_500ms_24v_and_saved_valid_profile");
        } else if (command.predictionEnabled && (predictSample == nullptr || predictionIsReady == nullptr || !predictionIsReady())) {
            ackLocked(command, false, "prediction_unavailable");
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
            ++state.acquisitionEpoch;
            state.transitionSequence = 0;
            state.transitionCommand[0] = state.transitionId[0] = '\0';
            state.predictionEnabled = command.predictionEnabled;
            state.paused = false;
            state.overruns = 0;
            state.incomplete = false;
            state.summaryPending = false;
            state.summarySent = false;
            state.sessionLease = true;
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
            if (!state.sampling && !state.paused) state.summaryPending = true;
            if (!ackLocked(command, true, "resumed")) return;
            if (!statusLocked()) requestCloseLocked();
            state.streamEnabled = !state.closeRequested;
        }
    } else if (strcmp(command.cmd, "PAUSE_DATASET") == 0 || strcmp(command.cmd, "CONTINUE_DATASET") == 0) {
        const bool pause = strcmp(command.cmd, "PAUSE_DATASET") == 0;
        if (!state.session[0] || strcmp(command.bootId, state.boot) || strcmp(command.sessionId, state.session) ||
            strcmp(command.label, state.label) || command.nullingProfile != state.profile) {
            ackLocked(command, false, "transition_identity_mismatch");
        } else if (command.transitionSequence == state.transitionSequence && state.transitionSequence &&
                   !strcmp(command.cmd, state.transitionCommand) && !strcmp(command.commandId, state.transitionId)) {
            if (ackLocked(command, true, "already_registered")) statusLocked();
        } else if (state.transitionSequence == UINT32_MAX || command.transitionSequence != state.transitionSequence + 1) {
            ackLocked(command, false, "transition_sequence_mismatch");
        } else if (state.incomplete || (!state.sampling && !state.paused) || state.stopCommand[0]) {
            ackLocked(command, false, "session_terminal");
        } else if ((pause && !state.sampling) || (!pause && !state.paused)) {
            ackLocked(command, false, "transition_state_mismatch");
        } else if (!pause && (command.nativeBusy || nativeBusy.load())) {
            ackLocked(command, false, "native_operation_busy");
        } else if (!pause && (isReady == nullptr || !isReady())) {
            ackLocked(command, false, "requires_24v_and_saved_valid_profile");
        } else if (uxQueueSpacesAvailable(controls) < 2) {
            ackLocked(command, false, "transport_busy");
        } else {
            // process() and acquireDueSample() share the main thread. Capture
            // has completed before this transition ACK can be queued.
            ++state.acquisitionEpoch;
            state.transitionSequence = command.transitionSequence;
            copy(state.transitionCommand, command.cmd);
            copy(state.transitionId, command.commandId);
            state.paused = pause;
            state.sampling = !pause;
            copy(state.reason, pause ? "operator_pause" : "operator_continue");
            if (!pause) state.nextDue = millis() + INTERVAL_MS;
            if (ackLocked(command, true, pause ? "paused" : "continued")) {
                if (!statusLocked()) requestCloseLocked();
            }
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
                if (state.sampling || state.paused) stopLocked("operator_stop", false);
            }
            if (ackLocked(command, true, "stopped")) statusLocked();
            if (!state.sampling && !state.paused && !state.summarySent) state.summaryPending = true;
        }
    } else {
        ackLocked(command, false, "unknown_command");
    }
}

// Called only by poll() on the main thread. Native serial/calibration/radio
// cannot execute concurrently with this ADS/MAV/NN operation.
void acquireDueSample() {
        uint32_t acquisitionEpoch;
        bool predictionEnabled;
        {
            Lock lock;
            checkLimitLocked(millis());
            if (!state.sampling || static_cast<int32_t>(millis() - state.nextDue) < 0) return;
            acquisitionEpoch = state.acquisitionEpoch;
            predictionEnabled = state.predictionEnabled;
            state.nextDue += INTERVAL_MS;
        }
        Sample sample;
        sample.raw.timestampMs = millis();
        const bool valid = isReady != nullptr && isReady() && captureSample(sample.raw);
        sample.raw.scanEndMs = millis();
        sample.predictionEnabled = predictionEnabled;
        // A transport/session transition does not invalidate the native MAV
        // or a valid steady alarm. Main-thread ownership permits continuity.
        if (valid) {
            sample.prediction.status = PredictionStatus::NotReady;
            // CSV projection is optional; native inference/AUTO alarm is not.
            if (predictSample != nullptr) {
                const uint32_t started = millis();
                predictSample(sample.raw, sample.prediction);
                sample.prediction.inferenceDurationMs = millis() - started;
                if (sample.prediction.status == PredictionStatus::Valid &&
                    (sample.prediction.predictedClass < 0 || sample.prediction.predictedClass >= modelInfo.outputElements ||
                     modelInfo.classMap == nullptr || sample.prediction.gasClass != modelInfo.classMap[sample.prediction.predictedClass] ||
                     !std::isfinite(sample.prediction.confidence) || sample.prediction.confidence < 0.0f || sample.prediction.confidence > 1.0f)) {
                    sample.prediction = Prediction{};
                    sample.prediction.status = PredictionStatus::Error;
                    sample.prediction.inferenceDurationMs = millis() - started;
                }
            }
        }
        if (!valid && resetPrediction != nullptr) resetPrediction();
        Lock lock;
        const uint32_t completed = millis();
        checkLimitLocked(completed);
        if (!state.sampling || acquisitionEpoch != state.acquisitionEpoch) return;
        if (!valid) {
            // Reset outside the state mutex: callbacks never run under a lock
            // also acquired by transport. No synthetic zero frame is inferred.
            stopLocked("invalid_sample_or_power", true);
            return;
        }
        if (static_cast<int32_t>(completed - state.nextDue) >= 0) {
            const uint32_t missed = (completed - state.nextDue) / INTERVAL_MS + 1;
            state.overruns += missed;
            state.nextDue += missed * INTERVAL_MS;
        }
        if (!retained.append(sample, state.overruns)) {
            stopLocked(retained.full() ? "buffer_full" : "sequence_limit", true);
        } else {
            ackClock.arm(completed);
            checkLimitLocked(completed);
        }
}

bool sampleMessageLocked(ControlMessage& wire, uint32_t& sequence) {
    if (!state.streamEnabled || state.client < 0 ||
        state.offerNext - retained.acknowledgedNext() >= REPLAY_WINDOW) return false;
    const RetainedSample* record = retained.find(state.offerNext);
    if (record == nullptr) return false;
    sequence = record->sequence;
    StaticJsonDocument<2304> doc;
    doc["type"] = "sample";
    doc["device_id"] = state.device;
    doc["session_id"] = state.session;
    doc["seq"] = record->sequence;
    doc["timestamp_ms"] = record->sample.raw.timestampMs;
    doc["scan_end_ms"] = record->sample.raw.scanEndMs;
    doc["mode"] = "DATASET";
    doc["label"] = state.label;
    doc["nulling_profile_id"] = state.profile;
    doc["overrun_count"] = record->overruns;
    JsonArray voltage = doc.createNestedArray("sensor_voltage");
    JsonArray gain = doc.createNestedArray("sensor_gain");
    JsonArray status = doc.createNestedArray("sensor_status");
    for (size_t i = 0; i < GLD_DATASET_FEATURE_COUNT; ++i) {
        voltage.add(record->sample.raw.voltage[i]);
        gain.add(record->sample.raw.gain[i]);
        status.add(record->sample.raw.status[i]);
    }
    JsonObject prediction = doc.createNestedObject("prediction");
    const Prediction& result = record->sample.prediction;
    const bool valid = record->sample.predictionEnabled && result.status == PredictionStatus::Valid;
    prediction["enabled"] = record->sample.predictionEnabled;
    prediction["valid"] = valid;
    const char* predictionStatus = "error";
    // Native inference runs independently of the CSV option. Project the
    // protocol's disabled/null shape when prediction columns are unchecked.
    switch (record->sample.predictionEnabled ? result.status : PredictionStatus::Disabled) {
        case PredictionStatus::Disabled: predictionStatus = "disabled"; break;
        case PredictionStatus::NotReady: predictionStatus = "not_ready"; break;
        case PredictionStatus::Warmup: predictionStatus = "warmup"; break;
        case PredictionStatus::Error: break;
        case PredictionStatus::Valid: predictionStatus = "valid"; break;
    }
    prediction["status"] = predictionStatus;
    prediction["predicted_class"] = nullptr;
    prediction["gas_class"] = nullptr;
    prediction["confidence"] = nullptr;
    if (valid) {
        prediction["predicted_class"] = result.predictedClass;
        prediction["gas_class"] = result.gasClass;
        prediction["confidence"] = result.confidence;
    }
    prediction["inference_duration_ms"] = result.inferenceDurationMs;
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
    if (transportHandle) { vTaskDelete(transportHandle); transportHandle = nullptr; }
    socket.closeChecked();
    WiFi.softAPdisconnect(true);
    if (controls) { vQueueDelete(controls); controls = nullptr; }
    if (commands) { vQueueDelete(commands); commands = nullptr; }
    if (guard) { vSemaphoreDelete(guard); guard = nullptr; }
}
}  // namespace

bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture,
           Ready predictionReady, Predict predict, ResetPrediction reset,
           const ModelInfo& model) {
    if (initialized || ready == nullptr || capture == nullptr) return false;
    copy(state.device, deviceId);
    state.profile = nullingProfileId;
    isReady = ready;
    captureSample = capture;
    predictionIsReady = predictionReady;
    predictSample = predict;
    resetPrediction = reset;
    modelInfo = model;
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
    const char* password = GLD_DATASET_WORKFLOW_PRIVATE_PASSWORD;
    const IPAddress address(192, 168, 4, 1);
    WiFi.persistent(false);
    // Preserve any station connection initialized by native MQTT Dataset.
    const wifi_mode_t mode = (WiFi.getMode() & WIFI_MODE_STA) ? WIFI_AP_STA : WIFI_AP;
    if (!WiFi.mode(mode) ||
        !WiFi.softAPConfig(address, address, IPAddress(255, 255, 255, 0)) ||
        !WiFi.softAP(ssid, password, 1, false, 1)) { failStartup(); return false; }
    socket.setAuthorization("gld", password);
    socket.onEvent(websocket);
    socket.enableHeartbeat(5000, 2000, 1);
    if (!socket.beginChecked()) { failStartup(); return false; }
    if (xTaskCreate(transmitter, "gld_workflow_tx", 12288, nullptr, 1, &transportHandle) != pdPASS) {
        failStartup(); return false;
    }
    state.ready = isReady();
    state.predictionReady = predictionIsReady != nullptr && predictionIsReady();
    initialized = true;
    return true;
}

bool available() { return initialized.load(); }

bool clientConnected() {
    if (!initialized || !guard) return false;
    Lock lock;
    return state.client >= 0;
}

bool exchangeNativeBusy(bool busy) { return nativeBusy.exchange(busy); }

bool ownsSession() {
    if (!initialized || !guard) return false;
    Lock lock;
    return state.sessionLease;
}

void refreshRuntime(uint8_t nullingProfileId) {
    if (!initialized || !guard) return;
    // Only the main thread observes native mutable readiness/model state.
    const bool ready = isReady != nullptr && isReady();
    const bool predictionReady = predictionIsReady != nullptr && predictionIsReady();
    bool invalidated = false;
    {
        Lock lock;
        state.ready = ready;
        state.predictionReady = predictionReady;
        if (!state.sessionLease) {
            invalidated = state.profile != nullingProfileId;
            state.profile = nullingProfileId;
        }
        if (state.sessionLease && (state.sampling || state.paused) && !ready) {
            stopLocked("invalid_sample_or_power", true);
            invalidated = true;
        }
    }
    if (invalidated && resetPrediction != nullptr) resetPrediction();
}

void poll() {
    if (!initialized || !guard) return;
    Command command;
    while (xQueueReceive(commands, &command, 0) == pdTRUE) process(command);
    acquireDueSample();
    Lock lock;
    checkLimitLocked(millis());
    if (state.sessionLease && !state.sampling && !state.paused && retained.size() == 0 &&
        state.summarySent && state.client < 0) state.sessionLease = false;
    if (state.client < 0 || !state.streamEnabled) return;
    if (!state.sampling && !state.paused && state.summaryPending && retained.size() == 0 &&
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
}  // namespace pgl::gld::datasetworkflowwifi
#endif
