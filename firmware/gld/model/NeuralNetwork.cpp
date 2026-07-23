#include "NeuralNetwork.h"
#include "ModelMetadata.h"
#include "model_data.h"
#include "cnn_gas_datasheet_normalize_params.h"
#include "cnn_gas_sensitivity_table.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"

#include <cmath>
#include <limits>

namespace {

int tensorElementCount(const TfLiteTensor* tensor) {
    if (tensor == nullptr || tensor->dims == nullptr || tensor->dims->size <= 0) {
        return 0;
    }
    int count = 1;
    for (int i = 0; i < tensor->dims->size; ++i) {
        const int dimension = tensor->dims->data[i];
        if (dimension <= 0 || count > std::numeric_limits<int>::max() / dimension) {
            return 0;
        }
        count *= dimension;
    }
    return count;
}

int8_t quantize(float normalizedValue, float scale, int zeroPoint) {
    if (scale == 0.0f) return static_cast<int8_t>(zeroPoint);
    long q = lroundf(normalizedValue / scale) + zeroPoint;
    if (q < -128) q = -128;
    if (q > 127) q = 127;
    return static_cast<int8_t>(q);
}

}  // namespace

// Arena sized for the dual-branch CNN (Conv1D + MaxPool1D + 2x Dense +
// Concatenate); measured usage is logged at init via arena_used_bytes().
const int kArenaSize = 40 * 1024;
uint8_t static_tensor_arena[kArenaSize] __attribute__((aligned(16)));

NeuralNetwork::NeuralNetwork()
    : resolver(nullptr), error_reporter(nullptr), model(nullptr),
      interpreter(nullptr), adcInput(nullptr), evidenceInput(nullptr),
      output(nullptr), tensor_arena(nullptr), outputSize(0), initialized(false)
{
    error_reporter = new tflite::MicroErrorReporter();
    if (!error_reporter) {
        return;
    }

    model = tflite::GetModel(g_cnn_gas_datasheet_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION)
    {
        TF_LITE_REPORT_ERROR(error_reporter, "Model provided is schema version %d not equal to supported version %d.",
                            model->version(), TFLITE_SCHEMA_VERSION);
        return;
    }

    resolver = new tflite::MicroMutableOpResolver<kOpCount>();
    if (!resolver) {
        TF_LITE_REPORT_ERROR(error_reporter, "Could not allocate resolver");
        return;
    }

    // Op set required by the dual-branch graph (Conv1D/MaxPool1D lower to
    // CONV_2D/MAX_POOL_2D; see TFLite ModelAnalyzer output in the source
    // notebook, Bagian 10/12).
    resolver->AddExpandDims();
    resolver->AddConv2D();
    resolver->AddReshape();
    resolver->AddMaxPool2D();
    resolver->AddShape();
    resolver->AddStridedSlice();
    resolver->AddPack();
    resolver->AddConcatenation();
    resolver->AddFullyConnected();
    resolver->AddSoftmax();

    tensor_arena = static_tensor_arena;

    interpreter = new tflite::MicroInterpreter(
        model, *resolver, tensor_arena, kArenaSize, error_reporter);
    if (!interpreter) {
        TF_LITE_REPORT_ERROR(error_reporter, "Could not allocate interpreter");
        return;
    }

    TfLiteStatus allocate_status = interpreter->AllocateTensors();
    if (allocate_status != kTfLiteOk)
    {
        TF_LITE_REPORT_ERROR(error_reporter, "AllocateTensors() failed");
        return;
    }

    size_t used_bytes = interpreter->arena_used_bytes();
    TF_LITE_REPORT_ERROR(error_reporter, "Used bytes %d\n", used_bytes);

    if (interpreter->inputs_size() != 2) {
        TF_LITE_REPORT_ERROR(error_reporter, "Expected 2 input tensors, model has %d.",
                            static_cast<int>(interpreter->inputs_size()));
        return;
    }

    if (!resolveInputTensors()) {
        TF_LITE_REPORT_ERROR(error_reporter, "Could not resolve adc/evidence input tensors by shape.");
        return;
    }

    output = interpreter->output(0);
    if (!adcInput || !evidenceInput || !output) {
        TF_LITE_REPORT_ERROR(error_reporter, "Input or output tensor not found.");
        return;
    }

    if (adcInput->type != kTfLiteInt8 || evidenceInput->type != kTfLiteInt8 ||
        output->type != kTfLiteInt8) {
        TF_LITE_REPORT_ERROR(error_reporter, "Model tensors must be int8.");
        return;
    }

    const int adcElements = tensorElementCount(adcInput);
    const int evidenceElements = tensorElementCount(evidenceInput);
    outputSize = tensorElementCount(output);
    if (adcElements != pgl::gld::model::EXPECTED_ADC_INPUT_ELEMENTS ||
        evidenceElements != pgl::gld::model::EXPECTED_EVIDENCE_INPUT_ELEMENTS ||
        outputSize != pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS) {
        TF_LITE_REPORT_ERROR(
            error_reporter,
            "Model tensor contract mismatch: adc=%d evidence=%d output=%d expected=%d/%d/%d.",
            adcElements, evidenceElements, outputSize,
            pgl::gld::model::EXPECTED_ADC_INPUT_ELEMENTS,
            pgl::gld::model::EXPECTED_EVIDENCE_INPUT_ELEMENTS,
            pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS);
        outputSize = 0;
        return;
    }
    initialized = true;
}

