#include "scaler_params.h"

// Pre-calculated mean and standard deviation values from StandardScaler,
// reordered to match physical channel order (BoardPins.h SENSOR_NAMES /
// design.md 8.6 Feature Order Alignment): MQ8, MQ135, MQ3, MQ5, MQ4, MQ7,
// MQ6, MQ2. Values are unchanged from the training pipeline; only the array
// index order was corrected to match hardware channel order.
const float feature_means[8] = {
    1.0096667, // ch0 MQ8V
    1.151226426190476, // ch1 MQ135V
    0.8747941047619049, // ch2 MQ3V
    3.120307857142857, // ch3 MQ5V
    0.849981730952381, // ch4 MQ4V
    0.8076531452380953, // ch5 MQ7V
    0.8551023309523809, // ch6 MQ6V
    0.9155299452380952, // ch7 MQ2V
};

const float feature_stds[8] = {
    0.9062927429386844, // ch0 MQ8V
    0.6836354136532563, // ch1 MQ135V
    0.5358539933242062, // ch2 MQ3V
    0.4780387180480543, // ch3 MQ5V
    0.7398564334928974, // ch4 MQ4V
    0.4721864452266815, // ch5 MQ7V
    0.669980479449558, // ch6 MQ6V
    0.8188832805994214, // ch7 MQ2V
};
