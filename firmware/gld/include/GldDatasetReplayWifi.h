#pragma once

#if defined(PGL_GLD_DATASET_REPLAY) && PGL_GLD_DATASET_REPLAY
#include "GldDatasetWifi.h"

namespace pgl::gld::datasetreplaywifi {
using Sample = pgl::gld::datasetwifi::Sample;
using Capture = pgl::gld::datasetwifi::Capture;
using Ready = pgl::gld::datasetwifi::Ready;

bool begin(const char* deviceId, uint8_t nullingProfileId, Ready ready, Capture capture);
void poll();
}  // namespace pgl::gld::datasetreplaywifi
#endif
