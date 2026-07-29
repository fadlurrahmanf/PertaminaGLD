#pragma once

// CNN real-time inference module (TAHAP 5) — kept out of main.cpp.
//
// Wraps the proven dual-branch TFLite Micro CNN (see
// firmware/gld/model/NeuralNetwork.cpp, model_data.h, ModelMetadata.h)
// behind the CNN_Init()/CNN_Predict() flow used by GldCnnRuntimeMain.cpp:
// load model + allocate tensor arena once (TAHAP 6/7/8), then per scan
// normalize -> quantize -> Invoke() -> dequantize/argmax (TAHAP 9-14).
//
// NOTE: this model is dual-input (8 raw ADC channels + 7 sensitivity-table
// "evidence" features) and 3-class (CO2, Clean_Air, LPG) per
// cnn_gas_datasheet_normalize_params.h — not the single-input/4-class shape
// a generic CNN guide assumes. CNN_Predict() still only requires the 8 raw
// ADC readings from the caller; the evidence branch is computed internally.

#include <cstdint>

namespace pgl::gld::cnn {

struct CnnPrediction {
    bool ok;                    // false if model not ready or inference failed
    int classIndex;             // argmax index into CNN_GAS_CLASS_NAMES, -1 if !ok
    const char* className;      // e.g. "LPG", "Clean_Air", "CO2"
    uint8_t gasClass;           // mapped GLD protocol gas class (ModelMetadata::CLASS_MAP)
    float confidence;           // dequantized softmax probability, 0..1
    uint8_t confidencePercent;  // confidence rounded to 0..100
};

// TAHAP 6/7/8: load the TFLite model, resolve ops, allocate the tensor
// arena. Call exactly once, after Serial/Sensor/WiFi/MQTT init in setup().
// Returns false (fail closed) if the model or tensor contract can't be
// satisfied — callers must not trust CNN_Predict() output in that case.
bool CNN_Init();

bool CNN_IsReady();

// TAHAP 9-14. rawAdc must be the 8 sensor voltages in the order required by
// training: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 (see
// cnn_gas_datasheet_normalize_params.h CNN_GAS_ADC_NAMES). Internally:
// normalizes (TAHAP 10), quantizes to INT8 using the model's own
// scale/zero-point (TAHAP 11), runs interpreter->Invoke() (TAHAP 12),
// dequantizes the output tensor and returns the largest-probability class
// (TAHAP 13/14).
CnnPrediction CNN_Predict(const float rawAdc[8]);

}  // namespace pgl::gld::cnn
