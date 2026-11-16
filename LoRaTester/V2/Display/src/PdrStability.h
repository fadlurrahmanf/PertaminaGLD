#pragma once
#include "../../CH/include/LoRaTesterWire.h"

namespace pdrstability {
enum class Result { Insufficient, Stable, Fluctuating };
inline Result classify(bool finished, const loratester::DirectionStats& s) {
  if (!finished || !s.available || !s.final || s.received<10 ||
      s.maxRssiDbm<s.minRssiDbm || s.maxSnrDb10<s.minSnrDb10)
    return Result::Insufficient;
  return (int(s.maxRssiDbm)-int(s.minRssiDbm)<=15 && int(s.maxSnrDb10)-int(s.minSnrDb10)<=50)
      ? Result::Stable : Result::Fluctuating;
}
inline const char* text(Result value) {
  return value==Result::Stable ? "STABIL" : value==Result::Fluctuating ? "BERFLUKTUASI" : "DATA KURANG";
}
}