// Destructor to clean up dynamically allocated memory
NeuralNetwork::~NeuralNetwork() {
    if (interpreter) {
        delete interpreter;
    }
    if (resolver) {
        delete resolver;
    }
    if (error_reporter) {
        delete error_reporter;
    }
}

bool NeuralNetwork::resolveInputTensors() {
    TfLiteTensor* in0 = interpreter->input(0);
    TfLiteTensor* in1 = interpreter->input(1);
    if (!in0 || !in1 || !in0->dims || !in1->dims) {
        return false;
    }

    // Input tensor order is not guaranteed by the converter (adc_input is a
    // 3-D [batch, 8, 1] tensor for the Conv1D branch; evidence_input is a
    // 2-D [batch, 7] tensor for the Dense branch), so identify by rank
    // rather than trusting index 0/1.
    TfLiteTensor* candidateAdc = nullptr;
    TfLiteTensor* candidateEvidence = nullptr;
    TfLiteTensor* candidates[2] = {in0, in1};
    for (TfLiteTensor* t : candidates) {
        if (t->dims->size == 3 && candidateAdc == nullptr) {
            candidateAdc = t;
        } else if (t->dims->size == 2 && candidateEvidence == nullptr) {
            candidateEvidence = t;
        }
    }
    if (!candidateAdc || !candidateEvidence) {
        return false;
    }
    adcInput = candidateAdc;
    evidenceInput = candidateEvidence;
    return true;
}

int NeuralNetwork::predict(const float rawAdc[8], float &confidence_score)
{
    if (!initialized) {
        TF_LITE_REPORT_ERROR(error_reporter, "Network not initialized. Cannot predict.");
        confidence_score = 0.0f;
        return -1;
    }

    // Step 1: min-max normalize raw ADC.
    float adcNorm[CNN_GAS_N_ADC];
    for (int i = 0; i < CNN_GAS_N_ADC; ++i) {
        const float range = CNN_GAS_ADC_MAX[i] - CNN_GAS_ADC_MIN[i];
        adcNorm[i] = (range != 0.0f) ? (rawAdc[i] - CNN_GAS_ADC_MIN[i]) / range : 0.0f;
    }

    // Step 2: evidence features = normalized ADC x sensitivity table, then
    // min-max normalize.
    float evidenceNorm[CNN_GAS_N_EVIDENCE];
    for (int g = 0; g < CNN_GAS_N_EVIDENCE; ++g) {
        float sum = 0.0f;
        for (int i = 0; i < CNN_GAS_N_ADC; ++i) {
            sum += adcNorm[i] * CNN_GAS_SENSITIVITY_TABLE[i][g];
        }
        const float range = CNN_GAS_EVIDENCE_MAX[g] - CNN_GAS_EVIDENCE_MIN[g];
        evidenceNorm[g] = (range != 0.0f) ? (sum - CNN_GAS_EVIDENCE_MIN[g]) / range : 0.0f;
    }

    // Step 3: quantize into both input tensors using each tensor's own
    // (model-declared) scale/zero-point.
    for (int i = 0; i < CNN_GAS_N_ADC; ++i) {
        adcInput->data.int8[i] =
            quantize(adcNorm[i], adcInput->params.scale, adcInput->params.zero_point);
    }
    for (int g = 0; g < CNN_GAS_N_EVIDENCE; ++g) {
        evidenceInput->data.int8[g] =
            quantize(evidenceNorm[g], evidenceInput->params.scale, evidenceInput->params.zero_point);
    }

    TfLiteStatus invoke_status = interpreter->Invoke();
    if (invoke_status != kTfLiteOk) {
        TF_LITE_REPORT_ERROR(error_reporter, "Interpreter invoke failed.");
        confidence_score = 0.0f;
        return -1;
    }

    // Step 4: dequantize output and argmax.
    const float outScale = output->params.scale;
    const int outZeroPoint = output->params.zero_point;
    float max_score = (output->data.int8[0] - outZeroPoint) * outScale;
    if (!std::isfinite(max_score)) {
        confidence_score = 0.0f;
        return -1;
    }
    int max_index = 0;

    for (int i = 1; i < outputSize; i++) {
        const float score = (output->data.int8[i] - outZeroPoint) * outScale;
        if (!std::isfinite(score)) {
            confidence_score = 0.0f;
            return -1;
        }
        if (score > max_score) {
            max_score = score;
            max_index = i;
        }
    }
    confidence_score = max_score;
    return max_index;
}

int NeuralNetwork::getInputSize() {
    if (!initialized) {
        return 0;
    }
    return pgl::gld::model::EXPECTED_ADC_INPUT_ELEMENTS +
           pgl::gld::model::EXPECTED_EVIDENCE_INPUT_ELEMENTS;
}

int NeuralNetwork::getOutputSize() {
    if (!initialized) {
        return 0;
    }
    return outputSize;
}

bool NeuralNetwork::isInitialized() {
    return initialized;
}
