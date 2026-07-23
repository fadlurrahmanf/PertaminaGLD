#pragma once

// CNN dual-branch + datasheet-evidence gas classification model, INT8
// quantized (see cnn_gas_sensitivity_table.h / cnn_gas_datasheet_normalize_params.h
// for the companion feature pipeline this model expects).
extern const unsigned char g_cnn_gas_datasheet_model_data[];
extern const unsigned int g_cnn_gas_datasheet_model_data_len;
