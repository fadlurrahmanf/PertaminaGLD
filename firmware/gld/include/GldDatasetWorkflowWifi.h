#pragma once

#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW
#if !defined(PGL_GLD_DATASET_WIFI) || !PGL_GLD_DATASET_WIFI
#error "Workflow requires the dedicated Dataset acquisition boundary"
#endif
#if defined(PGL_GLD_DATASET_REPLAY) && PGL_GLD_DATASET_REPLAY
#error "Workflow and protocol2 Replay are separate firmware targets"
#endif
#include "GldDatasetWifi.h"

namespace pgl::gld::datasetworkflowwifi {
using RawSample = pgl::gld::datasetwifi::Sample;
using Capture = pgl::gld::datasetwifi::Capture;
using Ready = pgl::gld::datasetwifi::Ready;

enum class PredictionStatus : uint8_t { Disabled, NotReady, Warmup, Error, Valid };
struct Prediction {
    float confidence = 0.0f;
    uint32_t inferenceDurationMs = 0;
    int16_t predictedClass = -1;
    uint8_t gasClass = 0;
    PredictionStatus status = PredictionStatus::Disabled;
};
struct Sample {
    RawSample raw{};
    Prediction prediction{};
    bool predictionEnabled = false;
};
struct ModelInfo {
    const char* profileId = "";
    const char* scalerProfileId = "";
    const char* runtimeVersion = "";
    const uint8_t* classMap = nullptr;
    uint8_t outputElements = 0;
    bool productionApproved = false;
#if defined(PGL_GLD_BOARD_PROFILE_GLD_ATEX) && PGL_GLD_BOARD_PROFILE_GLD_ATEX
    bool radioAutoTx = false;
#endif
};
using Predict = void (*)(const RawSample& sample, Prediction& result);
using ResetPrediction = void (*)();

// All callbacks run on the Arduino main thread, between native operations.
// Predict consumes the captured frame once and maintains native inference/alarm
// even when the session omits prediction columns. Socket transport owns no ADC,
// model, GPIO, calibration or native serial callbacks.
bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture,
           Ready predictionReady, Predict predict, ResetPrediction resetPrediction,
           const ModelInfo& model, Ready retryInterruptedCapture = nullptr);
void poll();
// Drain queued control commands without acquiring a sensor sample.
void pollCommands();
bool available();
bool clientConnected();
// Read-only main-thread scheduler queries; neither advances acquisition.
bool sampleDue();
bool samplingActive();
// Terminal failure keeps retained data available for drain and reconciliation.
void failSession(const char* reason);
// Session ownership includes Pause, replay and finalization, and is released
// only after a terminal session is fully delivered and the client disconnects.
bool ownsSession();
// Main-thread-only metadata refresh; never changes a leased session's profile.
void refreshRuntime(uint8_t nullingProfileId);
#if defined(PGL_GLD_BOARD_PROFILE_GLD_ATEX) && PGL_GLD_BOARD_PROFILE_GLD_ATEX
// Called only by main thread; transport snapshots under its mutex.
void updateAtexRadioAutoTx(bool enabled);
#endif
// Native long operations mark admission busy without sharing their hardware.
// The return value permits nested RAII scopes to restore the previous state.
bool exchangeNativeBusy(bool busy);
// ATEX radio owner blocks only a new START while finishing a previous TX/RX;
// Pause, Continue, Stop, ACK and replay remain independent of this gate.
void setRadioDrainBlocksStart(bool blocked);
}  // namespace pgl::gld::datasetworkflowwifi
#endif
