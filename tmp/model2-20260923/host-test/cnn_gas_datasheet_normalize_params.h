// Parameter normalisasi (min-max) & dequantization output -- model 2 kelas (Clean_Air, LPG)
#ifndef CNN_GAS_DATASHEET_2CLASS_NORMALIZE_PARAMS_H
#define CNN_GAS_DATASHEET_2CLASS_NORMALIZE_PARAMS_H

#define CNN_GAS_N_ADC 8
#define CNN_GAS_N_EVIDENCE 7
#define CNN_GAS_N_CLASSES 2

// Urutan fitur ADC WAJIB: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
static const char* CNN_GAS_ADC_NAMES[CNN_GAS_N_ADC] = {"MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"};

static const char* CNN_GAS_EVIDENCE_NAMES[CNN_GAS_N_EVIDENCE] = {"LPG_Combustible", "Methane_CNG", "CO", "Hydrogen", "Alcohol_Ethanol", "AirQuality_NH3_CO2", "Smoke"};

static const char* CNN_GAS_CLASS_NAMES[CNN_GAS_N_CLASSES] = {"Clean_Air", "LPG"};

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {0.02247964f, 0.03503217f, 0.00462895f, 0.00216922f, 0.01164770f, 0.02966303f, 0.02183222f, 0.05516692f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.05502787f, 0.20534357f, 0.00526757f, 0.28908956f, 0.20402069f, 0.29538319f, 0.29410881f, 0.30598706f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {2.05784273f, 1.37903297f, 0.39024752f, 1.05670118f, 1.32907557f, 0.00000000f, 0.22568689f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {12.55357647f, 9.44881821f, 6.05638599f, 10.30419064f, 6.84022665f, 3.00000000f, 6.03788280f};

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
