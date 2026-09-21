// Parameter normalisasi (min-max) & dequantization output untuk model CNN dual-branch + datasheet
#ifndef CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H
#define CNN_GAS_DATASHEET_NORMALIZE_PARAMS_H

#define CNN_GAS_N_ADC 8
#define CNN_GAS_N_EVIDENCE 7
#define CNN_GAS_N_CLASSES 4

// Urutan fitur ADC WAJIB: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
static const char* CNN_GAS_ADC_NAMES[CNN_GAS_N_ADC] = {"MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"};

static const char* CNN_GAS_EVIDENCE_NAMES[CNN_GAS_N_EVIDENCE] = {"LPG_Combustible", "Methane_CNG", "CO", "Hydrogen", "Alcohol_Ethanol", "AirQuality_NH3_CO2", "Smoke"};

static const char* CNN_GAS_CLASS_NAMES[CNN_GAS_N_CLASSES] = {"CO2", "Clean_Air", "H2", "LPG"};

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.60000002f, 0.00490443f, 0.00543134f, -0.00322094f, -0.64999998f, -0.01520367f, -0.02516099f, -0.03261270f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.93203688f, 1.36653411f, 0.15791170f, 1.64827311f, 1.18450952f, 1.29913104f, 1.26188087f, 1.22372282f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {0.26200223f, 0.53004992f, 0.47259197f, 1.00116789f, 0.01627133f, 0.00325348f, 0.17584638f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {11.92357826f, 9.93673897f, 7.23797750f, 7.82425833f, 4.73850203f, 3.03788018f, 8.41230202f};

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
