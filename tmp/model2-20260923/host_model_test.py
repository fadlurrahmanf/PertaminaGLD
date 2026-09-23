"""Host smoke test of the actual release TFLM and NN, no board access."""
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path('D:/Github/PertaminaGLD')
OUT = Path(__file__).resolve().parent / 'host-test'
OUT.mkdir(exist_ok=True)
MODEL = Path(__file__).resolve().parent / 'prepared-model2'
LIB = ROOT / 'firmware/lib/tfmicro'
CXX = Path('C:/Users/MSI/.platformio/packages/toolchain-gccmingw32/bin/g++.exe')
env = dict(os.environ)
env['PATH'] = str(CXX.parent) + os.pathsep + env.get('PATH', '')
for path in MODEL.iterdir():
    if path.suffix in ('.h', '.cpp'):
        shutil.copy2(path, OUT / path.name)
# g++5 only: equivalent nested namespace syntax; actual NN/kernels untouched.
metadata = (OUT / 'ModelMetadata.h').read_text(encoding='utf-8')
metadata = metadata.replace('namespace pgl::gld::model {', 'namespace pgl { namespace gld { namespace model {')
metadata = metadata.replace('}  // namespace pgl::gld::model', '}}}  // namespace pgl::gld::model')
(OUT / 'ModelMetadata.h').write_text(metadata, encoding='utf-8')
program = r'''
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
'''
(OUT / 'smoke.cpp').write_text(program, encoding='utf-8')
sources = []
excluded = {'all_ops_resolver.cc', 'test_helpers.cc', 'keyword_scrambled_model_data.cc', 'test_utils.cc', 'test_conv_model.cc', 'kernel_runner.cc'}
for path in (LIB / 'tensorflow/lite').rglob('*'):
    if path.suffix in ('.cc', '.c') and path.name not in excluded and 'testing' not in path.parts and 'benchmarks' not in path.parts:
        sources.append(path)
includes = [LIB, LIB/'third_party/ruy', LIB/'third_party/gemmlowp', LIB/'third_party/flatbuffers/include', OUT]
objects = []
for path in [p for p in sources if p.suffix == '.c']:
    obj = OUT / (path.name + '.o')
    subprocess.run([str(CXX.with_name('gcc.exe')), '-O0', '-w', *['-I'+str(p) for p in includes],
                    '-c', str(path), '-o', str(obj)], check=True, env=env, timeout=30)
    objects.append(obj)
args = ['-std=c++14', '-O0', '-w', *['-I'+str(p) for p in includes],
        str(OUT/'smoke.cpp'), str(OUT/'NeuralNetwork.cpp'), str(OUT/'model_data.cpp'),
        *[str(p) for p in sources if p.suffix != '.c'], *map(str, objects), '-o', str(OUT/'smoke.exe')]
response = OUT/'compile.rsp'
response.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args), encoding='utf-8')
subprocess.run([str(CXX), '@'+str(response)], check=True, env=env, timeout=180)
subprocess.run([str(OUT/'smoke.exe')], check=True, env=env, timeout=30)
