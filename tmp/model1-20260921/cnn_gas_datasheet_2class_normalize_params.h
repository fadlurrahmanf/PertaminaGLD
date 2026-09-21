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

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.00146476f, 0.03572841f, 0.00574261f, -0.00324865f, -0.01375208f, 0.03133556f, -0.00498847f, 0.07926339f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {-0.00075765f, 1.40544164f, 0.00645055f, 1.76242793f, 1.59203219f, 1.49846673f, 1.71751094f, 1.39785278f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {0.84980726f, 0.53512406f, 0.13707604f, 0.27438864f, 0.95769787f, 0.00000000f, 0.19844449f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {13.08199120f, 9.66271496f, 6.41652203f, 11.25782776f, 7.11596394f, 3.00000000f, 6.41374874f};

// Kuantisasi INPUT ADC (int8)
static const float CNN_GAS_ADC_SCALE = 0.0039215689f;
static const int CNN_GAS_ADC_ZERO_POINT = -128;

// Kuantisasi INPUT evidence (int8)
static const float CNN_GAS_EVID_SCALE = 0.0038727161f;
static const int CNN_GAS_EVID_ZERO_POINT = -128;

// Dequantization OUTPUT (int8)
static const float CNN_GAS_OUTPUT_SCALE = 0.0039062500f;
static const int CNN_GAS_OUTPUT_ZERO_POINT = -128;

#endif
