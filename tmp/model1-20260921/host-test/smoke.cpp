
#include <cassert>
#include <cmath>
#include <cstdio>
#include "NeuralNetwork.h"
#include "ModelMetadata.h"
#include "model_data.h"
#include "cnn_gas_datasheet_normalize_params.h"
#include "tensorflow/lite/schema/schema_generated.h"
int main() {
  flatbuffers::Verifier verifier(g_cnn_gas_datasheet_model_data, g_cnn_gas_datasheet_model_data_len);
  assert(tflite::VerifyModelBuffer(verifier));
  const auto* m = tflite::GetModel(g_cnn_gas_datasheet_model_data);
  auto* graph = m->subgraphs()->Get(0);
  assert(graph->inputs()->size() == 2 && graph->outputs()->size() == 1);
  for (unsigned i = 0; i < graph->inputs()->size(); ++i) {
    const auto* t = graph->tensors()->Get(graph->inputs()->Get(i));
    assert(t->type() == tflite::TensorType_INT8);
    printf("input %u: ", i);
    for (auto d : *t->shape()) printf("%d ", d);
    puts("");
  }
  for (const auto* op : *m->operator_codes())
    printf("op=%d version=%d\n", int(op->builtin_code()), op->version());
  NeuralNetwork nn;
  assert(nn.isInitialized() && nn.getInputSize() == 15 && nn.getOutputSize() == 2);
  assert(pgl::gld::model::CLASS_MAP[0] == 0 && pgl::gld::model::CLASS_MAP[1] == 1);
  for (int example = 0; example < 4; ++example) {
    float input[8];
    for (int i = 0; i < 8; ++i) {
      input[i] = example == 3 ? 0 : CNN_GAS_ADC_MIN[i] + (example * 0.5f) * (CNN_GAS_ADC_MAX[i] - CNN_GAS_ADC_MIN[i]);
    }
    float confidence = 0;
    int cls = nn.predict(input, confidence);
    assert(cls >= 0 && cls < 2 && std::isfinite(confidence) && confidence >= 0 && confidence <= 1);
    printf("example=%d class=%s confidence=%.6f\n", example, CNN_GAS_CLASS_NAMES[cls], confidence);
  }
  puts("PASS actual TFLM AllocateTensors + Invoke, 40KiB arena, INT8 8+7 -> 2; synthetic vectors only");
}
