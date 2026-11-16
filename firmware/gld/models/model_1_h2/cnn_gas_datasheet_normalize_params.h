// Parameter normalisasi (min-max) & dequantization output untuk model CNN dual-branch + datasheet
#ifndef CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H
#define CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H

#define CNN_GAS_N_ADC 8
#define CNN_GAS_N_EVIDENCE 7
#define CNN_GAS_N_CLASSES 3

// Urutan fitur ADC WAJIB: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
static const char* CNN_GAS_ADC_NAMES[CNN_GAS_N_ADC] = {"MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"};

static const char* CNN_GAS_EVIDENCE_NAMES[CNN_GAS_N_EVIDENCE] = {"LPG_Combustible", "Methane_CNG", "CO", "Hydrogen", "Alcohol_Ethanol", "AirQuality_NH3_CO2", "Smoke"};

static const char* CNN_GAS_CLASS_NAMES[CNN_GAS_N_CLASSES] = {"Clean_Air", "H2", "LPG"};

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.68000001f, 0.00490423f, 0.00577968f, -0.00322094f, -0.64999998f, -0.01520367f, -0.02516099f, -0.03261270f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.93203688f, 0.93506253f, 0.15791170f, 0.95232600f, 0.83999997f, 0.98828447f, 0.99761021f, 0.95542830f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {0.33979177f, 0.60316223f, 0.52903783f, 1.28691435f, 0.00982300f, 0.00113842f, 0.22261882f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {12.40421104f, 10.02026367f, 7.46494007f, 7.71887684f, 5.49094439f, 3.98824692f, 8.83455563f};

// Kuantisasi INPUT ADC (int8)
static const float CNN_GAS_ADC_SCALE = 0.0039215689f;
static const int CNN_GAS_ADC_ZERO_POINT = -128;

// Kuantisasi INPUT evidence (int8)
static const float CNN_GAS_EVID_SCALE = 0.0039215689f;
static const int CNN_GAS_EVID_ZERO_POINT = -128;

// Dequantization OUTPUT (int8)
static const float CNN_GAS_OUTPUT_SCALE = 0.0039062500f;
static const int CNN_GAS_OUTPUT_ZERO_POINT = -128;

#endif
