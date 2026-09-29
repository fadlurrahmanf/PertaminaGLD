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

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.00150291f, 0.00473808f, 0.00539662f, -0.00356514f, -0.70999998f, -0.01504890f, -0.02468623f, -0.93000001f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.98916370f, 0.93063146f, 0.01141582f, 0.88741648f, 0.89999998f, 0.74925148f, 0.76095682f, 0.94218522f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {0.90073818f, 0.99449313f, 0.45086271f, 0.45084214f, 0.30999261f, 0.05908305f, 0.55349725f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {12.41826439f, 9.54133892f, 7.09690285f, 7.14483786f, 5.25639868f, 3.85379839f, 8.76687050f};

// Kuantisasi INPUT ADC (int8)
static const float CNN_GAS_ADC_SCALE = 0.0039215689f;
static const int CNN_GAS_ADC_ZERO_POINT = -128;

// Kuantisasi INPUT evidence (int8)
static const float CNN_GAS_EVID_SCALE = 0.0035597037f;
static const int CNN_GAS_EVID_ZERO_POINT = -128;

// Dequantization OUTPUT (int8)
static const float CNN_GAS_OUTPUT_SCALE = 0.0039062500f;
static const int CNN_GAS_OUTPUT_ZERO_POINT = -128;

#endif
