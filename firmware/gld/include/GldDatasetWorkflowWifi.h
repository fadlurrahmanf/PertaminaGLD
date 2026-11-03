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
};
using Predict = void (*)(const RawSample& sample, Prediction& result);
using ResetPrediction = void (*)();

// All callbacks run on the Arduino main thread, between native operations.
// Predict consumes the captured frame once and maintains native inference/alarm
// even when the session omits prediction columns. Socket transport owns no ADC,
// model, GPIO, calibration or native serial callbacks.
bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture,
           Ready predictionReady, Predict predict, ResetPrediction resetPrediction,
           const ModelInfo& model);
void poll();
bool available();
bool clientConnected();
// Session ownership includes Pause, replay and finalization, and is released
// only after a terminal session is fully delivered and the client disconnects.
bool ownsSession();
// Main-thread-only metadata refresh; never changes a leased session's profile.
void refreshRuntime(uint8_t nullingProfileId);
// Native long operations mark admission busy without sharing their hardware.
// The return value permits nested RAII scopes to restore the previous state.
bool exchangeNativeBusy(bool busy);
}  // namespace pgl::gld::datasetworkflowwifi
#endif
