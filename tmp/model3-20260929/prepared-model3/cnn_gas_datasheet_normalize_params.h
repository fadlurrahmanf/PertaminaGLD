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

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.00157805f, 0.00365019f, 0.00445616f, -0.00332150f, -0.00966965f, -0.01475007f, -0.00294137f, -0.02736325f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {-0.00095305f, 0.67436564f, 0.00513223f, 0.93363893f, 0.63351053f, 0.56078547f, 0.88162357f, 0.68122643f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {1.08077812f, 0.71338451f, 0.30006492f, 0.92366111f, 0.89638156f, 0.00000000f, 0.33453214f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {13.65144920f, 10.01241398f, 6.63053751f, 11.92077351f, 6.80188608f, 3.00000000f, 6.59611559f};

// Kuantisasi INPUT ADC (int8)
static const float CNN_GAS_ADC_SCALE = 0.0038775746f;
static const int CNN_GAS_ADC_ZERO_POINT = -128;

// Kuantisasi INPUT evidence (int8)
static const float CNN_GAS_EVID_SCALE = 0.0038775746f;
static const int CNN_GAS_EVID_ZERO_POINT = -128;

// Dequantization OUTPUT (int8)
static const float CNN_GAS_OUTPUT_SCALE = 0.0039062500f;
static const int CNN_GAS_OUTPUT_ZERO_POINT = -128;

#endif
