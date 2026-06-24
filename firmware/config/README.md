# Firmware Config

Folder ini adalah pusat parameter deploy firmware.

| File | Target | Isi |
|---|---|---|
| `LoraStarConfig.h` | GLD + CH | Radio STAR GLD-CH: frekuensi, BW, SF, CR, sync word, power, preamble, TCXO |
| `LoraMeshConfig.h` | CH + Gateway | Radio MESH CH-Gateway/CH-CH: frekuensi, BW, SF, CR, sync word, power, preamble, TCXO |
| `ServerConfig.h` | GLD + Gateway | WiFi/MQTT server dataset dan WiFi/MQTT server site |
| `GldConfig.h` | GLD | GLD identity, CH target, topic dataset/nulling, timing GLD, alias ke STAR + server dataset |
| `ChConfig.h` | CH | CH ID, root Gateway ID, default MESH parent, queue/cache capacity, alias ke STAR + MESH |
| `GwConfig.h` | Gateway | Gateway ID, topic site bridge, timing Gateway, alias ke MESH + server site |

Ubah parameter deployment di sini, bukan langsung di file `.cpp`.

Pembagian domain:

- LoRa STAR: `LoraStarConfig.h`
- LoRa MESH: `LoraMeshConfig.h`
- Server Dataset: `ServerConfig.h` namespace/macro `dataset`, dipakai GLD direct dataset/nulling MQTT
- Server Site: `ServerConfig.h` namespace/macro `site`, dipakai Gateway MQTT bridge

Gateway command tidak menyimpan default CH/GLD target. MQTT command harus membawa target eksplisit:

- Pull: `hopList` atau `cluster`
- Node command/downlink: `cluster` dan `node`

Catatan: credential production sebaiknya tidak disimpan permanen di repo.
Tahap berikutnya bisa memisahkan secret ke file local/ignored atau generator.
