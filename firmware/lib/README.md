# Firmware Local Libraries

This directory is the source of truth for third-party Arduino/PlatformIO
libraries used by the firmware.

Do not add online `lib_deps` entries to the active firmware `platformio.ini`
files unless the library is intentionally being upgraded. Vendor the reviewed
library here first, then let PlatformIO resolve it from the local project.

Current pinned local libraries:

| Library | Local version | Notes |
| --- | --- | --- |
| ArduinoJson | 6.21.6 | Kept on v6 API for `StaticJsonDocument` firmware code. |
| PubSubClient | 2.8 | MQTT client used by GLD/Gateway runtime. |
| RadioLib | 7.1.1 | LoRa SX126x runtime. |

Changing `platformio.ini` invalidates more build cache than changing normal
headers/source, so board pin/profile changes should live in firmware headers
where possible.
