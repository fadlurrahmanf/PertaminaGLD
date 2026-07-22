#pragma once

#include <cstddef>
#include <cstdint>

#include "LoraMeshConfig.h"
#include "LoraStarConfig.h"

namespace pgl::config::ch {

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

#ifndef PGL_CH_ID
#define PGL_CH_ID 0x0010
#endif

#ifndef PGL_CH_ROOT_GATEWAY_ID
#define PGL_CH_ROOT_GATEWAY_ID 0x0001
#endif

#ifndef PGL_CH_BATT_START_MV
#define PGL_CH_BATT_START_MV 3500
#endif

#ifndef PGL_CH_BATT_RUN_MIN_MV
#define PGL_CH_BATT_RUN_MIN_MV 3150
#endif

#ifndef PGL_CH_BATT_CRITICAL_MV
#define PGL_CH_BATT_CRITICAL_MV 3100
#endif

#ifndef PGL_CH_FIELD_HELLO_INTERVAL_MS
#define PGL_CH_FIELD_HELLO_INTERVAL_MS 300000
#endif

#ifndef PGL_CH_FIELD_HELLO_JITTER_MS
#define PGL_CH_FIELD_HELLO_JITTER_MS 0
#endif

#ifndef PGL_CH_HELLO_ACK_TMO_MS
#define PGL_CH_HELLO_ACK_TMO_MS 1500
#endif

#ifndef PGL_CH_HELLO_RETRY_MAX
#define PGL_CH_HELLO_RETRY_MAX 3
#endif

#ifndef PGL_CH_HELLO_FAILURE_THRESHOLD
#define PGL_CH_HELLO_FAILURE_THRESHOLD 3
#endif

#ifndef PGL_CH_HELLO_REPROBE_MS
#define PGL_CH_HELLO_REPROBE_MS 30000
#endif

#ifndef PGL_CH_PARENT_HEALTH_TIMEOUT_MS
#define PGL_CH_PARENT_HEALTH_TIMEOUT_MS 960000
#endif

#ifndef PGL_CH_VBAT_READ_ONLY
#define PGL_CH_VBAT_READ_ONLY 0
#endif

// ID Cluster Head lokal. Harus cocok dengan GLD_CH_ID pada GLD yang terhubung
// dan dengan hopList/cluster yang dikirim Gateway untuk CH ini.
constexpr uint16_t CH_ID = PGL_CH_ID;

// ID Gateway root tujuan akhir MESH. Ini bukan parent statis; parent aktif
// dipilih otomatis lewat CH_CONFIG berdasarkan kandidat yang terdengar.
constexpr uint16_t ROOT_GATEWAY_ID = PGL_CH_ROOT_GATEWAY_ID;

// Tegangan baterai CH yang dilaporkan dalam response. 0xFFFF berarti unknown
// atau belum ada pembacaan baterai CH yang valid.
constexpr uint16_t CH_BATTERY_MV = 0xFFFF;

// Jumlah maksimum GLD yang disimpan di latest NodeCache RAM CH.
constexpr size_t NODE_CACHE_CAPACITY = 32;

// Jumlah maksimum alarm GLD yang bisa menunggu TX MESH.
constexpr size_t ALARM_QUEUE_CAPACITY = 8;

// Jumlah maksimum frame MESH yang bisa antre untuk dikirim ke parent/Gateway.
constexpr size_t TX_QUEUE_CAPACITY = 8;

// Jumlah maksimum pending downlink GLD yang disimpan per CH.
constexpr size_t DOWNLINK_STORE_CAPACITY = 16;

// Umur maksimum data GLD di NodeCache sebelum dianggap stale, dalam ms.
constexpr uint32_t NODE_STALE_AFTER_MS = 300000;

// Interval log/report ringkasan cache CH dalam ms.
constexpr uint32_t CACHE_REPORT_INTERVAL_MS = 10000;

// Battery ADC thresholds (mV). Formula: (avg_adc_mv * 3) + 200.
// START: batt harus stabil di atas ini (8x berturut) sebelum join.
// RUN_MIN: masuk LOW_POWER jika batt turun di bawah ini saat JOINED.
// CRITICAL: TX diblokir total di LOW_POWER jika batt di bawah ini.
constexpr uint16_t BATT_START_MV = PGL_CH_BATT_START_MV;
constexpr uint16_t BATT_RUN_MIN_MV = PGL_CH_BATT_RUN_MIN_MV;
constexpr uint16_t BATT_CRITICAL_MV = PGL_CH_BATT_CRITICAL_MV;

// Timeout tunggu alarm ACK dari parent (ms).
constexpr uint32_t ALARM_ACK_TMO_MS = 1500;
// Max retry kirim ulang alarm sebelum dianggap gagal dan dibuang.
constexpr uint8_t ALARM_RETRY_MAX = 5;

// Jumlah kegagalan alarm ACK sebelum trigger failover parent.
constexpr uint8_t PARENT_FAIL_TH = 3;
// Jumlah gagal ACK berturut-turut sebelum full restart.
constexpr uint8_t NO_ACK_RECOVERY_TH = 5;
// Cooldown minimum antar failover (ms) — cegah flip-flop.
constexpr uint32_t FAILOVER_CDN_MS = 60000;

// Interval CH_HELLO ke parent (ms). Satu sumber nilai ini dipakai untuk
// scheduling normal, join, failover, dan compile-time health checks.
constexpr uint32_t HELLO_INTERVAL_MS = PGL_CH_FIELD_HELLO_INTERVAL_MS;
constexpr uint32_t HELLO_JITTER_MS = PGL_CH_FIELD_HELLO_JITTER_MS;
constexpr uint32_t HELLO_ACK_TMO_MS = PGL_CH_HELLO_ACK_TMO_MS;
constexpr uint8_t HELLO_RETRY_MAX = PGL_CH_HELLO_RETRY_MAX;
constexpr uint8_t HELLO_FAILURE_THRESHOLD = PGL_CH_HELLO_FAILURE_THRESHOLD;
constexpr uint32_t HELLO_REPROBE_MS = PGL_CH_HELLO_REPROBE_MS;
constexpr bool VBAT_READ_ONLY = PGL_CH_VBAT_READ_ONLY != 0;

// Timeout tunggu CH_CONFIG_RESPONSE saat JOINING (ms).
constexpr uint32_t JOINING_TMO_MS = 15000;

// Interval antar CH_CONFIG_REQUEST dalam satu window discovery (ms). Nilai ini
// harus lebih besar dari slot CH_CONFIG_RESPONSE terjauh supaya request baru
// tidak menabrak response kandidat dari request sebelumnya.
constexpr uint32_t CFG_REQUEST_INTERVAL_MS = 5000;

// Anti-collision CH_CONFIG_RESPONSE. Setiap CH yang menjawab CH_CONFIG_REQUEST
// memakai slot deterministik dari CH_ID. Dengan base 200 ms, gap 280 ms, dan
// 16 slot, slot paling akhir berada di 4400 ms sehingga masih selesai sebelum
// request berikutnya pada interval 5000 ms.
constexpr uint32_t CFG_RESPONSE_BASE_DELAY_MS = 200;
constexpr uint32_t CFG_RESPONSE_SLOT_GAP_MS = 280;
constexpr uint8_t CFG_RESPONSE_SLOT_COUNT = 16;

// Interval dasar verifikasi route saat CH sudah JOINED. Dibuat konservatif
// agar jaringan 10+ CH memprioritaskan data/alarm/pull daripada maintenance.
constexpr uint32_t ROUTE_VERIFY_INTERVAL_MS = 600000;

// Tambahan jitter maksimum untuk verifikasi route (ms). Nilai ini mencegah
// beberapa CH melakukan scan CH_CONFIG bersamaan sehingga topology tidak
// berubah karena tabrakan/response window yang terlalu serempak.
constexpr uint32_t ROUTE_VERIFY_JITTER_MS = 300000;

// Durasi satu window scan CH_CONFIG untuk validasi parent (ms). 10 detik memberi
// sekitar dua round request/response dengan interval 5 detik.
constexpr uint32_t ROUTE_VERIFY_WINDOW_MS = 10000;

// Parent dianggap silent jika tidak terlihat dalam response verifikasi selama
// durasi ini.
constexpr uint32_t PARENT_HEALTH_TIMEOUT_MS = PGL_CH_PARENT_HEALTH_TIMEOUT_MS;

static_assert(
    static_cast<uint64_t>(PARENT_HEALTH_TIMEOUT_MS) >
        static_cast<uint64_t>(HELLO_INTERVAL_MS) + HELLO_JITTER_MS +
            (static_cast<uint64_t>(HELLO_RETRY_MAX) + 1ULL) * HELLO_ACK_TMO_MS,
    "CH parent health timeout must exceed one complete HELLO/ACK window");
static_assert(
    static_cast<uint64_t>(PARENT_HEALTH_TIMEOUT_MS) >
        static_cast<uint64_t>(ROUTE_VERIFY_INTERVAL_MS) + ROUTE_VERIFY_JITTER_MS + ROUTE_VERIFY_WINDOW_MS,
    "CH parent health timeout must exceed the worst-case legacy route verification window");

// Waktu minimum parent aktif dipertahankan sebelum boleh diganti oleh kandidat
// baru pada background verification. Failover tetap boleh pindah cepat jika
// parent benar-benar tidak sehat.
constexpr uint32_t PARENT_MIN_DWELL_MS = 300000;

// Kandidat baru hanya mengganti parent aktif jika RSSI lebih baik minimal
// margin ini, supaya route tidak flapping karena noise sesaat.
constexpr int16_t PARENT_SWITCH_MARGIN_DB = 15;

// Jika Gateway/root terdengar langsung dengan kualitas minimal ini, CH akan
// memprioritaskan Gateway sebagai parent utama. RSSI -95 dBm dengan SNR baik
// masih layak untuk LoRa bench, sedangkan link di bawah ini tetap menunggu
// parent CH agar route tidak dipaksa lewat direct link yang lemah/noisy.
constexpr int16_t GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM = -95;
constexpr int8_t  GATEWAY_DIRECT_PARENT_MIN_SNR_DB = 5;

// Gateway/root tidak boleh menjadi parent utama jika RSSI yang diterima CH
// lebih lemah dari floor ini. Ini berbeda dari direct-priority di atas:
// -95 dBm memprioritaskan Gateway, sedangkan -100 dBm adalah batas minimal
// supaya Gateway masih boleh dipakai sebagai parent sama sekali.
constexpr int16_t GATEWAY_PARENT_MIN_RSSI_DBM = -100;

// Gateway boleh disimpan sebagai alternate parent hanya jika link yang diterima
// CH masih di atas floor ini. Di bawah -100 dBm, Gateway dianggap terlalu lemah
// untuk jalur failover cadangan walaupun boleh tetap muncul sebagai discovery.
constexpr int16_t GATEWAY_ALT_PARENT_MIN_RSSI_DBM = -100;

// Parent/alt baru baru disimpan ke NVS setelah kombinasi yang sama terlihat
// stabil sebanyak jumlah scan ini.
constexpr uint8_t PARENT_NVS_STABLE_SCANS = 4;

// TTL pending downlink (ms) — command dibuang jika GLD tidak online dalam waktu ini.
constexpr uint32_t PENDING_TTL_MS = 1800000;

// Interval housekeeping (ms) — TTL cleanup + NodeCache expiry.
constexpr uint32_t HOUSEKEEPING_INTERVAL_MS = 60000;

// NodeCache entry expire setelah tidak ada data dari GLD (ms).
constexpr uint32_t CACHE_EXPIRE_MS = 3600000;

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------

// Tidak ada parent topologi yang di-flash. Nilai parent aktif berasal dari
// CH_CONFIG auto-discovery, lalu disimpan ke NVS sebagai cache hasil terakhir.
constexpr uint16_t DEFAULT_PARENT_ID = 0x0000;

// LoRa STAR (GLD <-> CH)
constexpr float STAR_FREQ_MHZ = pgl::config::lora::star::FREQ_MHZ;
constexpr float STAR_BW_KHZ = pgl::config::lora::star::BW_KHZ;
constexpr uint8_t STAR_SF = pgl::config::lora::star::SF;
constexpr uint8_t STAR_CR = pgl::config::lora::star::CR;
constexpr uint8_t STAR_SYNC_WORD = pgl::config::lora::star::SYNC_WORD;

// LoRa MESH (CH <-> Gateway / CH <-> CH)
constexpr float MESH_FREQ_MHZ = pgl::config::lora::mesh::FREQ_MHZ;
constexpr float MESH_BW_KHZ = pgl::config::lora::mesh::BW_KHZ;
constexpr uint8_t MESH_SF = pgl::config::lora::mesh::SF;
constexpr uint8_t MESH_CR = pgl::config::lora::mesh::CR;
constexpr uint8_t MESH_SYNC_WORD = pgl::config::lora::mesh::SYNC_WORD;

constexpr int8_t RADIO_TX_POWER_DBM = pgl::config::lora::mesh::TX_POWER_DBM;
constexpr uint16_t RADIO_PREAMBLE = pgl::config::lora::mesh::PREAMBLE;
constexpr float RADIO_TCXO_VOLTAGE = pgl::config::lora::mesh::TCXO_VOLTAGE;
constexpr float RADIO_XTAL_TCXO_VOLTAGE = pgl::config::lora::mesh::XTAL_TCXO_VOLTAGE;
constexpr uint32_t RADIO_SPI_HZ = pgl::config::lora::mesh::SPI_HZ;

}  // namespace pgl::config::ch
