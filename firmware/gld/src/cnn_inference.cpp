#include "cnn_inference.h"

#include "ProtocolConstants.h"

#include "ModelMetadata.h"
#include "NeuralNetwork.h"
#include "cnn_gas_datasheet_normalize_params.h"

namespace pgl::gld::cnn {

namespace {
NeuralNetwork* g_network = nullptr;
}  // namespace

bool CNN_Init() {
    if (g_network != nullptr) {
        return g_network->isInitialized();
    }
    g_network = new NeuralNetwork();
    return g_network->isInitialized();
}

bool CNN_IsReady() {
    return g_network != nullptr && g_network->isInitialized();
}

CnnPrediction CNN_Predict(const float rawAdc[8]) {
    CnnPrediction result{false, -1, "unknown",
                          pgl::protocol::GLD_GAS_ANOMALY, 0.0f, 0};
    if (!CNN_IsReady()) {
        return result;
    }

    float confidence = 0.0f;
    const int predicted = g_network->predict(rawAdc, confidence);
    if (predicted < 0 || predicted >= CNN_GAS_N_CLASSES) {
        return result;
    }

    result.ok = true;
    result.classIndex = predicted;
    result.className = CNN_GAS_CLASS_NAMES[predicted];
    result.gasClass = pgl::gld::model::CLASS_MAP[predicted];
    result.confidence = confidence;
    result.confidencePercent =
        static_cast<uint8_t>(confidence * 100.0f + 0.5f);
    return result;
}

}  // namespace pgl::gld::cnn
