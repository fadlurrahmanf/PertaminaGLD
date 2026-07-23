// Parameter normalisasi (min-max) & dequantization output untuk model CNN dual-branch + datasheet
#ifndef CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H
#define CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H

#define CNN_GAS_N_ADC 8
#define CNN_GAS_N_EVIDENCE 7
#define CNN_GAS_N_CLASSES 3

// Urutan fitur ADC WAJIB: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
static const char* CNN_GAS_ADC_NAMES[CNN_GAS_N_ADC] = {"MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"};

static const char* CNN_GAS_EVIDENCE_NAMES[CNN_GAS_N_EVIDENCE] = {"LPG_Combustible", "Methane_CNG", "CO", "Hydrogen", "Alcohol_Ethanol", "AirQuality_NH3_CO2", "Smoke"};

static const char* CNN_GAS_CLASS_NAMES[CNN_GAS_N_CLASSES] = {"CO2", "Clean_Air", "LPG"};

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.88400000f, 0.00395266f, 0.00033738f, 0.00062663f, -0.92299998f, -0.92000002f, -0.84399998f, -0.01486317f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.99299997f, 2.49700069f, 0.01190000f, 0.14416960f, 0.86799997f, 1.27645516f, 0.46200001f, 2.49699950f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {1.57478189f, 1.57512629f, 1.03106976f, 1.60288990f, 0.06828214f, 0.08526092f, 1.50557756f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {10.87857151f, 8.58851528f, 6.93729448f, 6.78605366f, 4.85208511f, 3.91176796f, 8.52260971f};

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
