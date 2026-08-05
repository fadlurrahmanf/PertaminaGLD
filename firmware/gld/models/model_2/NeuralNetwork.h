#ifndef __NeuralNetwork__
#define __NeuralNetwork__

#include <stdint.h>

namespace tflite
{
    template <unsigned int tOpCount>
    class MicroMutableOpResolver;
    class ErrorReporter;
    class Model;
    class MicroInterpreter;
} // namespace tflite

struct TfLiteTensor;

// CNN dual-branch + datasheet-evidence gas classification model (INT8,
// dual-input: 8 raw ADC channels + 7 sensitivity-table "evidence" features).
// See ModelMetadata.h for the fail-closed production-approval contract.
class NeuralNetwork
{
private:
    static constexpr unsigned int kOpCount = 10;

    tflite::MicroMutableOpResolver<kOpCount> *resolver;
    tflite::ErrorReporter *error_reporter;
    const tflite::Model *model;
    tflite::MicroInterpreter *interpreter;
    TfLiteTensor *adcInput;
    TfLiteTensor *evidenceInput;
    TfLiteTensor *output;
    uint8_t *tensor_arena;

    int outputSize;
    bool initialized;

    bool resolveInputTensors();

public:
    NeuralNetwork();
    ~NeuralNetwork();

    // rawAdc order must match BoardPins.h SENSOR_NAMES: MQ8, MQ135, MQ3,
    // MQ5, MQ4, MQ7, MQ6, MQ2. Internally normalizes, computes the evidence
    // branch from the sensitivity table, quantizes, runs both branches, and
    // returns the argmax class index (or -1 on error) with its confidence
    // (dequantized softmax probability, 0..1) in confidence_score.
    int predict(const float rawAdc[8], float &confidence_score);

    bool isInitialized();
    int getInputSize();
    int getOutputSize();
};

#endif
