/* Copyright 2021 The TensorFlow Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================*/
// Added locally: this vendored TFLite Micro snapshot ships the reference
// kernels for CONV_2D/MAX_POOL_2D/etc. but not EXPAND_DIMS. EXPAND_DIMS never
// reorders data -- it only inserts a size-1 dimension -- and the output
// tensor's shape is already resolved statically from the flatbuffer before
// Prepare() runs (see reshape.cc for the same property), so this mirrors
// reshape.cc's byte-copy Eval rather than porting upstream's dynamic-shape
// version, which needs APIs this snapshot doesn't have.

#include "tensorflow/lite/c/builtin_op_data.h"
#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/kernels/internal/tensor_ctypes.h"
#include "tensorflow/lite/kernels/kernel_util.h"
#include "tensorflow/lite/kernels/op_macros.h"
#include "tensorflow/lite/micro/kernels/kernel_util.h"
#include "tensorflow/lite/micro/memory_helpers.h"
#include "tensorflow/lite/micro/micro_utils.h"

namespace tflite {
namespace ops {
namespace micro {
namespace expand_dims {

constexpr int kInputTensor = 0;
constexpr int kOutputTensor = 0;

TfLiteStatus Prepare(TfLiteContext* context, TfLiteNode* node) {
  TF_LITE_ENSURE(context, NumInputs(node) == 1 || NumInputs(node) == 2);
  TF_LITE_ENSURE_EQ(context, NumOutputs(node), 1);

  const TfLiteTensor* input = GetInput(context, node, kInputTensor);
  TF_LITE_ENSURE(context, input != nullptr);
  TfLiteTensor* output = GetOutput(context, node, kOutputTensor);
  TF_LITE_ENSURE(context, output != nullptr);

  TF_LITE_ENSURE_TYPES_EQ(context, input->type, output->type);
  // Output shape is already resolved from the flatbuffer; only the element
  // count needs to match (a size-1 dimension was inserted).
  TF_LITE_ENSURE_EQ(context, NumElements(input), NumElements(output));
  return kTfLiteOk;
}

TfLiteStatus Eval(TfLiteContext* context, TfLiteNode* node) {
  const TfLiteEvalTensor* input =
      tflite::micro::GetEvalInput(context, node, kInputTensor);
  TfLiteEvalTensor* output =
      tflite::micro::GetEvalOutput(context, node, kOutputTensor);

  size_t input_bytes;
  TF_LITE_ENSURE_STATUS(TfLiteTypeSizeOf(input->type, &input_bytes));
  input_bytes *= ElementCount(*input->dims);

  if (input->data.raw != output->data.raw) {
    for (size_t i = 0; i < input_bytes; ++i) {
      output->data.raw[i] = input->data.raw[i];
    }
  }
  return kTfLiteOk;
}

}  // namespace expand_dims

TfLiteRegistration Register_EXPAND_DIMS() {
  return {/*init=*/nullptr,
          /*free=*/nullptr,
          /*prepare=*/expand_dims::Prepare,
          /*invoke=*/expand_dims::Eval,
          /*profiling_string=*/nullptr,
          /*builtin_code=*/0,
          /*custom_name=*/nullptr,
          /*version=*/0};
}

}  // namespace micro
}  // namespace ops
}  // namespace tflite
