#pragma once
#include <cstdint>
#include <cstdio>

struct BatteryText {
  char voltage[10];
  char percent[6];
};

inline BatteryText formatBattery(bool valid, int millivolts, int percent) {
  BatteryText result{};
  if (!valid || millivolts<2500 || millivolts>5000 || percent<0 || percent>100) {
    std::snprintf(result.voltage,sizeof(result.voltage),"--");
    std::snprintf(result.percent,sizeof(result.percent),"--");
  } else {
    const unsigned centivolts=unsigned(millivolts+5)/10;
    std::snprintf(result.voltage,sizeof(result.voltage),"%u.%02uV",centivolts/100,centivolts%100);
    std::snprintf(result.percent,sizeof(result.percent),"%d%%",percent);
  }
  return result;
}
