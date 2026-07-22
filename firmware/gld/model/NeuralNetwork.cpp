#include "NeuralNetwork.h"
#include "ModelMetadata.h"
#include "model_data.h"
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

}  // namespace

// Define a static tensor arena for better alignment and to avoid heap fragmentation
const int kArenaSize = 40 * 1024; // Adjust size as needed
uint8_t static_tensor_arena[kArenaSize] __attribute__((aligned(16))); // 16-byte alignment

NeuralNetwork::NeuralNetwork()
    : resolver(nullptr), error_reporter(nullptr), model(nullptr),
      interpreter(nullptr), input(nullptr), output(nullptr),
      tensor_arena(nullptr), inputSize(0), outputSize(0), initialized(false) // Initialize members
{
    error_reporter = new tflite::MicroErrorReporter();
    if (!error_reporter) {
        return;
    }

    model = tflite::GetModel(model_tflite);
    if (model->version() != TFLITE_SCHEMA_VERSION)
    {
        TF_LITE_REPORT_ERROR(error_reporter, "Model provided is schema version %d not equal to supported version %d.",
                            model->version(), TFLITE_SCHEMA_VERSION);
        return;
    }

    resolver = new tflite::MicroMutableOpResolver<10>();
    if (!resolver) {
        TF_LITE_REPORT_ERROR(error_reporter, "Could not allocate resolver");
        return;
    }

    resolver->AddFullyConnected();
    resolver->AddMul();
    resolver->AddAdd();
    resolver->AddLogistic();
    resolver->AddReshape();
    resolver->AddQuantize();
    resolver->AddDequantize();
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

    input = interpreter->input(0);
    output = interpreter->output(0);

    if (!input || !output) {
        TF_LITE_REPORT_ERROR(error_reporter, "Input or output tensor not found.");
        return;
    }

    if (input->type != kTfLiteFloat32 || output->type != kTfLiteFloat32) {
        TF_LITE_REPORT_ERROR(error_reporter, "Model tensors must be float32.");
        return;
    }

    inputSize = tensorElementCount(input);
    outputSize = tensorElementCount(output);
    if (inputSize != pgl::gld::model::EXPECTED_INPUT_ELEMENTS ||
        outputSize != pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS) {
        TF_LITE_REPORT_ERROR(
            error_reporter,
            "Model tensor contract mismatch: input=%d output=%d expected=%d/%d.",
            inputSize,
            outputSize,
            pgl::gld::model::EXPECTED_INPUT_ELEMENTS,
            pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS);
        inputSize = 0;
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

float *NeuralNetwork::getInputBuffer()
{
    if (!initialized || !input) {
        TF_LITE_REPORT_ERROR(error_reporter, "Network not initialized or input buffer not available.");
        return nullptr;
    }
    return input->data.f;
}

float *NeuralNetwork::getOutputBuffer()
{
    if (!initialized || !output) {
        TF_LITE_REPORT_ERROR(error_reporter, "Network not initialized or output buffer not available.");
        return nullptr;
    }
    return output->data.f;
}

// <--- MODIFIED predict FUNCTION --->
int NeuralNetwork::predict(float &confidence_score) // Now takes a reference to store confidence
{
    if (!initialized) {
        TF_LITE_REPORT_ERROR(error_reporter, "Network not initialized. Cannot predict.");
        confidence_score = 0.0f; // Set to 0 on error
        return -1; // Indicate error
    }

    TfLiteStatus invoke_status = interpreter->Invoke();
    if (invoke_status != kTfLiteOk) {
        TF_LITE_REPORT_ERROR(error_reporter, "Interpreter invoke failed.");
        confidence_score = 0.0f; // Set to 0 on error
        return -1; // Indicate error
    }

    // Find class with highest probability
    float max_score = output->data.f[0];
    if (!std::isfinite(max_score)) {
        confidence_score = 0.0f;
        return -1;
    }
    int max_index = 0;

    for (int i = 1; i < outputSize; i++) {
        if (!std::isfinite(output->data.f[i])) {
            confidence_score = 0.0f;
            return -1;
        }
        if (output->data.f[i] > max_score) {
            max_score = output->data.f[i];
            max_index = i;
        }
    }
    confidence_score = max_score; // Store the highest score in the reference
    return max_index;
}
// <--- END MODIFIED predict FUNCTION --->

int NeuralNetwork::getInputSize() {
    if (!initialized) {
        return 0;
    }
    return inputSize;
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
