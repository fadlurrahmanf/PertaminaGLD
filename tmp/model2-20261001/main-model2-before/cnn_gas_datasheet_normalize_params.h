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

static const float CNN_GAS_ADC_MIN[CNN_GAS_N_ADC] = {-0.00171918f, 0.00474419f, 0.00503206f, -0.00356514f, -0.70599997f, -0.01504890f, -0.02467737f, -0.92699999f};
static const float CNN_GAS_ADC_MAX[CNN_GAS_N_ADC] = {0.98982418f, 1.19616985f, 0.01144060f, 1.43614924f, 0.90399998f, 1.09612346f, 1.13351798f, 0.94218522f};

static const float CNN_GAS_EVIDENCE_MIN[CNN_GAS_N_EVIDENCE] = {0.89459825f, 0.99232763f, 0.44798264f, 0.44855243f, 0.46162677f, 0.11229800f, 0.60108298f};
static const float CNN_GAS_EVIDENCE_MAX[CNN_GAS_N_EVIDENCE] = {9.78477383f, 7.92474604f, 5.56471586f, 6.55038452f, 4.92808867f, 3.22840333f, 7.36242008f};

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
