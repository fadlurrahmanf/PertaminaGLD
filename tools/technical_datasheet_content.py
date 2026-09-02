from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BText:
    id: str
    en: str


def T(id_text: str, en_text: str) -> BText:
    return BText(id_text, en_text)


def resolve(value: Any, lang: str) -> Any:
    if isinstance(value, BText):
        return value.id if lang == "ID" else value.en
    if isinstance(value, dict):
        return {key: resolve(item, lang) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, lang) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve(item, lang) for item in value)
    return value


def page(title: BText, lead: BText, evidence: str, blocks: list[dict[str, Any]], basis: BText) -> dict[str, Any]:
    return {"title": title, "lead": lead, "evidence": evidence, "blocks": blocks, "basis": basis}


def cards(items: list[tuple[BText, BText]]) -> dict[str, Any]:
    return {"type": "cards", "items": items}


def diagram(nodes: list[tuple[BText, BText]], links: list[BText], caption: BText) -> dict[str, Any]:
    return {"type": "diagram", "nodes": nodes, "links": links, "caption": caption}


def kv(rows: list[tuple[BText, BText]], key_width_mm: float = 49) -> dict[str, Any]:
    return {"type": "kv", "rows": rows, "key_width_mm": key_width_mm}


def table(headers: list[BText], rows: list[list[Any]], widths: list[float] | None = None) -> dict[str, Any]:
    return {"type": "table", "headers": headers, "rows": rows, "widths": widths}


def bullets(items: list[BText]) -> dict[str, Any]:
    return {"type": "bullets", "items": items}


def note(text: BText, tone: str = "info") -> dict[str, Any]:
    return {"type": "note", "text": text, "tone": tone}


def layers(items: list[tuple[BText, BText]], caption: BText) -> dict[str, Any]:
    return {"type": "layers", "items": items, "caption": caption}


def sequence(actors: list[BText], steps: list[tuple[int, int, BText]], caption: BText) -> dict[str, Any]:
    return {"type": "sequence", "actors": actors, "steps": steps, "caption": caption}


def bar(labels: list[str], values: list[float], unit: str, caption: BText) -> dict[str, Any]:
    return {"type": "bar", "labels": labels, "values": values, "unit": unit, "caption": caption}


def common_meta(
    slug: str,
    product: str,
    status: BText,
    firmware: str,
    subtitle: BText,
    cover_nodes: list[tuple[BText, BText]],
    cover_links: list[BText],
    facts: list[tuple[BText, BText]],
    abbreviations: list[tuple[str, BText]],
) -> dict[str, Any]:
    return {
        "slug": slug,
        "product": product,
        "status": status,
        "firmware": firmware,
        "subtitle": subtitle,
        "cover_nodes": cover_nodes,
        "cover_links": cover_links,
        "facts": facts,
        "abbreviations": abbreviations,
        "revision": "4.0",
        "issuer": "Lab IoT ITB",
    }


def gas_document() -> dict[str, Any]:
    d = common_meta(
        slug="GasleakDetector",
        product="GasleakDetector",
        status=T("Prototipe Engineering", "Engineering Prototype"),
        firmware="Firmware 0.8.19 | Protocol 0.2.0",
        subtitle=T(
            "Perangkat sensing delapan channel dengan pemrosesan lokal, alarm 24 V, LoRa STAR, dan RS-485.",
            "Eight-channel sensing device with local processing, 24 V alarm output, LoRa STAR, and RS-485.",
        ),
        cover_nodes=[
            (T("8 channel sensor", "8 sensor channels"), T("Seri MQ Winsen", "Winsen MQ series")),
            (T("Akuisisi", "Acquisition"), T("ADS1256", "ADS1256")),
            (T("Pemrosesan", "Processing"), T("ESP32-S3", "ESP32-S3")),
            (T("Komunikasi", "Communication"), T("LoRa / RS-485", "LoRa / RS-485")),
            (T("Keluaran", "Output"), T("Alarm 24 V", "24 V alarm")),
        ],
        cover_links=[T("analog", "analog"), T("SPI", "SPI"), T("data", "data"), T("event", "event")],
        facts=[
            (T("CHANNEL SENSOR", "SENSOR CHANNELS"), T("8 channel", "8 channels")),
            (T("CATU UTAMA", "MAIN SUPPLY"), T("24 VDC nominal", "24 VDC nominal")),
            (T("RF", "RF"), T("920-923 MHz", "920-923 MHz")),
            (T("ALARM", "ALARM"), T("AUTO, keluaran 24 V", "AUTO, 24 V output")),
        ],
        abbreviations=[
            ("ADC", T("Analog-to-Digital Converter", "Analog-to-Digital Converter")),
            ("DAC", T("Digital-to-Analog Converter", "Digital-to-Analog Converter")),
            ("NVM", T("Memori non-volatile", "Non-volatile memory")),
            ("RF", T("Radio frequency", "Radio frequency")),
            ("RTU", T("Remote Terminal Unit pada Modbus", "Remote Terminal Unit in Modbus")),
            ("STAR", T("Domain radio endpoint-ke-CH", "Endpoint-to-CH radio domain")),
            ("TLS", T("Transport Layer Security", "Transport Layer Security")),
        ],
    )

    d["chapters"] = [
        page(
            T("Ikhtisar produk", "Product overview"),
            T("GasleakDetector menggabungkan sensing multi-channel, pemrosesan lokal, alarm fisik, dan dua antarmuka komunikasi dalam satu endpoint lapangan.",
              "GasleakDetector combines multi-channel sensing, local processing, a physical alarm output, and two communication interfaces in one field endpoint."),
            "implemented",
            [
                cards([
                    (T("Arsitektur", "Architecture"), T("8 channel analog", "8 analog channels")),
                    (T("Kontrol", "Control"), T("ESP32-S3", "ESP32-S3")),
                    (T("Jalur utama", "Primary link"), T("LoRa STAR ke CH", "LoRa STAR to CH")),
                    (T("Jalur lokal", "Local link"), T("RS-485 Modbus", "RS-485 Modbus")),
                ]),
                bullets([
                    T("Akuisisi delapan channel sensor dengan pengaktifan daya per channel.", "Acquires eight sensor channels with per-channel power control."),
                    T("Menjalankan pemrosesan lokal pada mode Running/Inference.", "Runs local processing in Running/Inference mode."),
                    T("Mengirim telemetri dan event alarm ke CH melalui LoRa STAR.", "Sends telemetry and alarm events to CH over LoRa STAR."),
                    T("Menyediakan keluaran steady 24 V untuk perangkat alarm eksternal.", "Provides a steady 24 V output for an external alarm device."),
                ]),
            ],
            T("Schematic/PCB, firmware produk, dan konfigurasi produk.",
              "Product schematic/PCB, firmware, and product configuration."),
        ),
        page(
            T("Arsitektur fungsional", "Functional architecture"),
            T("Jalur utama bergerak dari sensor menuju akuisisi, pemrosesan, komunikasi, lalu alarm atau telemetri.",
              "The primary path runs from sensors through acquisition and processing to communication, alarm, or telemetry."),
            "implemented",
            [
                diagram([
                    (T("Sensor MQ", "MQ sensors"), T("8 channel", "8 channels")),
                    (T("ADS1256", "ADS1256"), T("ADC 24-bit", "24-bit ADC")),
                    (T("ESP32-S3", "ESP32-S3"), T("Kontrol + inferensi", "Control + inference")),
                    (T("LoRa STAR", "LoRa STAR"), T("Uplink ke CH", "Uplink to CH")),
                    (T("Alarm", "Alarm"), T("Output 24 V", "24 V output")),
                ], [T("analog", "analog"), T("SPI", "SPI"), T("frame", "frame"), T("event", "event")],
                   T("Gambar 1. Jalur fungsi utama GasleakDetector.", "Figure 1. Primary GasleakDetector functional path.")),
                kv([
                    (T("Pemrosesan lokal", "Local processing"), T("Scanning, validasi input, inferensi, status, dan pembentukan frame.", "Scanning, input validation, inference, status, and frame construction.")),
                    (T("Komunikasi", "Communication"), T("LoRa STAR sebagai jalur field utama; RS-485 sebagai antarmuka lokal read-only.", "LoRa STAR as the primary field path; RS-485 as a local read-only interface.")),
                    (T("Alarm", "Alarm"), T("Mode AUTO mengikuti hasil inferensi alarm valid; MANUAL hanya sesi pengujian.", "AUTO follows a valid alarm inference; MANUAL is restricted to a test session.")),
                ]),
            ],
            T("Basis: implementasi runtime GasleakDetector dan pemetaan perangkat keras produk.", "Basis: GasleakDetector runtime implementation and product hardware mapping."),
        ),
        page(
            T("Komponen perangkat keras utama", "Primary hardware components"),
            T("Tabel ini mengidentifikasi komponen yang terlihat pada desain; rating komponen tidak otomatis menjadi rating produk rakitan.",
              "This table identifies components present in the design; component ratings do not automatically become assembled-product ratings."),
            "component",
            [
                table([T("Fungsi", "Function"), T("Komponen", "Component"), T("Peran pada produk", "Product role")], [
                    [T("MCU", "MCU"), "ESP32-S3-WROOM-1U-N16R8", T("Kontrol, komunikasi, dan pemrosesan lokal", "Control, communication, and local processing")],
                    [T("ADC", "ADC"), "ADS1256IDBR", T("Akuisisi analog multi-channel 24-bit", "24-bit multi-channel analog acquisition")],
                    [T("Lingkungan", "Environment"), "SHT40-AD1B-R2", T("Pemantauan suhu dan kelembapan tambahan", "Auxiliary temperature and humidity sensing")],
                    [T("Radio", "Radio"), "E22-900MM22S", T("Antarmuka LoRa STAR", "LoRa STAR interface")],
                    ["RS-485", "THVD1410DR", T("Physical layer Modbus RTU", "Modbus RTU physical layer")],
                    [T("Ekspander", "Expander"), "PCF8574T", T("Kontrol enable channel sensor", "Sensor-channel enable control")],
                ], [0.20, 0.29, 0.51]),
            ],
            T("Basis: design records dan daftar komponen pada schematic/PCB.", "Basis: design records and schematic/PCB component records."),
        ),
        page(
            T("Pemetaan delapan channel sensor", "Eight-channel sensor map"),
            T("Urutan channel adalah bagian dari kontrak akuisisi dan pemrosesan; nilai performa gas tidak disimpulkan dari nama sensor.",
              "Channel order is part of the acquisition and processing contract; gas performance is not inferred from sensor names."),
            "confirmed",
            [
                table([T("Channel", "Channel"), T("Sensor", "Sensor"), T("Identifikasi", "Identification")], [
                    ["1", "MQ-8", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["2", "MQ-135", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["3", "MQ-3", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["4", "MQ-5", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["5", "MQ-4", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["6", "MQ-7", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["7", "MQ-6", T("Seri MQ Winsen", "Winsen MQ series")],
                    ["8", "MQ-2", T("Seri MQ Winsen", "Winsen MQ series")],
                ], [0.15, 0.22, 0.63]),
            ],
            T("Urutan channel firmware dan konfigurasi sensor perangkat.", "Firmware channel order and device sensor configuration."),
        ),
        page(
            T("Kontrol daya channel dan nulling", "Channel power control and nulling"),
            T("Setiap channel memiliki jalur kontrol yang memungkinkan pengaktifan sensor dan proses nulling secara terarah.",
              "Each channel has a control path that enables directed sensor activation and nulling."),
            "implemented",
            [
                layers([
                    (T("Lapisan kontrol", "Control layer"), T("ESP32-S3 mengatur enable dan urutan layanan", "ESP32-S3 controls enables and service sequence")),
                    (T("Ekspansi I/O", "I/O expansion"), T("PCF8574T memetakan delapan sinyal enable", "PCF8574T maps eight enable signals")),
                    (T("Switch daya", "Power switch"), T("TPS22919 mengendalikan suplai per channel", "TPS22919 controls supply per channel")),
                    (T("Nulling analog", "Analog nulling"), T("DAC dan multiplexer mengatur koreksi channel", "DAC and multiplexer apply channel correction")),
                ], T("Gambar 2. Lapisan kontrol daya dan nulling.", "Figure 2. Power-control and nulling layers.")),
                bullets([
                    T("Mode Nulling adalah fungsi engineering terpisah dari mode operasi normal.", "Nulling mode is an engineering function separate from normal operation."),
                    T("Status channel dan hasil nulling tersedia untuk readback engineering.", "Channel status and nulling results are available for engineering readback."),
                ]),
                note(T("Prosedur nulling mencakup delapan channel, penyimpanan profile, reboot, dan penerapan kembali profile yang valid.",
                       "The nulling procedure covers all eight channels, profile storage, reboot, and re-application of a valid profile.")),
            ],
            T("Schematic produk dan implementasi kontrol channel/nulling pada firmware.", "Product schematic and firmware channel-control/nulling implementation."),
        ),
        page(
            T("Jalur akuisisi analog", "Analog acquisition path"),
            T("Akuisisi menggunakan ADC eksternal 24-bit dan dikendalikan secara terurut oleh firmware.",
              "Acquisition uses an external 24-bit ADC under sequenced firmware control."),
            "implemented",
            [
                diagram([
                    (T("Keluaran sensor", "Sensor output"), T("8 input analog", "8 analog inputs")),
                    (T("Conditioning", "Conditioning"), T("Jalur analog PCB", "PCB analog path")),
                    ("ADS1256", T("24-bit ADC", "24-bit ADC")),
                    (T("SPI", "SPI"), T("1.92 MHz", "1.92 MHz")),
                    ("ESP32-S3", T("Filter + status", "Filter + status")),
                ], [T("tegangan", "voltage"), T("mux", "mux"), T("digital", "digital"), T("sample", "sample")],
                   T("Gambar 3. Rantai akuisisi analog yang diimplementasikan.", "Figure 3. Implemented analog acquisition chain.")),
                kv([
                    (T("ADC", "ADC"), T("Texas Instruments ADS1256IDBR, resolusi komponen 24-bit.", "Texas Instruments ADS1256IDBR, 24-bit component resolution.")),
                    (T("Clock SPI firmware", "Firmware SPI clock"), "1,920,000 Hz"),
                    (T("Output pemrosesan", "Processing output"), T("Nilai channel, validitas, fault status, dan input untuk inferensi.", "Channel values, validity, fault status, and inference input.")),
                ]),
            ],
            T("Basis: part number schematic dan konfigurasi SPI pada source akuisisi.", "Basis: schematic part number and acquisition-source SPI configuration."),
        ),
        page(
            T("Konfigurasi ADC dan sampling", "ADC and sampling configuration"),
            T("Firmware mengendalikan multiplexer, gain, kalibrasi, dan penerimaan sampel secara eksplisit.",
              "Firmware explicitly controls multiplexing, gain, calibration, and sample acceptance."),
            "implemented",
            [
                table([T("Parameter", "Parameter"), T("Nilai implementasi", "Implemented value"), T("Makna", "Meaning")], [
                    [T("ADS1256 data rate", "ADS1256 data rate"), "30,000 SPS", T("Konfigurasi ADC component", "ADC component configuration")],
                    [T("VREF firmware", "Firmware VREF"), "2.497 V", T("Nilai conversion source", "Source conversion value")],
                    [T("PGA", "PGA"), "1x - 64x adaptive", T("Gain dipilih sesuai input", "Gain selected according to input")],
                    [T("Calibration", "Calibration"), T("Self-calibration", "Self-calibration"), T("Dilakukan pada initialization path", "Performed in the initialization path")],
                    [T("Setelah mux switch", "After mux switch"), T("Konversi pertama dibuang", "First conversion discarded"), T("Mengurangi carry-over setelah pergantian channel", "Reduces carry-over after channel switching")],
                    [T("Scan cadence default", "Default scan cadence"), "500 ms", T("Interval siklus akuisisi firmware", "Firmware acquisition-cycle interval")],
                ], [0.27, 0.25, 0.48]),
            ],
            T("ADS1256 reader configuration dan default scan configuration.", "ADS1256 reader configuration and default scan configuration."),
        ),
        page(
            T("Penyaringan dan perilaku batch valid", "Filtering and valid-batch behavior"),
            T("Pemrosesan hanya mengkomit batch bila seluruh delapan channel memenuhi validitas dan saturation checks.",
              "Processing commits a batch only when all eight channels pass validity and saturation checks."),
            "implemented",
            [
                layers([
                    (T("Scan 8 channel", "Scan 8 channels"), T("Multiplexed sequential acquisition", "Multiplexed sequential acquisition")),
                    (T("Per-channel checks", "Per-channel checks"), T("Read success, validity, saturation", "Read success, validity, saturation")),
                    (T("Batch gate", "Batch gate"), T("Harus 8/8 valid dan non-saturated", "Must be 8/8 valid and non-saturated")),
                    (T("Moving average", "Moving average"), T("10 sampel per channel", "10 samples per channel")),
                    (T("Commit", "Commit"), T("Data baru menjadi input pemrosesan/inferensi", "Data becomes processing/inference input")),
                ], T("Gambar 4. Gate penerimaan satu batch sensor.", "Figure 4. Sensor-batch acceptance gates.")),
                note(T("Satu channel invalid membuat keseluruhan batch invalid.",
                       "One invalid channel makes the complete batch invalid."), "success"),
            ],
            T("Moving-average implementation dan 8/8 valid non-saturated commit gate.", "Moving-average implementation and 8/8 valid non-saturated commit gate."),
        ),
        page(
            T("Gerbang validitas inferensi", "Inference-validity gates"),
            T("Hasil classifier hanya dianggap valid bila acquisition, model, nulling, dan DAC state semuanya siap.",
              "A classifier result is valid only when acquisition, model, nulling, and DAC state are all ready."),
            "implemented",
            [
                layers([
                    (T("Sensor gate", "Sensor gate"), T("8/8 channel valid dan non-saturated", "8/8 channels valid and non-saturated")),
                    (T("Filter gate", "Filter gate"), T("Moving average telah primed", "Moving average is primed")),
                    (T("Model gate", "Model gate"), T("ML runtime dan model metadata siap", "ML runtime and model metadata are ready")),
                    (T("Nulling gate", "Nulling gate"), T("Profile diterapkan dan terikat ke model", "Profile is applied and bound to the model")),
                    (T("DAC gate", "DAC gate"), T("Output nulling terverifikasi", "Nulling output is verified")),
                    (T("Valid inference", "Valid inference"), T("Baru dapat mempengaruhi AUTO alarm", "Only then may affect AUTO alarm")),
                ], T("Gambar 5. Gate berlapis sebelum inference dinyatakan valid.", "Figure 5. Layered gates before inference is declared valid.")),
            ],
            T("Inference preconditions pada runtime dan binding nulling/model.", "Runtime inference preconditions and nulling/model binding."),
        ),
        page(
            T("Keluaran klasifikasi yang dikonfigurasi", "Configured classification outputs"),
            T("Model inferensi menyediakan empat label klasifikasi dan satu nilai confidence.",
              "The inference model provides four classification labels and a confidence value."),
            "implemented",
            [
                cards([
                    (T("Class 0", "Class 0"), "Clean Air"),
                    (T("Class 1", "Class 1"), "LPG"),
                    (T("Class 2", "Class 2"), "H2"),
                    (T("Class 3", "Class 3"), "CO2"),
                ]),
                table([T("Output", "Output"), T("Arti", "Meaning")], [
                    [T("Class label", "Class label"), T("Hasil klasifikasi model yang dikonfigurasi", "Configured model classification result")],
                    [T("Confidence", "Confidence"), T("Nilai confidence classifier", "Classifier confidence value")],
                ], [0.28, 0.72]),
            ],
            T("Model metadata/class map dan batas evidence gas-performance.", "Model metadata/class map and gas-performance evidence boundary."),
        ),
        page(
            T("Pemantauan suhu dan kelembapan tambahan", "Auxiliary temperature and humidity sensing"),
            T("SHT40 menyediakan data suhu dan kelembapan tambahan untuk status dan pemrosesan.",
              "SHT40 provides auxiliary temperature and humidity data for status and processing."),
            "component",
            [
                cards([
                    (T("Komponen", "Component"), "SHT40-AD1B-R2"),
                    (T("Antarmuka", "Interface"), "I2C"),
                    (T("Besaran", "Quantities"), T("Suhu + RH", "Temperature + RH")),
                    (T("Peran", "Role"), T("Masukan tambahan", "Auxiliary input")),
                ]),
                bullets([
                    T("Firmware mengonversi raw temperature dan humidity dari sensor digital.", "Firmware converts raw digital temperature and humidity values."),
                    T("Nilai dapat disertakan pada status/telemetri sesuai jalur firmware.", "Values can be included in status/telemetry according to the firmware path."),
                ]),
                note(T("Referensi resmi komponen: Sensirion SHT40 product page dan SHT4x datasheet.",
                       "Official component reference: Sensirion SHT40 product page and SHT4x datasheet.")),
            ],
            T("Basis: schematic, source pembacaan SHT40, dan dokumentasi resmi Sensirion.", "Basis: schematic, SHT40 reading source, and official Sensirion documentation."),
        ),
        page(
            T("Mode operasi firmware", "Firmware operating modes"),
            T("Mode dipisahkan berdasarkan tujuan operasi, pengumpulan data, dan commissioning.",
              "Modes are separated by operational, data-collection, and commissioning purpose."),
            "implemented",
            [
                table([T("Mode", "Mode"), T("Tujuan", "Purpose"), T("Batas penggunaan", "Use boundary")], [
                    [T("Running / Inference", "Running / Inference"), T("Scanning dan inferensi lokal", "Scanning and local inference"), T("Mode operasi normal setelah boot", "Normal operating mode after boot")],
                    [T("Dataset", "Dataset"), T("Pengumpulan data engineering", "Engineering data collection"), T("Tidak menjadi alarm produksi", "Not a production-alarm path")],
                    [T("Nulling", "Nulling"), T("Koreksi baseline per channel", "Per-channel baseline correction"), T("Memerlukan alur engineering", "Requires engineering workflow")],
                    [T("Battery session", "Battery session"), T("Siklus operasi saat sumber baterai dipilih", "Operating cycle when battery source is selected"), T("Perilaku daya bergantung hardware", "Power behavior depends on hardware")],
                    [T("Alarm MANUAL", "MANUAL alarm"), T("Uji beban alarm", "Alarm-load test"), T("Session-only; AUTO kembali pada boot", "Session-only; AUTO returns at boot")],
                ], [0.22, 0.38, 0.40]),
                note(T("Mode AUTO adalah default produk setiap boot. Mode MANUAL tidak disimpan sebagai pilihan boot permanen.",
                       "AUTO is the product default at every boot. MANUAL is not stored as a permanent boot selection."), "success"),
            ],
            T("Basis: state/mode handling pada runtime dan kontrak kontrol Operator Hub.", "Basis: runtime state/mode handling and Operator Hub control contract."),
        ),
        page(
            T("Urutan boot dan sesi normal", "Boot and normal-session sequence"),
            T("Urutan ini menunjukkan dependency utama sebelum perangkat dapat menghasilkan data operasi.",
              "This sequence shows the primary dependencies before the device can produce operational data."),
            "implemented",
            [
                sequence([T("Daya", "Power"), T("Firmware", "Firmware"), T("Sensor", "Sensors"), T("Radio", "Radio"), T("CH", "CH")], [
                    (0, 1, T("Power-up / reset", "Power-up / reset")),
                    (1, 2, T("Init + enable channel", "Init + enable channels")),
                    (2, 1, T("Sample + validasi", "Sample + validation")),
                    (1, 3, T("Bangun frame", "Build frame")),
                    (3, 4, T("LoRa STAR TX", "LoRa STAR TX")),
                ], T("Gambar 6. Urutan boot sampai pengiriman telemetri.", "Figure 6. Boot-to-telemetry sequence.")),
                bullets([
                    T("Kegagalan inisialisasi atau validasi ditampilkan melalui status diagnostik.", "Initialization or validation failures are exposed through diagnostic status."),
                    T("Konfigurasi runtime dapat berasal dari default firmware atau NVM yang tervalidasi.", "Runtime configuration may come from firmware defaults or validated NVM."),
                    T("Konfigurasi RF aktual harus diperiksa melalui readback perangkat.", "Actual RF configuration must be checked through device readback."),
                ]),
            ],
            T("Basis: setup/loop runtime, status JSON, dan konfigurasi LoRa tersimpan.", "Basis: runtime setup/loop, status JSON, and stored LoRa configuration."),
        ),
        page(
            T("Arsitektur alarm lokal", "Local alarm architecture"),
            T("Firmware mengendalikan satu keluaran alarm 24 V; pola bunyi/lampu dihasilkan oleh perangkat alarm eksternal.",
              "Firmware controls one 24 V alarm output; audible/visual cadence is generated by the external alarm device."),
            "tested",
            [
                diagram([
                    (T("Inferensi valid", "Valid inference"), T("Alarm state", "Alarm state")),
                    (T("Mode AUTO", "AUTO mode"), T("Default boot", "Boot default")),
                    (T("Kontrol alarm", "Alarm control"), T("Keluaran ON/OFF", "ON/OFF output")),
                    (T("Boost/output", "Boost/output"), T("Steady 24 V", "Steady 24 V")),
                    (T("Buzzer + LED", "Buzzer + LED"), T("1 s ON / 1 s OFF", "1 s ON / 1 s OFF")),
                ], [T("trigger", "trigger"), T("enable", "enable"), T("drive", "drive"), T("di unit alarm", "in alarm unit")],
                   T("Gambar 7. Batas tanggung jawab firmware dan perangkat alarm.", "Figure 7. Firmware and external-alarm responsibility boundary.")),
                kv([
                    (T("Perilaku firmware", "Firmware behavior"), T("Keluaran steady ON/OFF pada 24 V.", "Steady 24 V ON/OFF output.")),
                    (T("Perilaku beban", "Load behavior"), T("Buzzer dan LED berkedip otomatis 1 detik ON, 1 detik OFF saat diberi 24 V steady.", "Buzzer and LED automatically cycle 1 second ON, 1 second OFF from steady 24 V.")),
                    (T("Mode uji", "Test mode"), T("MANUAL session-only, dapat dipilih melalui Operator Hub.", "Session-only MANUAL mode selectable through Operator Hub.")),
                ]),
                note(T("Keluaran 24 V telah diuji dengan perangkat alarm eksternal berupa buzzer dan LED.",
                       "The 24 V output has been tested with an external buzzer-and-LED alarm device."), "success"),
            ],
            T("Kontrak AUTO/MANUAL, kontrol keluaran alarm, dan uji beban alarm.", "AUTO/MANUAL contract, alarm-output control, and alarm-load test."),
        ),
        page(
            T("Arsitektur catu daya", "Power architecture"),
            T("Produk menerima 24 VDC sebagai catu utama dan memiliki jalur operasi baterai terpisah.",
              "The product accepts 24 VDC as its main supply and includes a separate battery operating path."),
            "confirmed",
            [
                layers([
                    (T("Masukan utama", "Main input"), T("24 VDC nominal", "24 VDC nominal")),
                    (T("Pemilihan sumber", "Source selection"), T("Baterai diprioritaskan bila terdeteksi; selain itu 24 V/5 V sesuai status hardware", "Battery is selected when detected; otherwise 24 V/5 V follows hardware status")),
                    (T("Rail internal", "Internal rails"), T("Konversi untuk MCU, analog, radio, dan sensor", "Conversion for MCU, analog, radio, and sensors")),
                    (T("Output alarm", "Alarm output"), T("24 V steady saat aktif", "Steady 24 V when active")),
                ], T("Gambar 8. Domain daya utama produk.", "Figure 8. Primary product power domains.")),
                table(
                    [T("Parameter elektrik", "Electrical parameter"), T("Nilai", "Value")],
                    [
                        [T("Rating nominal produk", "Nominal product input"), "24 VDC"],
                        [T("Arus terukur", "Measured current"), T("Hingga 300 mA steady pada delapan sensor aktif", "Up to 300 mA steady with eight sensors active")],
                    ],
                    [0.36, 0.64],
                ),
            ],
            T("Basis: schematic/power source logic dan pengukuran internal pada input 24 V.", "Basis: schematic/power-source logic and internal measurement at the 24 V input."),
        ),
        page(
            T("Konsumsi arus pada input 24 V", "Current consumption at the 24 V input"),
            T("Nilai adalah pengukuran steady-state ketika jumlah sensor aktif dinaikkan dari nol sampai delapan.",
              "Values are steady-state measurements as the number of active sensors increases from zero to eight."),
            "measured",
            [
                bar(["0", "1", "2", "3", "4", "5", "6", "7", "8"], [2.56, 60, 100, 130, 160, 210, 240, 270, 300], "mA",
                    T("Gambar 9. Arus steady-state terhadap jumlah sensor aktif.", "Figure 9. Steady-state current versus active sensor count.")),
                table([T("Sensor aktif", "Active sensors"), "0", "1", "2", "3", "4", "5", "6", "7", "8"], [
                    [T("Arus (mA)", "Current (mA)"), "2.56", "60", "100", "130", "160", "210", "240", "270", "300"]
                ], [0.20, 0.088, 0.088, 0.088, 0.088, 0.088, 0.088, 0.088, 0.088, 0.088]),
                note(T("Pengukuran dilakukan dengan alat ukur diseri pada jalur 24 V+ dari PSU ke board. Nilai 300 mA adalah steady-state, bukan peak atau rating PSU.",
                       "The meter was placed in series in the 24 V+ path from PSU to board. The 300 mA value is steady-state, not peak current or PSU rating."), "success"),
            ],
            T("Pengukuran steady-state pada jalur input 24 V perangkat.", "Steady-state measurement on the device 24 V input path."),
        ),
        page(
            T("Konfigurasi baterai", "Battery configuration"),
            T("Mode baterai menggunakan tujuh sel 18650 yang disusun paralel.",
              "Battery mode uses seven 18650 cells connected in parallel."),
            "confirmed",
            [
                diagram([
                    (T("7 x sel", "7 x cells"), T("LiitoKala", "LiitoKala")),
                    (T("Topologi", "Topology"), T("Paralel", "Parallel")),
                    (T("Battery rail", "Battery rail"), T("Tegangan satu sel", "Single-cell voltage")),
                    (T("Power logic", "Power logic"), T("Mode baterai", "Battery mode")),
                ], [T("gabung", "combine"), T("tegangan", "voltage"), T("supply", "supply")],
                   T("Gambar 10. Topologi baterai GasleakDetector.", "Figure 10. GasleakDetector battery topology.")),
                kv([
                    (T("Jenis sel", "Cell type"), T("LiitoKala Lii-King4000 18650, label 4000 mAh per sel", "LiitoKala Lii-King4000 18650, 4000 mAh label per cell")),
                    (T("Jumlah", "Quantity"), "7"),
                    (T("Susunan", "Arrangement"), T("Paralel", "Parallel")),
                ]),
                note(T("Angka 4000 mAh adalah nilai label sel, bukan hasil capacity test pada pack produk.",
                       "The 4000 mAh figure is a cell-label value, not a product-pack capacity-test result."), "caution"),
            ],
            T("Konfigurasi baterai fisik dan identifikasi label sel.", "Physical battery configuration and cell-label identification."),
        ),
        page(
            T("Pemantauan tegangan baterai", "Battery-voltage monitoring"),
            T("Firmware melaporkan battery voltage dan diagnostic flags, tetapi tidak memakai flag tersebut sebagai active cutoff.",
              "Firmware reports battery voltage and diagnostic flags but does not use those flags as an active cutoff."),
            "implemented",
            [
                table([T("Diagnostic", "Diagnostic"), T("Threshold source", "Source threshold"), T("Perilaku", "Behavior")], [
                    [T("Battery low", "Battery low"), "3.50 V", T("Status/flag; tidak menghentikan operasi", "Status/flag; does not stop operation")],
                    [T("Battery critical", "Battery critical"), "3.30 V", T("Status/flag; bukan physical cutoff", "Status/flag; not a physical cutoff")],
                ], [0.28, 0.27, 0.45]),
                layers([
                    (T("Voltage read", "Voltage read"), T("Battery monitor acquisition", "Battery-monitor acquisition")),
                    (T("Diagnostic compare", "Diagnostic compare"), T("Low / critical flags", "Low / critical flags")),
                    (T("Status output", "Status output"), T("Nilai dan flag tersedia untuk readback", "Value and flags available for readback")),
                    (T("Protection boundary", "Protection boundary"), T("Tidak memutus pack atau rail secara aktif", "Does not actively disconnect pack or rail")),
                ], T("Gambar 11. Monitoring diagnostik versus proteksi aktif.", "Figure 11. Diagnostic monitoring versus active protection.")),
            ],
            T("Battery-monitor thresholds, status reporting, dan absence of active cutoff behavior.", "Battery-monitor thresholds, status reporting, and absence of active-cutoff behavior."),
        ),
        page(
            T("Antarmuka LoRa STAR", "LoRa STAR interface"),
            T("LoRa STAR menghubungkan GasleakDetector ke radio STAR pada CH.",
              "LoRa STAR connects GasleakDetector to the STAR radio on CH."),
            "implemented",
            [
                table([T("Parameter", "Parameter"), T("Default firmware", "Firmware default"), T("Catatan", "Note")], [
                    [T("Carrier", "Carrier"), "920.0 MHz", T("Input konfigurasi dibatasi 920-923 MHz inclusive", "Configuration input constrained to 920-923 MHz inclusive")],
                    [T("Bandwidth", "Bandwidth"), "125 kHz", T("Harus sama pada GasleakDetector dan CH STAR", "Must match GasleakDetector and CH STAR")],
                    [T("Spreading factor", "Spreading factor"), "SF7", T("Default domain STAR", "STAR-domain default")],
                    [T("Coding rate", "Coding rate"), "4/5", T("Nilai konfigurasi firmware CR=5", "Firmware configuration value CR=5")],
                    [T("TX power", "TX power"), "17 dBm", T("Setting firmware, bukan output terukur", "Firmware setting, not measured output")],
                    [T("Preamble", "Preamble"), "8", T("Default firmware", "Firmware default")],
                    [T("Antena", "Antenna"), "3 dBi", T("Konfigurasi produk", "Product configuration")],
                ], [0.25, 0.25, 0.50]),
                note(T("Konfigurasi aktif diverifikasi melalui device readback setelah komisioning.",
                       "The active configuration is verified through device readback after commissioning.")),
            ],
            T("LoraStarConfig, validasi runtime 920-923 MHz, dan konfigurasi antena produk.", "LoraStarConfig, 920-923 MHz runtime validation, and product antenna configuration."),
        ),
        page(
            T("Antarmuka RS-485 / Modbus", "RS-485 / Modbus interface"),
            T("Antarmuka lokal disediakan sebagai Modbus RTU slave read-only untuk pembacaan data/status yang diekspos produk.",
              "The local interface is provided as a read-only Modbus RTU slave for product-exposed data/status."),
            "implemented",
            [
                cards([
                    (T("Physical layer", "Physical layer"), "RS-485"),
                    (T("Protocol", "Protocol"), "Modbus RTU"),
                    (T("Mode", "Mode"), T("Slave read-only", "Read-only slave")),
                    (T("Unit ID", "Unit ID"), "1"),
                ]),
                kv([
                    (T("Serial format", "Serial format"), "9600 bit/s, 8N1"),
                    (T("Transceiver", "Transceiver"), "THVD1410DR"),
                    (T("Akses customer", "Customer access"), T("Pembacaan delapan register publik yang didukung; tidak digunakan untuk menulis kontrol produk.", "Reads the eight supported public registers; not used to write product control.")),
                ]),
                note(T("Interface menggunakan function code 03/04 dan register read-only yang ditetapkan pada peta register produk.",
                       "The interface uses function codes 03/04 and the read-only registers defined in the product register map.")),
            ],
            T("Basis: Modbus scaffold/runtime dan transceiver pada schematic.", "Basis: Modbus scaffold/runtime and schematic transceiver."),
        ),
        page(
            T("Keamanan data dan frame", "Data and frame security"),
            T("Payload field menggunakan autentikasi aplikasi agar penerima dapat memverifikasi keaslian frame dan menolak frame yang tidak valid sebelum pemrosesan lebih lanjut.",
              "Field payloads use application authentication so the receiver can verify frame authenticity and reject invalid frames before further processing."),
            "implemented",
            [
                layers([
                    (T("Data sensor", "Sensor data"), T("Nilai, status, dan event", "Values, status, and events")),
                    (T("Frame aplikasi", "Application frame"), T("Identitas, sequence, dan payload", "Identity, sequence, and payload")),
                    (T("AES-128-GCM", "AES-128-GCM"), T("Confidentiality + authentication", "Confidentiality + authentication")),
                    (T("Transport LoRa", "LoRa transport"), T("STAR menuju CH", "STAR toward CH")),
                ], T("Gambar 12. Lapisan perlindungan payload field.", "Figure 12. Field-payload protection layers.")),
                bullets([
                    T("CH meneruskan frame field dan tidak menjadi titik terminasi TLS.", "CH forwards field frames and is not a TLS termination point."),
                    T("TLS, bila dipilih, berada pada segmen Gateway-ke-broker.", "TLS, when selected, is on the Gateway-to-broker segment."),
                    T("Penerima menolak payload yang gagal autentikasi atau pemeriksaan anti-replay.", "The receiver rejects payloads that fail authentication or anti-replay checks."),
                ]),
            ],
            T("Basis: kontrak protocol 0.2.0 dan implementasi keamanan payload.", "Basis: protocol 0.2.0 contract and payload-security implementation."),
        ),
        page(
            T("Komisioning melalui Operator Hub", "Commissioning through Operator Hub"),
            T("Operator Hub menjadi antarmuka pemilihan varian firmware, upload, konfigurasi, dan readback engineering.",
              "Operator Hub is the engineering interface for firmware-variant selection, upload, configuration, and readback."),
            "implemented",
            [
                sequence([T("Engineer", "Engineer"), T("Operator Hub", "Operator Hub"), T("Firmware", "Firmware"), T("Perangkat", "Device")], [
                    (0, 1, T("Pilih GasleakDetector", "Select GasleakDetector")),
                    (1, 2, T("Validasi varian/versi", "Validate variant/version")),
                    (1, 3, T("Upload firmware terpilih", "Upload selected firmware")),
                    (3, 1, T("Status + version readback", "Status + version readback")),
                    (0, 1, T("Konfigurasi / uji alarm", "Configure / alarm test")),
                ], T("Gambar 13. Alur commissioning terkontrol operator.", "Figure 13. Operator-controlled commissioning flow.")),
                table(
                    [T("Verifikasi komisioning", "Commissioning verification"), T("Kriteria", "Criterion")],
                    [
                        [T("Versi dan hardware", "Version and hardware"), T("Versi aktif dan profil hardware diverifikasi melalui readback perangkat setelah upload.", "The active version and hardware profile are verified through device readback after upload.")],
                        [T("Mode alarm", "Alarm mode"), T("Mode MANUAL memerlukan langkah eksplisit dan kembali AUTO saat boot.", "MANUAL mode requires an explicit step and returns to AUTO on boot.")],
                        [T("Batas RF", "RF boundary"), T("Konfigurasi frekuensi di luar 920-923 MHz ditolak.", "Frequency configuration outside 920-923 MHz is rejected.")],
                    ],
                    [0.28, 0.72],
                ),
            ],
            T("Basis: pilihan firmware Operator Hub, kontrak kontrol alarm, dan runtime readback.", "Basis: Operator Hub firmware selection, alarm-control contract, and runtime readback."),
        ),
        page(
            T("Status dan diagnostik", "Status and diagnostics"),
            T("Status machine-readable digunakan untuk membedakan konfigurasi, kesiapan subsistem, fault, dan hasil operasi.",
              "Machine-readable status separates configuration, subsystem readiness, faults, and operational results."),
            "implemented",
            [
                table([T("Kelompok status", "Status group"), T("Contoh isi engineering", "Engineering content examples")], [
                    [T("Identitas", "Identity"), T("Firmware version, protocol version, device identity", "Firmware version, protocol version, device identity")],
                    [T("Sensor", "Sensors"), T("Channel aktif, validitas, dan fault state", "Active channels, validity, and fault state")],
                    [T("Nulling", "Nulling"), T("Profile/status dan hasil per channel", "Profile/status and per-channel result")],
                    [T("Radio", "Radio"), T("Frequency, bandwidth, SF, CR, power, preamble", "Frequency, bandwidth, SF, CR, power, preamble")],
                    [T("Alarm", "Alarm"), T("AUTO/MANUAL, commanded output, session-only flag", "AUTO/MANUAL, commanded output, session-only flag")],
                    [T("Daya", "Power"), T("Sumber terdeteksi dan state power path", "Detected source and power-path state")],
                ], [0.30, 0.70]),
                note(T("Pembacaan kembali perangkat digunakan untuk memverifikasi konfigurasi unit aktif.",
                       "Device readback verifies the active unit configuration."), "success"),
            ],
            T("Basis: status JSON dan kapabilitas command firmware/operator.", "Basis: firmware/operator status JSON and command capabilities."),
        ),
        page(
            T("Referensi dan riwayat revisi", "References and revision history"),
            T("Referensi eksternal menjelaskan komponen; nilai produk rakitan mengikuti spesifikasi dalam dokumen ini.",
              "External references describe components; assembled-product values follow the specifications in this document."),
            "reference",
            [
                table([T("Referensi", "Reference"), T("Dokumen / URL", "Document / URL")], [
                    ["R1", "Espressif - ESP32-S3-WROOM-1/1U Datasheet, v1.8, documentation.espressif.com"],
                    ["R2", "Texas Instruments - ADS1256 product datasheet, ti.com/product/ADS1256"],
                    ["R3", "Texas Instruments - THVD1410 product datasheet, ti.com/product/THVD1410"],
                    ["R4", "Sensirion - SHT40 / SHT4x Datasheet, sensirion.com/products/catalog/SHT40"],
                    ["R5", "Winsen - MQ Sensor Series Overview, winsen-sensor.com/mq-sensor.html"],
                ], [0.14, 0.86]),
                table([T("Revisi", "Revision"), T("Perubahan", "Change")], [
                    ["4.0", T("Pembaruan struktur dan spesifikasi teknis.", "Updated technical structure and specifications.")],
                ], [0.18, 0.82]),
            ],
            T("Dokumentasi resmi komponen dan revisi teknis saat ini.", "Official component documentation and current technical revision."),
        ),
    ]
    return d


def ch_document() -> dict[str, Any]:
    d = common_meta(
        slug="CH",
        product="CH",
        status=T("Prototipe Engineering", "Engineering Prototype"),
        firmware="Firmware 0.8.0 | Protocol 0.2.0",
        subtitle=T(
            "Node dual-radio untuk agregasi LoRa STAR, routing dinamis, dan penerusan multi-hop LoRa MESH.",
            "Dual-radio node for LoRa STAR aggregation, dynamic routing, and multi-hop LoRa MESH forwarding.",
        ),
        cover_nodes=[
            (T("GasleakDetector", "GasleakDetector"), T("Endpoint", "Endpoint")),
            (T("Radio STAR", "STAR radio"), T("Antena 3 dBi", "3 dBi antenna")),
            ("CH", T("Discovery + routing", "Discovery + routing")),
            (T("Radio MESH", "MESH radio"), T("Antena 8 dBi", "8 dBi antenna")),
            (T("CH / Gateway", "CH / Gateway"), T("Next hop", "Next hop")),
        ],
        cover_links=[T("920 MHz", "920 MHz"), T("ingress", "ingress"), T("egress", "egress"), T("921 MHz", "921 MHz")],
        facts=[
            (T("VARIAN PCB", "PCB VARIANTS"), T("Rectangle / Circle", "Rectangle / Circle")),
            (T("RADIO", "RADIOS"), T("2 x E22-900MM22S", "2 x E22-900MM22S")),
            (T("ENERGI", "ENERGY"), T("Baterai + 2 panel", "Battery + 2 panels")),
            (T("ROUTING", "ROUTING"), T("Dynamic multi-hop", "Dynamic multi-hop")),
        ],
        abbreviations=[
            ("CH", T("Communication Hub / node komunikasi lapangan", "Communication Hub / field communication node")),
            ("EIRP", T("Equivalent Isotropically Radiated Power", "Equivalent Isotropically Radiated Power")),
            ("MESH", T("Domain radio backbone antar-CH dan Gateway", "Backbone radio domain between CH and Gateway")),
            ("NVM/NVS", T("Penyimpanan konfigurasi non-volatile", "Non-volatile configuration storage")),
            ("RF", T("Radio frequency", "Radio frequency")),
            ("STAR", T("Domain radio GasleakDetector-ke-CH", "GasleakDetector-to-CH radio domain")),
            ("TX", T("Transmit", "Transmit")),
            ("VBAT", T("Tegangan baterai yang dibaca perangkat", "Battery voltage read by the device")),
        ],
    )
    d["chapters"] = [
        page(
            T("Ikhtisar produk", "Product overview"),
            T("CH menjembatani domain endpoint LoRa STAR dan backbone LoRa MESH tanpa menetapkan parent secara permanen.",
              "CH bridges the LoRa STAR endpoint domain and LoRa MESH backbone without permanently fixing a parent."),
            "implemented",
            [
                cards([
                    (T("Ingress", "Ingress"), T("LoRa STAR", "LoRa STAR")),
                    (T("Egress", "Egress"), T("LoRa MESH", "LoRa MESH")),
                    (T("Radio", "Radios"), "2"),
                    (T("Varian", "Variants"), T("2 bentuk PCB", "2 PCB forms")),
                ]),
                bullets([
                    T("Menerima trafik GasleakDetector melalui Radio A/STAR.", "Receives GasleakDetector traffic through Radio A/STAR."),
                    T("Memilih parent berdasarkan discovery, root reachability, dan health.", "Selects a parent based on discovery, root reachability, and health."),
                    T("Meneruskan uplink dan downlink melalui Radio B/MESH.", "Forwards uplink and downlink through Radio B/MESH."),
                    T("Mendukung CH transit tambahan ketika rute langsung ke Gateway tidak dipilih.", "Supports additional transit CH nodes when a direct Gateway route is not selected."),
                ]),
            ],
            T("Firmware CH, dua profil board, dan schematic/PCB produk.", "CH firmware, two board profiles, and product schematic/PCB."),
        ),
        page(
            T("Peran CH dalam jaringan", "CH role in the network"),
            T("Satu CH dapat berperan sebagai serving CH untuk endpoint lokal dan sebagai transit CH untuk node lain.",
              "A CH can act as the serving CH for local endpoints and as a transit CH for other nodes."),
            "implemented",
            [
                diagram([
                    (T("GasleakDetector", "GasleakDetector"), T("Endpoint lokal", "Local endpoint")),
                    (T("Serving CH", "Serving CH"), T("STAR ke MESH", "STAR to MESH")),
                    (T("Transit CH", "Transit CH"), T("Opsional", "Optional")),
                    (T("Parent berikut", "Next parent"), T("CH / Gateway", "CH / Gateway")),
                    (T("Gateway", "Gateway"), T("Root tujuan", "Root destination")),
                ], [T("STAR", "STAR"), T("MESH", "MESH"), T("MESH", "MESH"), T("root", "root")],
                   T("Gambar 1. Peran serving dan transit pada jalur field.", "Figure 1. Serving and transit roles in the field path.")),
                kv([
                    (T("Serving CH", "Serving CH"), T("Menerima frame STAR dari GasleakDetector yang dilayani.", "Receives STAR frames from its served GasleakDetector.")),
                    (T("Transit CH", "Transit CH"), T("Meneruskan frame MESH tanpa menjadi sumber data endpoint.", "Forwards MESH frames without becoming the endpoint data source.")),
                    (T("Gateway root", "Gateway root"), T("Tujuan akhir rute; bukan parent statis untuk semua CH.", "Final route destination; not a static parent for every CH.")),
                ]),
            ],
            T("Implementasi serving, transit, forwarding, dan root routing pada runtime CH.", "CH runtime serving, transit, forwarding, and root-routing implementation."),
        ),
        page(
            T("Varian PCB dan kompatibilitas firmware", "PCB variants and firmware compatibility"),
            T("Rectangle/kecil dan Circle/besar menggunakan pemetaan hardware berbeda sehingga target firmware harus dipilih secara eksplisit.",
              "Rectangle/small and Circle/large use different hardware mappings, so the firmware target must be selected explicitly."),
            "implemented",
            [
                table([T("Varian produk", "Product variant"), T("Basis desain", "Design basis"), T("Pilihan Operator Hub", "Operator Hub selection"), T("Keterangan", "Description")], [
                    [T("CH Rectangle", "CH Rectangle"), T("Profil hardware Rectangle", "Rectangle hardware profile"), T("CH Rectangle", "CH Rectangle"), T("Pemetaan khusus board Rectangle", "Rectangle-board-specific mapping")],
                    [T("CH Circle", "CH Circle"), T("Profil hardware Circle", "Circle hardware profile"), T("CH Circle", "CH Circle"), T("Pemetaan khusus board Circle", "Circle-board-specific mapping")],
                ], [0.24, 0.27, 0.20, 0.29]),
                layers([
                    (T("Pilih bentuk board", "Select board form"), T("Rectangle atau Circle", "Rectangle or Circle")),
                    (T("Pilih varian firmware", "Select firmware variant"), T("Target harus cocok dengan profil hardware", "Target must match the hardware profile")),
                    (T("Upload", "Upload"), T("Operator Hub menolak fallback hardware", "Operator Hub rejects hardware fallback")),
                    (T("Readback", "Readback"), T("Versi, identitas, dan varian board diperiksa", "Version, identity, and board variant are checked")),
                ], T("Gambar 2. Gate kompatibilitas board dan firmware.", "Figure 2. Board and firmware compatibility gate.")),
                note(T("Firmware kedua varian tidak boleh dipertukarkan tanpa pemilihan target hardware yang benar.",
                       "The two firmware variants are not interchangeable without selecting the correct hardware target."), "success"),
            ],
            T("Profil hardware Rectangle/Circle, target firmware, dan validasi kompatibilitas Operator Hub.", "Rectangle/Circle hardware profiles, firmware targets, and Operator Hub compatibility validation."),
        ),
        page(
            T("Komponen perangkat keras utama", "Primary hardware components"),
            T("Kedua board berbagi arsitektur fungsional yang sama walaupun layout dan pin mapping berbeda.",
              "Both boards share the same functional architecture even though layout and pin mapping differ."),
            "component",
            [
                table([T("Fungsi", "Function"), T("Komponen desain", "Design component"), T("Peran", "Role")], [
                    [T("MCU", "MCU"), "ESP32-S3-WROOM-1U-N16R8", T("Runtime, routing, konfigurasi, dan status", "Runtime, routing, configuration, and status")],
                    [T("Radio A", "Radio A"), "EBYTE E22-900MM22S", T("Domain LoRa STAR", "LoRa STAR domain")],
                    [T("Radio B", "Radio B"), "EBYTE E22-900MM22S", T("Domain LoRa MESH", "LoRa MESH domain")],
                    [T("Charger", "Charger"), "TI BQ25185DLHR", T("Interface pengisian/solar pada PCB", "PCB charging/solar interface")],
                    [T("Watchdog", "Watchdog"), "TI TPL5010DDCR", T("Watchdog/timing hardware", "Hardware watchdog/timing")],
                ], [0.20, 0.34, 0.46]),
                note(T("Rating temperatur, keselamatan, dan compliance komponen tidak menjadi rating produk CH.",
                       "Component temperature, safety, and compliance ratings do not become CH product ratings."), "caution"),
            ],
            T("Record komponen pada schematic/PCB Ver4 dan Ver5.", "Component records in the Ver4 and Ver5 schematic/PCB."),
        ),
        page(
            T("Arsitektur dual-radio", "Dual-radio architecture"),
            T("Domain STAR dan MESH dipisahkan secara fisik dan logis dengan radio serta parameter default berbeda.",
              "STAR and MESH domains are physically and logically separated with different radios and defaults."),
            "implemented",
            [
                diagram([
                    (T("Endpoint", "Endpoint"), T("GasleakDetector", "GasleakDetector")),
                    (T("Radio A", "Radio A"), T("STAR / 3 dBi", "STAR / 3 dBi")),
                    (T("Runtime CH", "CH runtime"), T("Cache + routing", "Cache + routing")),
                    (T("Radio B", "Radio B"), T("MESH / 8 dBi", "MESH / 8 dBi")),
                    (T("Backbone", "Backbone"), T("CH / Gateway", "CH / Gateway")),
                ], [T("STAR", "STAR"), T("ingress", "ingress"), T("forward", "forward"), T("MESH", "MESH")],
                   T("Gambar 3. Pemisahan dua domain radio pada CH.", "Figure 3. Separation of the two CH radio domains.")),
                bullets([
                    T("Radio A dan Radio B menggunakan driver SX1262.", "Radio A and Radio B use the SX1262 driver."),
                    T("Operasi normal membutuhkan inisialisasi STAR dan MESH yang berhasil.", "Normal operation requires successful STAR and MESH initialization."),
                    T("STAR dan MESH menggunakan antena terpisah sesuai domain radio masing-masing.", "STAR and MESH use separate antennas for their respective radio domains."),
                ]),
            ],
            T("Inisialisasi dua radio dan pemetaan Radio A/Radio B pada source CH.", "Dual-radio initialization and Radio A/Radio B mapping in CH source."),
        ),
        page(
            T("Karakteristik LoRa STAR", "LoRa STAR characteristics"),
            T("STAR adalah link lokal dari GasleakDetector menuju serving CH.",
              "STAR is the local link from GasleakDetector to its serving CH."),
            "implemented",
            [
                table([T("Parameter", "Parameter"), T("Default", "Default"), T("Status", "Status")], [
                    [T("Carrier", "Carrier"), "920.0 MHz", T("Konfigurasi diterima 920-923 MHz", "Configuration accepted from 920-923 MHz")],
                    [T("Bandwidth", "Bandwidth"), "125 kHz", T("Default firmware", "Firmware default")],
                    [T("Spreading factor", "Spreading factor"), "SF7", T("Default firmware", "Firmware default")],
                    [T("Coding rate", "Coding rate"), "4/5", T("Default firmware", "Firmware default")],
                    [T("TX setting", "TX setting"), "17 dBm", T("Setting, bukan output terukur", "Setting, not measured output")],
                    [T("Antena CH", "CH antenna"), "3 dBi", T("Konfigurasi produk", "Product configuration")],
                ], [0.28, 0.25, 0.47]),
                note(T("Konfigurasi aktual dapat berasal dari NVS. Device readback adalah rujukan deployment, bukan tabel default.",
                       "Actual configuration may come from NVS. Device readback, not the default table, is the deployment reference."), "caution"),
            ],
            T("LoraStarConfig, validasi carrier runtime, NVS, dan konfigurasi antena produk.", "LoraStarConfig, runtime carrier validation, NVS, and product antenna configuration."),
        ),
        page(
            T("Karakteristik LoRa MESH", "LoRa MESH characteristics"),
            T("MESH adalah backbone CH-ke-CH dan CH-ke-Gateway.",
              "MESH is the CH-to-CH and CH-to-Gateway backbone."),
            "implemented",
            [
                table([T("Parameter", "Parameter"), T("Default", "Default"), T("Status", "Status")], [
                    [T("Carrier", "Carrier"), "921.0 MHz", T("Konfigurasi diterima 920-923 MHz", "Configuration accepted from 920-923 MHz")],
                    [T("Bandwidth", "Bandwidth"), "125 kHz", T("Default firmware", "Firmware default")],
                    [T("Spreading factor", "Spreading factor"), "SF9", T("Default firmware", "Firmware default")],
                    [T("Coding rate", "Coding rate"), "4/5", T("Default firmware", "Firmware default")],
                    [T("TX setting", "TX setting"), "17 dBm", T("Setting, bukan output terukur", "Setting, not measured output")],
                    [T("Antena CH", "CH antenna"), "8 dBi", T("Konfigurasi produk", "Product configuration")],
                ], [0.28, 0.25, 0.47]),
            ],
            T("LoraMeshConfig, validasi carrier runtime, NVS, dan konfigurasi antena produk.", "LoraMeshConfig, runtime carrier validation, NVS, and product antenna configuration."),
        ),
        page(
            T("Nilai default, NVS, dan pembacaan kembali perangkat", "Defaults, NVS, and device readback"),
            T("Firmware membedakan nilai default, nilai tersimpan, dan nilai aktual yang dibaca kembali setelah write.",
              "Firmware distinguishes defaults, stored values, and actual values read back after a write."),
            "implemented",
            [
                layers([
                    (T("Default build", "Build default"), T("STAR 920.0 MHz; MESH 921.0 MHz", "STAR 920.0 MHz; MESH 921.0 MHz")),
                    (T("Validasi input", "Input validation"), T("Carrier harus 920-923 MHz inclusive", "Carrier must be within 920-923 MHz inclusive")),
                    (T("Penyimpanan", "Storage"), T("Konfigurasi STAR/MESH disimpan ke NVS", "STAR/MESH configuration is stored in NVS")),
                    (T("Readback", "Readback"), T("Write diverifikasi sebelum ACK sukses", "Write is verified before success ACK")),
                    (T("Boot berikut", "Next boot"), T("Konfigurasi valid dimuat kembali", "Valid configuration is reloaded")),
                ], T("Gambar 4. Siklus konfigurasi RF terkontrol.", "Figure 4. Controlled RF-configuration cycle.")),
                note(T("Engineer harus mencatat hasil readback unit setelah commissioning.", "Engineers must record unit readback after commissioning."), "success"),
            ],
            T("Validasi RF, persistence NVS, readback verification, dan boot-load source.", "RF validation, NVS persistence, readback verification, and boot-load source."),
        ),
        page(
            T("Perhitungan EIRP nominal", "Nominal EIRP calculation"),
            T("Nilai berikut adalah arithmetic TX setting + gain antena sebelum loss; bukan hasil pengukuran RF.",
              "The values below are arithmetic TX setting plus antenna gain before losses; they are not RF measurements."),
            "boundary",
            [
                table([T("Domain", "Domain"), T("TX setting", "TX setting"), T("Gain antena", "Antenna gain"), T("Nominal sebelum loss", "Nominal before loss")], [
                    ["STAR", "17 dBm", "3 dBi", "20 dBm"],
                    ["MESH", "17 dBm", "8 dBi", "25 dBm"],
                ], [0.22, 0.22, 0.25, 0.31]),
                bullets([
                    T("Rugi kabel/konektor tidak termasuk dalam perhitungan nominal.", "Cable/connector loss is not included in the nominal calculation."),
                ]),
                note(T("Jika dokumen regulasi membutuhkan EIRP, gunakan hasil laboratorium terakreditasi dan konfigurasi antena final.",
                       "If regulatory documentation requires EIRP, use accredited-laboratory results and the final antenna configuration."), "caution"),
            ],
            T("Perhitungan nominal dari setting firmware dan gain antena produk.", "Nominal calculation from firmware settings and product antenna gain."),
        ),
        page(
            T("Discovery dan kandidat parent", "Discovery and parent candidates"),
            T("CH membentuk kandidat parent dari discovery dan tidak memakai identitas parent yang dipatok.",
              "CH builds parent candidates through discovery and does not use a fixed parent identity."),
            "implemented",
            [
                diagram([
                    (T("CH lokal", "Local CH"), T("Butuh rute", "Needs route")),
                    (T("Discovery", "Discovery"), T("Kandidat sekitar", "Nearby candidates")),
                    (T("Lineage check", "Lineage check"), T("Menuju root", "Toward root")),
                    (T("Scoring", "Scoring"), T("Health + kualitas", "Health + quality")),
                    (T("Parent aktif", "Active parent"), T("CH / Gateway", "CH / Gateway")),
                ], [T("probe", "probe"), T("filter", "filter"), T("rank", "rank"), T("install", "install")],
                   T("Gambar 5. Alur pembentukan parent aktif.", "Figure 5. Active-parent selection flow.")),
                bullets([
                    T("Kandidat harus mempunyai lineage yang mencapai root Gateway.", "A candidate must have lineage that reaches the Gateway root."),
                    T("Loop dan lineage yang tidak valid ditolak.", "Loops and invalid lineage are rejected."),
                    T("Parent dan alternate dapat disimpan setelah stabil.", "Parent and alternate can be stored after stabilization."),
                ]),
            ],
            T("Discovery, lineage guard, candidate scoring, dan parent installation pada runtime CH.", "CH runtime discovery, lineage guard, candidate scoring, and parent installation."),
        ),
        page(
            T("Parent aktif, parent alternatif, dan pencegahan loop", "Active parent, alternate, and loop prevention"),
            T("Routing menjaga jalur menuju Gateway serta mencegah parent chain berputar kembali ke node asal.",
              "Routing maintains a path toward the Gateway while preventing the parent chain from looping back to the origin node."),
            "implemented",
            [
                table([T("Kontrol", "Control"), T("Fungsi", "Function"), T("Hasil", "Outcome")], [
                    [T("Root reachability", "Root reachability"), T("Memastikan kandidat mempunyai jalur ke Gateway", "Ensures candidate has a path to Gateway"), T("Kandidat tanpa root ditolak", "Candidate without root is rejected")],
                    [T("Lineage guard", "Lineage guard"), T("Mengecek rantai parent", "Checks parent chain"), T("Loop candidate ditolak", "Looping candidate is rejected")],
                    [T("Parent health", "Parent health"), T("Memantau respons parent aktif", "Monitors active-parent response"), T("Dapat memicu pergantian", "Can trigger replacement")],
                    [T("Alternate parent", "Alternate parent"), T("Menjaga kandidat cadangan", "Keeps a backup candidate"), T("Dapat dipakai sebelum rediscovery", "Can be used before rediscovery")],
                ], [0.22, 0.38, 0.40]),
                note(T("Rute aktual bergantung hasil discovery lapangan; datasheet tidak menamai parent tertentu sebagai pasangan permanen.",
                       "The actual route depends on field discovery; the datasheet does not name any parent as a permanent pair."), "success"),
            ],
            T("Root reachability, lineage, health monitoring, dan alternate-parent source.", "Root-reachability, lineage, health-monitoring, and alternate-parent source."),
        ),
        page(
            T("Penerusan multi-hop", "Multi-hop forwarding"),
            T("Frame dapat melewati nol atau lebih transit CH sebelum mencapai Gateway.",
              "A frame can pass through zero or more transit CH nodes before reaching the Gateway."),
            "implemented",
            [
                sequence([T("Serving CH", "Serving CH"), T("Transit CH 1", "Transit CH 1"), T("Transit CH n", "Transit CH n"), T("Gateway", "Gateway")], [
                    (0, 1, T("Forward MESH", "Forward MESH")),
                    (1, 2, T("Relay sesuai route", "Relay by route")),
                    (2, 3, T("Deliver ke root", "Deliver to root")),
                    (3, 2, T("Downlink reverse path", "Downlink reverse path")),
                    (2, 0, T("Relay ke serving CH", "Relay to serving CH")),
                ], T("Gambar 6. Penerusan uplink dan downlink multi-hop.", "Figure 6. Multi-hop uplink and downlink forwarding.")),
            ],
            T("Implementasi relay uplink/downlink dan route handling pada CH.", "CH uplink/downlink relay and route-handling implementation."),
        ),
        page(
            T("Telemetri normal: cache dan permintaan server", "Normal telemetry: cache and server pull"),
            T("Telemetry normal tidak memakai pola push yang sama dengan alarm; data disimpan pada cache CH dan dikirim sebagai respons pull.",
              "Normal telemetry does not use the same push pattern as alarms; data is cached at CH and sent in response to a pull."),
            "implemented",
            [
                sequence([T("GasleakDetector", "GasleakDetector"), T("Serving CH", "Serving CH"), T("Gateway/Server", "Gateway/Server")], [
                    (0, 1, T("Telemetry STAR", "STAR telemetry")),
                    (1, 1, T("Simpan/refresh cache", "Store/refresh cache")),
                    (2, 1, T("Server pull", "Server pull")),
                    (1, 2, T("Cluster response", "Cluster response")),
                ], T("Gambar 7. Jalur telemetry normal berbasis cache/pull.", "Figure 7. Cache/pull path for normal telemetry.")),
                bullets([
                    T("Cache memisahkan penerimaan endpoint dari siklus permintaan server.", "Cache separates endpoint reception from the server request cycle."),
                    T("Pengiriman ke Server berlangsung saat permintaan pull mencapai serving CH.", "Delivery to the Server occurs when a pull request reaches the serving CH."),
                ]),
            ],
            T("Node cache, CH runtime, cluster response, dan server-pull handling.", "Node cache, CH runtime, cluster response, and server-pull handling."),
        ),
        page(
            T("Push alarm dan kembali-normal", "Alarm push and return-to-clear"),
            T("Alarm dan event kembali-clear menggunakan jalur push agar tidak menunggu siklus telemetry normal.",
              "Alarm and return-to-clear events use a push path so they do not wait for the normal telemetry cycle."),
            "implemented",
            [
                sequence([T("GasleakDetector", "GasleakDetector"), T("Serving CH", "Serving CH"), T("Parent", "Parent"), T("Gateway", "Gateway")], [
                    (0, 1, T("Alarm/clear frame", "Alarm/clear frame")),
                    (1, 2, T("Teruskan melalui MESH", "Forward over MESH")),
                    (2, 3, T("Relay toward root", "Relay toward root")),
                    (3, 2, T("ACK path", "ACK path")),
                    (2, 1, T("ACK to serving CH", "ACK to serving CH")),
                ], T("Gambar 8. Jalur push untuk alarm dan return-to-clear.", "Figure 8. Push path for alarm and return-to-clear.")),
            ],
            T("Alarm push, clear event, forwarding langsung, dan ACK handling pada CH.", "CH alarm push, clear event, immediate forwarding, and ACK handling."),
        ),
        page(
            T("Peralihan parent", "Parent failover"),
            T("Failover dapat memakai alternate parent atau kembali ke discovery ketika health parent aktif menurun.",
              "Failover can use an alternate parent or return to discovery when active-parent health degrades."),
            "tested",
            [
                layers([
                    (T("Parent aktif", "Active parent"), T("HELLO/ACK dan health dipantau", "HELLO/ACK and health are monitored")),
                    (T("Failure trigger", "Failure trigger"), T("Timeout, HELLO ACK gagal, atau alarm ACK gagal", "Timeout, HELLO ACK failure, or alarm ACK failure")),
                    (T("Alternate", "Alternate"), T("Dipakai bila masih valid", "Used when still valid")),
                    (T("Rediscovery", "Rediscovery"), T("Mencari kandidat baru bila perlu", "Finds new candidates when needed")),
                    (T("Rute baru", "New route"), T("Parent ditentukan hasil discovery", "Parent is determined by discovery")),
                ], T("Gambar 9. State failover parent.", "Figure 9. Parent-failover state flow.")),
                note(T("Multi-hop dan failover telah divalidasi di Lab IoT ITB. Parent pengganti dipilih dinamis melalui discovery.",
                       "Multi-hop and failover have been validated at the ITB IoT Lab. The replacement parent is selected dynamically through discovery."), "success"),
            ],
            T("Implementasi failover dan validasi laboratorium internal.", "Failover implementation and internal laboratory validation."),
        ),
        page(
            T("Arsitektur energi CH", "CH energy architecture"),
            T("Konfigurasi produk menggabungkan baterai paralel dan dua panel surya paralel melalui hardware charging pada board.",
              "The product configuration combines parallel batteries and two parallel solar panels through on-board charging hardware."),
            "confirmed",
            [
                diagram([
                    (T("2 x panel", "2 x panels"), T("6 W masing-masing", "6 W each")),
                    (T("Input SOLAR", "SOLAR input"), T("Paralel", "Parallel")),
                    ("BQ25185", T("Charge/power path", "Charge/power path")),
                    (T("1-3 sel", "1-3 cells"), T("18650 paralel", "Parallel 18650")),
                    (T("CH", "CH"), T("Dual-radio load", "Dual-radio load")),
                ], [T("gabung", "combine"), T("charge", "charge"), T("store", "store"), T("supply", "supply")],
                   T("Gambar 10. Topologi energi CH.", "Figure 10. CH energy topology.")),
                note(T("Konfigurasi produk menggunakan 1-3 sel 18650 paralel dan dua panel 6 W paralel melalui jalur charging pada board.",
                       "The product configuration uses 1-3 parallel 18650 cells and two parallel 6 W panels through the on-board charging path.")),
            ],
            T("Schematic dua board, BQ25185, dan konfigurasi energi produk.", "Two-board schematics, BQ25185, and product energy configuration."),
        ),
        page(
            T("Konfigurasi baterai CH", "CH battery configuration"),
            T("CH menggunakan satu sampai tiga sel LiitoKala 18650 yang disusun paralel.",
              "CH uses one to three LiitoKala 18650 cells connected in parallel."),
            "confirmed",
            [
                table([T("Parameter", "Parameter"), T("Konfigurasi", "Configuration"), T("Catatan", "Note")], [
                    [T("Jenis", "Type"), "LiitoKala Lii-King4000 18650", T("Identifikasi label sel", "Cell-label identification")],
                    [T("Jumlah", "Quantity"), "1-3", T("Bergantung deployment", "Deployment-dependent")],
                    [T("Label kapasitas", "Capacity label"), T("4000 mAh / sel", "4000 mAh / cell"), T("Bukan hasil uji kapasitas pakai", "Not a usable-capacity test")],
                    [T("Topologi", "Topology"), T("Paralel", "Parallel"), T("Mempertahankan domain tegangan satu sel", "Maintains the single-cell voltage domain")],
                ], [0.25, 0.29, 0.46]),
                note(T("Nilai 4000 mAh adalah kapasitas pada label tiap sel.", "The 4000 mAh value is the nameplate capacity of each cell.")),
            ],
            T("Konfigurasi baterai produk dan interface baterai pada schematic Ver4/Ver5.", "Product battery configuration and Ver4/Ver5 schematic battery interfaces."),
        ),
        page(
            T("Panel surya dan pengisian", "Solar panels and charging"),
            T("Dua panel 6 W disusun paralel menuju interface solar CH.",
              "Two 6 W panels are connected in parallel to the CH solar interface."),
            "confirmed",
            [
                cards([
                    (T("Jumlah panel", "Panel count"), "2"),
                    (T("Daya nominal", "Nameplate"), T("6 W masing-masing", "6 W each")),
                    (T("Topologi", "Topology"), T("Paralel", "Parallel")),
                    (T("Gabungan", "Combined"), T("12 W nominal", "12 W nameplate")),
                ]),
                kv([
                    (T("Interface board", "Board interface"), T("Satu input SOLAR menuju power/charge path.", "One SOLAR input into the power/charge path.")),
                    (T("Controller", "Controller"), "TI BQ25185DLHR"),
                ]),
                note(T("12 W adalah penjumlahan nameplate dua panel, bukan output lapangan terukur.",
                       "12 W is the sum of two panel nameplates, not measured field output."), "caution"),
            ],
            T("Konfigurasi dua panel dan interface solar/charger pada schematic.", "Two-panel configuration and schematic solar/charger interface."),
        ),
        page(
            T("Telemetri baterai dan batas proteksi", "Battery telemetry and protection boundary"),
            T("Firmware membaca serta melaporkan tegangan baterai, tetapi tidak menggunakan low voltage untuk memblokir operasi produk.",
              "Firmware reads and reports battery voltage but does not use low voltage to block product operation."),
            "implemented",
            [
                layers([
                    (T("VBAT sensing", "VBAT sensing"), T("Tegangan dibaca oleh CH", "Voltage is read by CH")),
                    (T("Status", "Status"), T("Nilai dilaporkan read-only", "Value is reported read-only")),
                    (T("Boot/TX", "Boot/TX"), T("Tidak diblokir oleh threshold VBAT", "Not blocked by VBAT threshold")),
                    (T("Low-power", "Low-power"), T("Tidak dipicu otomatis oleh undervoltage", "Not automatically triggered by undervoltage")),
                ], T("Gambar 11. Batas fungsi VBAT read-only.", "Figure 11. VBAT read-only function boundary.")),
                note(T("VBAT digunakan untuk telemetri diagnostik; firmware tidak memutus daya atau memasuki low-power secara otomatis berdasarkan pembacaan tersebut.",
                       "VBAT is used for diagnostic telemetry; firmware does not disconnect power or enter low-power mode automatically from that reading.")),
            ],
            T("VBAT read-only build flags dan runtime battery-status logic.", "VBAT read-only build flags and runtime battery-status logic."),
        ),
        page(
            T("Komisioning dan Operator Hub", "Commissioning and Operator Hub"),
            T("Commissioning mengunci bentuk board, varian firmware, identitas, serta readback konfigurasi sebelum unit diterima.",
              "Commissioning locks board form, firmware variant, identity, and configuration readback before unit acceptance."),
            "implemented",
            [
                sequence([T("Engineer", "Engineer"), T("Operator Hub", "Operator Hub"), T("Firmware", "Firmware"), T("CH", "CH")], [
                    (0, 1, T("Pilih Rectangle/Circle", "Select Rectangle/Circle")),
                    (1, 2, T("Pilih CH Rectangle/CH Circle", "Select CH Rectangle/CH Circle")),
                    (1, 3, T("Upload", "Upload")),
                    (3, 1, T("Versi + varian board", "Version + board variant")),
                    (0, 1, T("RF readback", "RF readback")),
                ], T("Gambar 12. Gate commissioning CH.", "Figure 12. CH commissioning gates.")),
                table([T("Interface", "Interface"), T("Cakupan", "Scope")], [
                    [T("Simple Operator Hub", "Simple Operator Hub"), T("Pemilihan board/firmware dan kontrol konfigurasi sederhana.", "Board/firmware selection and simplified configuration controls.")],
                    [T("CH Expert Operator", "CH Expert Operator"), T("Konfigurasi/readback STAR dan MESH lebih lengkap.", "More complete STAR and MESH configuration/readback.")],
                ], [0.32, 0.68]),
            ],
            T("Pemetaan board Operator Hub, pemilihan firmware, readback perangkat, dan CH Expert Operator.", "Operator Hub board mapping, firmware selection, device readback, and CH Expert Operator."),
        ),
        page(
            T("Referensi dan riwayat revisi", "References and revision history"),
            T("Referensi komponen dipakai untuk identifikasi, bukan untuk menaikkan klaim produk rakitan.",
              "Component references are used for identification, not to elevate assembled-product claims."),
            "reference",
            [
                table([T("Referensi", "Reference"), T("Dokumen", "Document")], [
                    ["R1", "Espressif - ESP32-S3-WROOM-1/1U Datasheet v1.8"],
                    ["R2", "EBYTE - E22-900MM22S module documentation"],
                    ["R3", "Texas Instruments - BQ25185 product datasheet"],
                    ["R4", "Texas Instruments - TPL5010 product datasheet"],
                ], [0.14, 0.86]),
                table([T("Rev", "Rev"), T("Perubahan", "Change")], [
                    ["4.0", T("Pembaruan struktur dan spesifikasi teknis.", "Updated technical structure and specifications.")],
                ], [0.18, 0.82]),
            ],
            T("Dokumentasi komponen resmi dan revisi teknis saat ini.", "Official component documentation and current technical revision."),
        ),
    ]
    return d


def gateway_document() -> dict[str, Any]:
    d = common_meta(
        slug="Gateway",
        product="Gateway",
        status=T("Prototipe Engineering", "Engineering Prototype"),
        firmware="Firmware 0.2.0 | Protocol 0.2.0",
        subtitle=T(
            "Bridge LoRa MESH ke jaringan IP melalui Wi-Fi STA dan MQTT, dengan firmware TLS dan non-TLS terpisah.",
            "LoRa MESH to IP-network bridge over Wi-Fi STA and MQTT, with separate TLS and non-TLS firmware.",
        ),
        cover_nodes=[
            (T("Jaringan CH", "CH network"), T("LoRa MESH", "LoRa MESH")),
            (T("Radio B", "Radio B"), T("Antena 8 dBi", "8 dBi antenna")),
            (T("Gateway", "Gateway"), T("ESP32-S3", "ESP32-S3")),
            (T("Wi-Fi STA", "Wi-Fi STA"), T("IP uplink", "IP uplink")),
            (T("Broker/Server", "Broker/Server"), T("MQTT / TLS", "MQTT / TLS")),
        ],
        cover_links=[T("921 MHz", "921 MHz"), T("frame", "frame"), T("IP", "IP"), T("publish", "publish")],
        facts=[
            (T("BOARD", "BOARDS"), T("Rectangle / Circle", "Rectangle / Circle")),
            (T("RADIO AKTIF", "ACTIVE RADIO"), T("MESH / Radio B", "MESH / Radio B")),
            (T("JARINGAN", "NETWORK"), T("Wi-Fi STA", "Wi-Fi STA")),
            (T("TRANSPORT", "TRANSPORT"), T("MQTT TLS / non-TLS", "MQTT TLS / non-TLS")),
        ],
        abbreviations=[
            ("CA", T("Certificate Authority", "Certificate Authority")),
            ("MESH", T("Domain radio backbone CH-ke-Gateway", "CH-to-Gateway backbone radio domain")),
            ("MQTT", T("Message Queuing Telemetry Transport", "Message Queuing Telemetry Transport")),
            ("NTP", T("Network Time Protocol", "Network Time Protocol")),
            ("NVS", T("Penyimpanan konfigurasi non-volatile", "Non-volatile configuration storage")),
            ("STA", T("Mode Wi-Fi station", "Wi-Fi station mode")),
            ("TLS", T("Transport Layer Security", "Transport Layer Security")),
            ("WAN/LAN", T("Segmen jaringan IP deployment", "Deployment IP-network segment")),
        ],
    )
    d["chapters"] = [
        page(
            T("Ikhtisar produk", "Product overview"),
            T("Gateway menghubungkan backbone LoRa MESH ke broker MQTT melalui Wi-Fi dan mempertahankan jalur downlink menuju field.",
              "Gateway connects the LoRa MESH backbone to an MQTT broker over Wi-Fi while maintaining a downlink path to the field."),
            "implemented",
            [
                cards([
                    (T("Ingress", "Ingress"), T("LoRa MESH", "LoRa MESH")),
                    (T("Uplink IP", "IP uplink"), T("Wi-Fi STA", "Wi-Fi STA")),
                    (T("Messaging", "Messaging"), "MQTT"),
                    (T("Security option", "Security option"), T("CA-verified TLS", "CA-verified TLS")),
                ]),
                bullets([
                    T("Menerima frame dari CH melalui Radio B/MESH.", "Receives frames from CH through Radio B/MESH."),
                    T("Mempublikasikan uplink, status, dan topologi secara fungsional ke MQTT.", "Functionally publishes uplink, status, and topology over MQTT."),
                    T("Menerima command dari MQTT dan meneruskannya sebagai downlink MESH.", "Receives commands from MQTT and forwards them as MESH downlink."),
                    T("Menyediakan target firmware TLS dan non-TLS secara terpisah.", "Provides separate TLS and non-TLS firmware targets."),
                ]),
            ],
            T("Firmware Gateway, profil board, dan interface MQTT fungsional.", "Gateway firmware, board profiles, and functional MQTT interface."),
        ),
        page(
            T("Peran dalam arsitektur sistem", "Role in the system architecture"),
            T("Gateway merupakan batas antara jaringan radio field dan jaringan IP customer.",
              "Gateway is the boundary between the field radio network and the customer IP network."),
            "implemented",
            [
                diagram([
                    (T("CH MESH", "CH MESH"), T("Field network", "Field network")),
                    (T("Radio B", "Radio B"), T("SX1262", "SX1262")),
                    (T("Gateway", "Gateway"), T("Decode + queue", "Decode + queue")),
                    (T("Wi-Fi STA", "Wi-Fi STA"), T("Customer IP", "Customer IP")),
                    (T("MQTT broker", "MQTT broker"), T("Server boundary", "Server boundary")),
                ], [T("MESH", "MESH"), T("frame", "frame"), T("network", "network"), T("MQTT", "MQTT")],
                   T("Gambar 1. Batas radio-to-IP pada Gateway.", "Figure 1. Gateway radio-to-IP boundary.")),
                kv([
                    (T("Uplink", "Uplink"), T("MESH frame diterima, diproses, lalu diterbitkan melalui MQTT.", "MESH frame is received, processed, then published over MQTT.")),
                    (T("Downlink", "Downlink"), T("Command MQTT diterjemahkan ke jalur MESH menuju CH.", "MQTT command is translated into the MESH path toward CH.")),
                    (T("Trust boundary", "Trust boundary"), T("TLS, bila dipilih, berhenti pada broker; bukan TLS sepanjang LoRa.", "TLS, when selected, terminates at the broker; it does not span LoRa.")),
                ]),
            ],
            T("MESH receive/transmit, Wi-Fi STA, MQTT publish/subscribe, dan downlink source.", "MESH receive/transmit, Wi-Fi STA, MQTT publish/subscribe, and downlink source."),
        ),
        page(
            T("Varian PCB", "PCB variants"),
            T("Gateway memakai basis PCB yang sama dengan CH namun firmware mengaktifkan fungsi yang berbeda.",
              "Gateway uses the same PCB basis as CH but activates a different functional profile in firmware."),
            "implemented",
            [
                table([T("Varian produk", "Product variant"), T("Basis desain", "Design basis"), T("Pilihan standar", "Standard selection"), T("Pilihan TLS", "TLS selection")], [
                    [T("Gateway Rectangle", "Gateway Rectangle"), T("Profil hardware Rectangle", "Rectangle hardware profile"), T("Gateway Rectangle - standard", "Gateway Rectangle - standard"), T("Gateway Rectangle - TLS", "Gateway Rectangle - TLS")],
                    [T("Gateway Circle", "Gateway Circle"), T("Profil hardware Circle", "Circle hardware profile"), T("Gateway Circle - standard", "Gateway Circle - standard"), T("Gateway Circle - TLS", "Gateway Circle - TLS")],
                ], [0.23, 0.29, 0.24, 0.24]),
                bullets([
                    T("Profil pin Rectangle dan Circle berbeda.", "Rectangle and Circle pin profiles differ."),
                    T("Radio A/STAR dinonaktifkan pada firmware Gateway.", "Radio A/STAR is disabled in Gateway firmware."),
                    T("Radio B/MESH adalah radio aktif untuk kedua varian.", "Radio B/MESH is the active radio for both variants."),
                    T("Operator Hub mewajibkan pilihan bentuk board sebelum upload.", "Operator Hub requires board-form selection before upload."),
                ]),
            ],
            T("Dua profil hardware Gateway dan pemetaan pilihan firmware pada Operator Hub.", "Two Gateway hardware profiles and Operator Hub firmware-selection mapping."),
        ),
        page(
            T("Perangkat keras dan penggunaan radio", "Hardware and radio usage"),
            T("Gateway menggunakan MCU ESP32-S3 dan satu jalur radio MESH aktif pada PCB dual-radio.",
              "Gateway uses an ESP32-S3 MCU and one active MESH radio path on a dual-radio PCB."),
            "component",
            [
                table([T("Fungsi", "Function"), T("Komponen / jalur", "Component / path"), T("Status firmware", "Firmware status")], [
                    [T("MCU", "MCU"), "ESP32-S3-WROOM-1U-N16R8", T("Aktif", "Active")],
                    [T("Radio A", "Radio A"), "E22-900MM22S", T("Dinonaktifkan / tidak digunakan", "Disabled / unused")],
                    [T("Radio B", "Radio B"), "E22-900MM22S", T("Aktif sebagai LoRa MESH", "Active as LoRa MESH")],
                    [T("Wi-Fi", "Wi-Fi"), T("ESP32-S3 station interface", "ESP32-S3 station interface"), T("Aktif sebagai uplink IP native", "Active as native IP uplink")],
                    [T("Status LED", "Status LED"), T("Board-specific mapping", "Board-specific mapping"), T("Dikendalikan firmware", "Firmware-controlled")],
                ], [0.21, 0.39, 0.40]),
            ],
            T("Schematic/PCB, Gateway board headers, dan radio initialization source.", "Schematic/PCB, Gateway board headers, and radio-initialization source."),
        ),
        page(
            T("Matriks target firmware", "Firmware target matrix"),
            T("Empat target menjaga pilihan bentuk board dan transport MQTT tetap eksplisit.",
              "Four targets keep board-form and MQTT-transport choices explicit."),
            "implemented",
            [
                table([T("Board", "Board"), T("Transport", "Transport"), T("Pilihan Operator Hub", "Operator Hub selection"), T("Profil keamanan", "Security profile")], [
                    [T("Rectangle", "Rectangle"), T("MQTT tanpa TLS", "MQTT without TLS"), T("Gateway Rectangle - standard", "Gateway Rectangle - standard"), T("Tidak", "No")],
                    [T("Circle", "Circle"), T("MQTT tanpa TLS", "MQTT without TLS"), T("Gateway Circle - standard", "Gateway Circle - standard"), T("Tidak", "No")],
                    [T("Rectangle", "Rectangle"), "MQTT over TLS", T("Gateway Rectangle - TLS", "Gateway Rectangle - TLS"), T("Ya", "Yes")],
                    [T("Circle", "Circle"), "MQTT over TLS", T("Gateway Circle - TLS", "Gateway Circle - TLS"), T("Ya", "Yes")],
                ], [0.22, 0.30, 0.27, 0.21]),
                layers([
                    (T("Pilihan board", "Board selection"), T("Rectangle atau Circle", "Rectangle or Circle")),
                    (T("Pilihan transport", "Transport selection"), T("TLS atau non-TLS", "TLS or non-TLS")),
                    (T("Varian firmware", "Firmware variant"), T("Harus cocok dengan board dan transport", "Must match the board and transport")),
                    (T("Verifikasi perangkat", "Device verification"), T("Varian board, profil transport, dan kapabilitas TLS dibaca", "Board variant, transport profile, and TLS capability are read")),
                ], T("Gambar 2. Seleksi target Gateway dua dimensi.", "Figure 2. Two-dimensional Gateway target selection.")),
            ],
            T("Target firmware, pilihan Operator Hub, dan verifikasi kapabilitas melalui readback.", "Firmware targets, Operator Hub selections, and capability verification through readback."),
        ),
        page(
            T("Antarmuka LoRa MESH", "LoRa MESH interface"),
            T("Gateway berbagi default MESH dengan CH dan menolak carrier di luar 920-923 MHz.",
              "Gateway shares MESH defaults with CH and rejects carriers outside 920-923 MHz."),
            "implemented",
            [
                table([T("Parameter", "Parameter"), T("Default firmware", "Firmware default"), T("Status", "Status")], [
                    [T("Carrier", "Carrier"), "921.0 MHz", T("Accepted 920-923 MHz inclusive", "Accepted 920-923 MHz inclusive")],
                    [T("Bandwidth", "Bandwidth"), "125 kHz", T("Harus cocok dengan CH MESH", "Must match CH MESH")],
                    [T("Spreading factor", "Spreading factor"), "SF9", T("Default MESH", "MESH default")],
                    [T("Coding rate", "Coding rate"), "4/5", T("Default MESH", "MESH default")],
                    [T("TX setting", "TX setting"), "17 dBm", T("Bukan output terukur", "Not measured output")],
                    [T("Antena", "Antenna"), "8 dBi", T("Konfigurasi produk", "Product configuration")],
                ], [0.28, 0.27, 0.45]),
                note(T("Perhitungan nominal 17 dBm + 8 dBi menghasilkan 25 dBm sebelum rugi kabel dan konektor.",
                       "The nominal 17 dBm + 8 dBi calculation yields 25 dBm before cable and connector losses.")),
            ],
            T("LoraMeshConfig, runtime carrier validation, NVS, dan konfigurasi antena produk.", "LoraMeshConfig, runtime carrier validation, NVS, and product antenna configuration."),
        ),
        page(
            T("Konfigurasi MESH dan pembacaan kembali", "MESH configuration and readback"),
            T("Konfigurasi radio disimpan ke NVS, diverifikasi, dan dimuat kembali pada boot.",
              "Radio configuration is stored in NVS, verified, and reloaded at boot."),
            "implemented",
            [
                layers([
                    (T("Input engineer", "Engineer input"), T("Parameter MESH", "MESH parameters")),
                    (T("Validation", "Validation"), T("Carrier 920-923 MHz dan field lain valid", "Carrier 920-923 MHz and other fields valid")),
                    (T("NVS write", "NVS write"), T("Konfigurasi tersimpan", "Configuration stored")),
                    (T("Readback", "Readback"), T("Nilai dibaca dan dibandingkan", "Values are read and compared")),
                    (T("Runtime", "Runtime"), T("Konfigurasi valid digunakan", "Valid configuration is used")),
                ], T("Gambar 3. Siklus konfigurasi MESH Gateway.", "Figure 3. Gateway MESH configuration cycle.")),
                note(T("Device readback harus dicatat setelah commissioning karena NVS dapat mengganti default firmware.",
                       "Device readback must be recorded after commissioning because NVS can override firmware defaults."), "success"),
            ],
            T("Gateway MESH validation, NVS persistence, readback, dan boot load.", "Gateway MESH validation, NVS persistence, readback, and boot load."),
        ),
        page(
            T("Antarmuka jaringan Wi-Fi", "Wi-Fi network interface"),
            T("Interface jaringan native Gateway adalah Wi-Fi station.",
              "The Gateway native network interface is Wi-Fi station."),
            "implemented",
            [
                cards([
                    (T("Mode", "Mode"), "Wi-Fi STA"),
                    (T("Uplink", "Uplink"), T("Jaringan IP", "IP network")),
                    (T("Protocol", "Protocol"), "MQTT"),
                    (T("Ethernet native", "Native Ethernet"), T("Tidak", "No")),
                ]),
                kv([
                    (T("Provisioning", "Provisioning"), T("SSID dan network credential dikonfigurasi pada perangkat.", "SSID and network credentials are configured on the device.")),
                    (T("Site dependency", "Site dependency"), T("DHCP/static policy, VLAN, NAC, DNS, NTP, dan firewall ditentukan customer.", "DHCP/static policy, VLAN, NAC, DNS, NTP, and firewall are customer-defined.")),
                    (T("Opsi kabel", "Wired option"), T("Konverter Wi-Fi-to-Ethernet eksternal dapat dipertimbangkan sebagai aksesori deployment; bukan interface native produk.", "An external Wi-Fi-to-Ethernet converter may be considered as a deployment accessory; it is not a native product interface.")),
                ]),
            ],
            T("WiFi STA implementation dan tidak adanya Ethernet stack/interface native.", "Wi-Fi STA implementation and absence of a native Ethernet stack/interface."),
        ),
        page(
            T("Fungsi MQTT", "MQTT functions"),
            T("MQTT membawa informasi uplink/status/topologi ke broker dan command kembali ke Gateway.",
              "MQTT carries uplink/status/topology information to the broker and commands back to the Gateway."),
            "implemented",
            [
                sequence([T("CH", "CH"), T("Gateway", "Gateway"), T("Broker", "Broker"), T("Server", "Server")], [
                    (0, 1, T("MESH uplink", "MESH uplink")),
                    (1, 2, T("MQTT publish", "MQTT publish")),
                    (2, 3, T("MQTT deliver", "MQTT deliver")),
                    (3, 2, T("Command publish", "Command publish")),
                    (2, 1, T("Command deliver", "Command deliver")),
                    (1, 0, T("MESH downlink", "MESH downlink")),
                ], T("Gambar 4. Uplink dan downlink melalui MQTT.", "Figure 4. MQTT uplink and downlink.")),
                note(T("Publikasi uplink dan penerimaan perintah berjalan setelah sesi broker aktif.",
                       "Uplink publication and command reception operate after the broker session is established.")),
            ],
            T("Gateway MQTT publish/subscribe, uplink, topology/status, dan command downlink source.", "Gateway MQTT publish/subscribe, uplink, topology/status, and command-downlink source."),
        ),
        page(
            T("MQTT over TLS", "MQTT over TLS"),
            T("Profil TLS menggunakan klien TLS, Root CA, dan trusted time sebelum koneksi broker.",
              "The TLS profile uses a TLS client, Root CA, and trusted time before broker connection."),
            "implemented",
            [
                layers([
                    (T("TLS-capable firmware", "TLS-capable firmware"), T("Gateway Rectangle - TLS atau Gateway Circle - TLS", "Gateway Rectangle - TLS or Gateway Circle - TLS")),
                    (T("Root CA", "Root CA"), T("PEM wajib diprovisioning dan lulus validasi", "PEM must be provisioned and pass validation")),
                    (T("Waktu tepercaya", "Trusted time"), T("Koneksi diblokir sampai host NTP valid dan waktu sistem siap", "Connection is blocked until the NTP host is valid and system time is ready")),
                    (T("Klien aman", "Secure client"), T("Mendukung verifikasi CA; tidak menyediakan mode tidak aman", "Supports CA verification; no insecure mode is provided")),
                    (T("Sesi broker", "Broker session"), T("Mendukung MQTT over TLS setelah seluruh gate valid", "Supports MQTT over TLS after all gates are valid")),
                ], T("Gambar 5. Gate koneksi MQTT/TLS.", "Figure 5. MQTT/TLS connection gates.")),
                bullets([
                    T("Firmware memblokir TLS bila Root CA atau trusted time belum valid.", "Firmware blocks TLS when Root CA or trusted time is invalid."),
                    T("TLS melindungi segmen Gateway-ke-broker, bukan seluruh jalur radio.", "TLS protects the Gateway-to-broker segment, not the entire radio path."),
                    T("Status koneksi broker, validitas CA, dan kesiapan waktu tersedia melalui readback perangkat.", "Broker connection, CA validity, and trusted-time readiness are available through device readback."),
                ]),
            ],
            T("Varian firmware TLS, validasi Root CA, dan gerbang kesiapan waktu.", "TLS firmware variants, Root CA validation, and trusted-time readiness gates."),
        ),
        page(
            T("Firmware non-TLS", "Non-TLS firmware"),
            T("Target non-TLS dipertahankan sebagai firmware terpisah dan tidak digantikan oleh varian TLS.",
              "The non-TLS target is retained as separate firmware and is not replaced by the TLS variant."),
            "implemented",
            [
                table([T("Area", "Area"), T("Non-TLS", "Non-TLS"), T("TLS", "TLS")], [
                    [T("Dukungan board", "Board support"), T("Rectangle + Circle", "Rectangle + Circle"), T("Rectangle + Circle", "Rectangle + Circle")],
                    [T("Transport MQTT", "MQTT transport"), T("TCP tanpa TLS", "TCP without TLS"), T("TLS terverifikasi CA", "CA-verified TLS")],
                    [T("Root CA", "Root CA"), T("Tidak digunakan", "Not used"), T("Wajib", "Required")],
                    [T("Waktu tepercaya", "Trusted time"), T("Bukan gate TLS", "Not a TLS gate"), T("Wajib untuk TLS", "Required for TLS")],
                    [T("Pemilihan operator", "Operator selection"), T("Eksplisit", "Explicit"), T("Eksplisit", "Explicit")],
                ], [0.30, 0.35, 0.35]),
                note(T("Pilih profil TLS untuk deployment yang membutuhkan transport broker terenkripsi dan verifikasi sertifikat.",
                       "Select the TLS profile for deployments requiring encrypted broker transport and certificate verification.")),
            ],
            T("Empat target firmware dan pemisahan compile-time transport.", "Four firmware targets and compile-time transport separation."),
        ),
        page(
            T("Antrean MQTT dan perilaku offline", "MQTT queue and offline behavior"),
            T("Gateway menyediakan queue RAM terbatas untuk publikasi ketika koneksi MQTT belum tersedia.",
              "Gateway provides a bounded RAM queue for publications when MQTT is unavailable."),
            "implemented",
            [
                cards([
                    (T("Kapasitas", "Capacity"), T("8 publikasi", "8 publications")),
                    (T("Payload", "Payload"), "1-1023 bytes"),
                    (T("Media", "Medium"), "RAM"),
                    (T("Persistence", "Persistence"), T("Volatile", "Volatile")),
                ]),
                layers([
                    (T("Percobaan publikasi", "Publish attempt"), T("Jika broker tersedia, kirim langsung", "Send directly when broker is available")),
                    (T("Broker tidak tersedia", "Broker unavailable"), T("Simpan pada antrean bila ada ruang", "Queue when space is available")),
                    (T("Antrean penuh", "Queue full"), T("Item baru ditolak", "New item is rejected")),
                    (T("Restart/kehilangan daya", "Restart/power loss"), T("Isi antrean hilang", "Queue contents are lost")),
                ], T("Gambar 6. Perilaku buffering MQTT.", "Figure 6. MQTT buffering behavior.")),
            ],
            T("GwConfig queue limits dan Gateway enqueue/flush/drop implementation.", "GwConfig queue limits and Gateway enqueue/flush/drop implementation."),
        ),
        page(
            T("Jalur perintah downlink", "Command downlink path"),
            T("Gateway menerima command dari broker, memvalidasi target fungsional, lalu meneruskannya melalui MESH.",
              "Gateway receives commands from the broker, validates the functional target, then forwards them over MESH."),
            "implemented",
            [
                sequence([T("Server", "Server"), T("Broker", "Broker"), T("Gateway", "Gateway"), T("CH route", "CH route"), T("GasleakDetector", "GasleakDetector")], [
                    (0, 1, T("Authenticated command", "Authenticated command")),
                    (1, 2, T("MQTT deliver", "MQTT deliver")),
                    (2, 3, T("MESH downlink", "MESH downlink")),
                    (3, 4, T("Serving-CH delivery", "Serving-CH delivery")),
                    (4, 3, T("Device response if available", "Device response if available")),
                ], T("Gambar 7. Jalur command melalui Gateway.", "Figure 7. Command path through the Gateway.")),
            ],
            T("MQTT command input, Gateway downlink, CH routing, dan endpoint receive-window behavior.", "MQTT command input, Gateway downlink, CH routing, and endpoint receive-window behavior."),
        ),
        page(
            T("Penyimpanan konfigurasi transaksional", "Transactional configuration storage"),
            T("Wi-Fi/MQTT configuration menggunakan journal NVS dua slot dengan readback sebelum selector terakhir di-commit.",
              "Wi-Fi/MQTT configuration uses a two-slot NVS journal with readback before committing the final selector."),
            "implemented",
            [
                sequence([T("Operator", "Operator"), T("Active slot", "Active slot"), T("Inactive slot", "Inactive slot"), T("Readback", "Readback"), T("Selector", "Selector")], [
                    (0, 2, T("Write new config", "Write new config")),
                    (2, 3, T("Read + validate", "Read + validate")),
                    (3, 4, T("Commit active selector", "Commit active selector")),
                    (4, 1, T("Use selected slot", "Use selected slot")),
                ], T("Gambar 8. Journal konfigurasi dua slot.", "Figure 8. Two-slot configuration journal.")),
                bullets([
                    T("Firmware menyediakan fallback/recovery apabila slot tidak valid.", "Firmware provides fallback/recovery when a slot is invalid."),
                ]),
            ],
            T("NVS journal, inactive-slot write, readback verification, dan selector commit source.", "NVS journal, inactive-slot write, readback verification, and selector-commit source."),
        ),
        page(
            T("Penyediaan melalui Operator Hub", "Provisioning through Operator Hub"),
            T("Operator Hub mengunci board, transport, varian firmware, dan material TLS sebelum upload/configuration diterima.",
              "Operator Hub locks board, transport, firmware variant, and TLS material before upload/configuration is accepted."),
            "implemented",
            [
                table([T("Gate", "Gate"), T("Pemeriksaan", "Check")], [
                    [T("Board", "Board"), T("Rectangle atau Circle harus dipilih.", "Rectangle or Circle must be selected.")],
                    [T("Transport", "Transport"), T("TLS atau non-TLS harus dipilih.", "TLS or non-TLS must be selected.")],
                    [T("Firmware", "Firmware"), T("Versi dan kecocokan varian firmware diperiksa.", "Firmware version and variant compatibility are checked.")],
                    [T("TLS material", "TLS material"), T("Root CA PEM dan NTP host diwajibkan pada target TLS.", "Root CA PEM and NTP host are required for TLS targets.")],
                    [T("Verifikasi perangkat", "Device verification"), T("Varian board, profil transport, dan kapabilitas TLS dibaca kembali.", "Board variant, transport profile, and TLS capability are read back.")],
                ], [0.27, 0.73]),
                note(T("Material TLS ditolak pada firmware non-TLS agar operator tidak salah mengira transport aman sedang aktif.",
                       "TLS material is rejected on non-TLS firmware so the operator cannot mistake the active transport for a secure one."), "success"),
            ],
            T("Pemetaan board/transport Operator Hub, validasi provisioning TLS, dan readback perangkat.", "Operator Hub board/transport mapping, TLS provisioning validation, and device readback."),
        ),
        page(
            T("Prasyarat penerapan jaringan", "Network deployment prerequisites"),
            T("Deployment customer membutuhkan keputusan jaringan dan broker di luar firmware Gateway.",
              "Customer deployment requires network and broker decisions outside Gateway firmware."),
            "boundary",
            [
                table([T("Area", "Area"), T("Input deployment yang harus tersedia", "Required deployment input")], [
                    [T("Wi-Fi", "Wi-Fi"), T("SSID, authentication, address policy, VLAN/NAC, dan coverage.", "SSID, authentication, address policy, VLAN/NAC, and coverage.")],
                    [T("Name/time", "Name/time"), T("DNS dan NTP yang dapat dijangkau target TLS.", "DNS and NTP reachable by the TLS target.")],
                    [T("Broker", "Broker"), T("FQDN/IP, port, credential, CA chain, ACL, dan topic policy.", "FQDN/IP, port, credentials, CA chain, ACL, and topic policy.")],
                    [T("Firewall", "Firewall"), T("Egress/return traffic untuk Wi-Fi, DNS, NTP, dan MQTT/TLS.", "Egress/return traffic for Wi-Fi, DNS, NTP, and MQTT/TLS.")],
                    [T("Catatan komisioning", "Commissioning record"), T("CONNACK, publish/subscribe, reconnect, log, dan hasil validasi sertifikat.", "CONNACK, publish/subscribe, reconnect, logs, and certificate-validation results.")],
                ], [0.25, 0.75]),
                note(T("Penerimaan deployment mencakup CONNACK, publish/subscribe, reconnect, dan validasi sertifikat.", "Deployment acceptance covers CONNACK, publish/subscribe, reconnect, and certificate validation.")),
            ],
            T("Kebutuhan jaringan dan kriteria penerimaan deployment customer.", "Customer-deployment network requirements and acceptance criteria."),
        ),
        page(
            T("Status dan diagnostik", "Status and diagnostics"),
            T("Readback membedakan identitas firmware, board, transport, radio, Wi-Fi, MQTT, TLS, dan status antrean.",
              "Readback separates firmware identity, board, transport, radio, Wi-Fi, MQTT, TLS, and queue state."),
            "implemented",
            [
                table([T("Kelompok", "Group"), T("Contoh readback engineering", "Engineering readback examples")], [
                    [T("Identity", "Identity"), T("Firmware/protocol version dan Gateway identity", "Firmware/protocol version and Gateway identity")],
                    [T("Hardware", "Hardware"), T("Varian board dan peran radio aktif", "Board variant and active-radio role")],
                    [T("RF", "RF"), T("Carrier, BW, SF, CR, TX setting, preamble", "Carrier, BW, SF, CR, TX setting, preamble")],
                    [T("Network", "Network"), T("Wi-Fi connection state dan address information", "Wi-Fi connection state and address information")],
                    ["MQTT", T("Transport mode, broker state, reconnect, dan queue depth", "Transport mode, broker state, reconnect, and queue depth")],
                    ["TLS", T("Kapabilitas TLS serta kesiapan CA/waktu pada target TLS", "TLS capability and CA/time readiness on TLS targets")],
                ], [0.27, 0.73]),
                note(T("Status dan readback perangkat menampilkan hasil koneksi MQTT/TLS serta kedalaman antrean aktif.", "Device status and readback expose the MQTT/TLS connection result and active queue depth."), "success"),
            ],
            T("Kontrak status/readback Gateway dan verifikasi perangkat melalui Operator Hub.", "Gateway status/readback contract and device verification through Operator Hub."),
        ),
        page(
            T("Referensi dan riwayat revisi", "References and revision history"),
            T("Referensi komponen melengkapi identifikasi hardware dan antarmuka produk.",
              "Component references support hardware and product-interface identification."),
            "reference",
            [
                table([T("Referensi", "Reference"), T("Dokumen", "Document")], [
                    ["R1", "Espressif - ESP32-S3-WROOM-1/1U Datasheet v1.8"],
                    ["R2", "EBYTE - E22-900MM22S module documentation"],
                    ["R3", "OASIS - MQTT Version 3.1.1, OASIS Standard"],
                    ["R4", "IETF RFC 5280 - Internet X.509 Public Key Infrastructure Certificate and CRL Profile"],
                ], [0.14, 0.86]),
                table([T("Rev", "Rev"), T("Perubahan", "Change")], [
                    ["4.0", T("Pembaruan struktur dan spesifikasi teknis.", "Updated technical structure and specifications.")],
                ], [0.18, 0.82]),
            ],
            T("Dokumentasi komponen, implementasi Gateway, dan revisi teknis saat ini.", "Component documentation, Gateway implementation, and current technical revision."),
        ),
    ]
    return d


def server_document() -> dict[str, Any]:
    d = common_meta(
        slug="Server",
        product="Server",
        status=T("Prototipe Engineering", "Engineering Prototype"),
        firmware="Server Application | Protocol 0.2.0",
        subtitle=T(
            "Aplikasi Node-RED untuk masuknya data MQTT, validasi integritas, routing alarm, topologi, dataset, dan perintah.",
            "Node-RED application for MQTT ingestion, integrity validation, alarm routing, topology, datasets, and commands.",
        ),
        cover_nodes=[
            (T("Broker", "Broker"), T("MQTT ingress", "MQTT ingress")),
            (T("Validasi", "Validation"), T("CRC + skema", "CRC + schema")),
            (T("Keamanan", "Security"), T("AES-128-GCM", "AES-128-GCM")),
            (T("Aplikasi", "Application"), T("Alarm + topologi", "Alarm + topology")),
            (T("Keluaran", "Outputs"), T("Dataset + perintah", "Dataset + command")),
        ],
        cover_links=[T("langganan", "subscribe"), T("gerbang", "gate"), T("rute", "route"), T("simpan/kirim", "store/send")],
        facts=[
            (T("TARGET HOST", "TARGET HOST"), T("VM customer", "Customer VM")),
            (T("RUNTIME", "RUNTIME"), "Node-RED"),
            (T("DATA SECURITY", "DATA SECURITY"), "AES-128-GCM"),
            (T("DATA ENGINEERING", "ENGINEERING DATA"), "MySQL / CSV"),
        ],
        abbreviations=[
            ("AES-GCM", T("Authenticated encryption dengan Galois/Counter Mode", "Authenticated encryption using Galois/Counter Mode")),
            ("CA", T("Certificate Authority", "Certificate Authority")),
            ("CRC", T("Cyclic Redundancy Check", "Cyclic Redundancy Check")),
            ("MQTT", T("Message Queuing Telemetry Transport", "Message Queuing Telemetry Transport")),
            ("NVM", T("Non-volatile memory/state", "Non-volatile memory/state")),
            ("TLS", T("Transport Layer Security", "Transport Layer Security")),
            ("VM", T("Virtual machine pada infrastruktur customer", "Virtual machine on customer infrastructure")),
            ("UI", T("User interface", "User interface")),
        ],
    )
    d["chapters"] = [
        page(
            T("Ikhtisar aplikasi", "Application overview"),
            T("Server menyediakan pipeline pemrosesan data dan perintah pada sisi aplikasi, dengan target penerapan di VM customer.",
              "The Server provides an application-side data and command pipeline targeted for deployment on a customer VM."),
            "implemented",
            [
                cards([
                    (T("Runtime", "Runtime"), "Node-RED"),
                    (T("Ingress", "Ingress"), "MQTT"),
                    (T("Integrity", "Integrity"), T("CRC + AES-GCM", "CRC + AES-GCM")),
                    (T("Target", "Target"), T("VM customer", "Customer VM")),
                ]),
                bullets([
                    T("Menerima dan memisahkan data uplink, status, topologi, serta jalur integritas.", "Receives and separates uplink, status, topology, and integrity-path data."),
                    T("Memvalidasi frame sebelum data masuk jalur aplikasi normal.", "Validates frames before data enters the normal application path."),
                    T("Merutekan event alarm terautentikasi dan memisahkan masukan manual/uji.", "Routes authenticated alarm events and separates manual/test input."),
                    T("Membentuk perintah mode tingkat tinggi yang diautentikasi.", "Builds authenticated high-level mode commands."),
                ]),
            ],
            T("Node-RED server source, flow generator, decoder, command builder, dan dataset recorder.", "Node-RED server source, flow generator, decoder, command builder, and dataset recorder."),
        ),
        page(
            T("Arsitektur logis Server", "Server logical architecture"),
            T("Pipeline memisahkan transport, integritas, routing aplikasi, penyimpanan, dan perintah downlink.",
              "The pipeline separates transport, integrity, application routing, storage, and command downlink."),
            "implemented",
            [
                diagram([
                    (T("Masuk MQTT", "MQTT ingress"), T("Masukan broker", "Broker input")),
                    (T("Gerbang frame", "Frame gate"), T("Panjang + CRC", "Length + CRC")),
                    (T("Gerbang keamanan", "Security gate"), T("AES-GCM + replay", "AES-GCM + replay")),
                    (T("Aplikasi", "Application"), T("Alarm + topologi", "Alarm + topology")),
                    (T("Keluaran", "Outputs"), T("Dataset / perintah", "Dataset / command")),
                ], [T("terima", "receive"), T("validasi", "validate"), T("otorisasi", "authorize"), T("rute", "route")],
                   T("Gambar 1. Pipeline logis aplikasi Server.", "Figure 1. Server application logical pipeline.")),
                kv([
                    (T("Transport", "Transport"), T("MQTT melalui broker yang dipilih untuk deployment.", "MQTT through the broker selected for deployment.")),
                    (T("Integritas", "Integrity"), T("Struktur frame, panjang, CRC, autentikasi, pemeriksaan semantik, dan kebijakan replay.", "Frame structure, length, CRC, authentication, semantic checks, and replay policy.")),
                    (T("Aplikasi", "Application"), T("Data hasil dekode, routing alarm, topologi, UI engineering, dan perintah.", "Decoded data, alarm routing, topology, engineering UI, and commands.")),
                ]),
            ],
            T("Flow generator, decoder pipeline, alarm output, topology view, dan command builder.", "Flow generator, decoder pipeline, alarm output, topology view, and command builder."),
        ),
        page(
            T("Kategori input MQTT", "MQTT input categories"),
            T("Masukan dipisahkan secara fungsional agar status, topologi, payload, dan event integritas tidak diperlakukan sebagai data yang sama.",
              "Inputs are functionally separated so status, topology, payload, and integrity events are not treated as the same data."),
            "implemented",
            [
                table([T("Kategori", "Category"), T("Tujuan", "Purpose"), T("Jalur lanjutan", "Downstream path")], [
                    [T("Uplink perangkat", "Device uplink"), T("Membawa frame/data dari field", "Carries frames/data from the field"), T("Validasi dan dekode", "Validation and decode")],
                    [T("Status Gateway", "Gateway status"), T("Keadaan komunikasi Gateway", "Gateway communication state"), T("Pemantauan/status", "Monitoring/status")],
                    [T("Topologi", "Topology"), T("Informasi parent, discovery, dan rute", "Parent, discovery, and route information"), T("Tampilan topologi engineering", "Engineering topology view")],
                    [T("Integritas/mentah", "Integrity/raw"), T("Kegagalan validasi atau observability", "Validation failures or observability"), T("Jalur karantina/integritas", "Quarantine/integrity path")],
                ], [0.24, 0.38, 0.38]),
                note(T("Setiap kategori input dipetakan ke jalur pemrosesan yang terpisah.",
                       "Each input category is mapped to a separate processing path.")),
            ],
            T("Node MQTT input pada generated flow dan fungsi routing Server.", "MQTT input nodes in the generated flow and Server routing functions."),
        ),
        page(
            T("Validasi frame", "Frame validation"),
            T("Frame harus lolos pemeriksaan struktur sebelum autentikasi dan pemrosesan semantik.",
              "A frame must pass structural checks before authentication and semantic processing."),
            "implemented",
            [
                layers([
                    (T("Terima", "Receive"), T("Pesan diterima dari MQTT", "Message received from MQTT")),
                    (T("Struktur", "Structure"), T("Format dan field wajib", "Format and mandatory fields")),
                    (T("Panjang", "Length"), T("Ukuran frame/payload diperiksa", "Frame/payload size is checked")),
                    (T("CRC", "CRC"), T("Integritas transport diperiksa", "Transport integrity is checked")),
                    (T("Keamanan/semantik", "Security/semantic"), T("Masuk ke gerbang autentikasi", "Enters the authentication gate")),
                ], T("Gambar 2. Urutan gate validasi frame.", "Figure 2. Frame-validation gate sequence.")),
                bullets([
                    T("Frame yang gagal struktur/panjang/CRC tidak menjadi data produksi hasil dekode.", "Frames failing structure/length/CRC do not become decoded production data."),
                    T("Kesalahan validasi tetap dapat diarahkan ke jalur integritas/diagnostik.", "Validation errors can still be routed to an integrity/diagnostic path."),
                ]),
            ],
            T("Decoder structure, length, dan CRC checks.", "Decoder structure, length, and CRC checks."),
        ),
        page(
            T("Autentikasi AES-128-GCM", "AES-128-GCM authentication"),
            T("Payload GasleakDetector diautentikasi dan didekripsi dengan runtime key yang wajib tersedia.",
              "GasleakDetector payloads are authenticated and decrypted with a required runtime key."),
            "implemented",
            [
                layers([
                    (T("Payload terenkripsi", "Encrypted payload"), T("Diterima setelah gerbang frame", "Received after the frame gate")),
                    (T("Kunci runtime", "Runtime key"), T("Wajib dan dipetakan ke ID kunci", "Required and mapped to key ID")),
                    (T("AES-128-GCM", "AES-128-GCM"), T("Dekripsi + pemeriksaan tag autentikasi", "Decrypt + authentication-tag check")),
                    (T("Validasi semantik", "Semantic validation"), T("Batasan identitas/peran dan nilai", "Identity/role and value constraints")),
                    (T("Keluaran valid", "Valid output"), T("Baru masuk routing aplikasi", "Only then enters application routing")),
                ], T("Gambar 3. Security gate payload field.", "Figure 3. Field-payload security gate.")),
                note(T("Kunci runtime wajib tersedia; payload ditolak jika autentikasi tidak dapat diselesaikan.",
                       "A runtime key is required; a payload is rejected when authentication cannot be completed."), "success"),
            ],
            T("AES-GCM decoder, mandatory runtime key, key ID validation, dan semantic validation.", "AES-GCM decoder, mandatory runtime key, key ID validation, and semantic validation."),
        ),
        page(
            T("Pemutaran ulang, penggunaan ulang nonce, dan karantina", "Replay, nonce reuse, and quarantine"),
            T("Data autentik tetapi berulang tetap dapat ditolak agar event lama tidak diproses ulang sebagai data baru.",
              "Authenticated but repeated data can still be rejected so old events are not reprocessed as new data."),
            "implemented",
            [
                table([T("Kondisi", "Condition"), T("Keputusan", "Decision"), T("Jalur", "Path")], [
                    [T("Autentikasi gagal", "Authentication failure"), T("Tolak", "Reject"), T("Integritas/karantina", "Integrity/quarantine")],
                    [T("Replay terdeteksi", "Replay detected"), T("Tolak", "Reject"), T("Integritas/karantina", "Integrity/quarantine")],
                    [T("Nonce digunakan ulang", "Nonce reuse"), T("Tolak", "Reject"), T("Integritas/karantina", "Integrity/quarantine")],
                    [T("Semantik tidak valid", "Semantic invalid"), T("Tolak", "Reject"), T("Integritas/karantina", "Integrity/quarantine")],
                    [T("Valid dan baru", "Valid and fresh"), T("Terima", "Accept"), T("Hasil dekode/aplikasi", "Decoded/application")],
                ], [0.30, 0.22, 0.48]),
                kv([
                    (T("Keadaan anti-replay", "Anti-replay state"), T("Deployment Server wajib mengonfigurasi penyimpanan persisten.", "The Server deployment must configure persistent storage.")),
                    (T("Pemulihan layanan", "Service recovery"), T("Dengan konfigurasi tersebut, status anti-replay dimuat kembali setelah layanan dimulai ulang.", "With that configuration, anti-replay state is reloaded after a service restart.")),
                ]),
            ],
            T("Kebijakan anti-replay, pelacakan nonce, routing karantina, dan penyimpanan status persisten.", "Anti-replay policy, nonce tracking, quarantine routing, and persistent state storage."),
        ),
        page(
            T("Penanganan alarm dan event", "Alarm and event handling"),
            T("Server hanya merutekan alarm setelah frame lolos gerbang integritas dan autentikasi.",
              "The Server routes alarms only after a frame passes integrity and authentication gates."),
            "implemented",
            [
                sequence([T("MQTT", "MQTT"), T("Decoder", "Decoder"), T("Gerbang integritas", "Integrity gate"), T("Rute alarm", "Alarm route"), T("UI engineering", "Engineering UI")], [
                    (0, 1, T("Terima frame", "Receive frame")),
                    (1, 2, T("Validasi + autentikasi", "Validate + authenticate")),
                    (2, 3, T("Event alarm valid", "Valid alarm event")),
                    (3, 4, T("Rute/tampilkan", "Route/display")),
                ], T("Gambar 4. Alarm routing pada Server.", "Figure 4. Server alarm routing.")),
                table([T("Masukan", "Input"), T("Jalur alarm produksi", "Production alarm path")], [
                    [T("Alarm field terautentikasi", "Authenticated field alarm"), T("Dapat dirutekan", "May be routed")],
                    [T("Masukan manual/uji", "Manual/test input"), T("Dipisahkan", "Separated")],
                    [T("Autentikasi/replay gagal", "Failed authentication/replay"), T("Dikarantina; bukan alarm produksi", "Quarantined; not a production alarm")],
                ], [0.43, 0.57]),
                note(T("Server menghasilkan event alarm aplikasi; integrasi notifikasi eksternal menggunakan antarmuka deployment customer.",
                       "The Server produces application alarm events; external notification integration uses customer-deployment interfaces.")),
            ],
            T("Decoder alarm routing dan separation manual/test/integrity paths.", "Decoder alarm routing and manual/test/integrity-path separation."),
        ),
        page(
            T("Tampilan topologi engineering", "Engineering topology view"),
            T("Server menyediakan tampilan hubungan Gateway, CH, GasleakDetector, parent aktif, kandidat discovery, dan rute.",
              "The Server provides a view of Gateway, CH, GasleakDetector, active parent, discovery candidates, and routes."),
            "implemented",
            [
                diagram([
                    (T("Gateway", "Gateway"), T("Root", "Root")),
                    (T("CH parent", "CH parent"), T("Rute aktif", "Active route")),
                    (T("CH child", "CH child"), T("Multi-hop", "Multi-hop")),
                    (T("GasleakDetector", "GasleakDetector"), T("Endpoint yang dilayani", "Served endpoint")),
                ], [T("parent", "parent"), T("child", "child"), T("serves", "serves")],
                   T("Gambar 5. Informasi yang tersedia pada tampilan topologi.", "Figure 5. Information available in the topology view.")),
                bullets([
                    T("Tampilan dapat menunjukkan parent terpasang, kandidat discovery, dan lineage rute.", "The view can show installed parent, discovery candidates, and route lineage."),
                    T("Flow topologi merupakan bagian dari aplikasi Server berbasis Node-RED.", "The topology flow is part of the Node-RED-based Server application."),
                    T("Konfigurasi Gateway dan jaringan disesuaikan untuk setiap deployment customer.", "Gateway and network configuration is adapted for each customer deployment."),
                ]),
            ],
            T("Node-RED topology generator/view dan model runtime Server.", "Node-RED topology generator/view and Server runtime model."),
        ),
        page(
            T("Perintah mode tingkat tinggi", "High-level mode command"),
            T("Server dapat membentuk perintah pergantian mode operasional yang diautentikasi untuk diteruskan menuju GasleakDetector.",
              "The Server can build an authenticated operational-mode command for forwarding toward GasleakDetector."),
            "implemented",
            [
                sequence([T("Pengguna berwenang", "Authorized user"), T("Server", "Server"), T("Broker", "Broker"), T("Gateway/CH", "Gateway/CH"), T("GasleakDetector", "GasleakDetector")], [
                    (0, 1, T("Permintaan mode + token autentikasi", "Mode request + auth token")),
                    (1, 1, T("Validasi + autentikasi", "Validate + authenticate")),
                    (1, 2, T("Publikasikan perintah", "Publish command")),
                    (2, 3, T("Kirim downlink", "Deliver downlink")),
                    (3, 4, T("Kirim dalam jendela penerimaan", "Deliver in receive window")),
                ], T("Gambar 6. Command path dari Server ke field.", "Figure 6. Server-to-field command path.")),
                bullets([
                    T("Perintah eksternal membutuhkan token otorisasi.", "External commands require an authorization token."),
                    T("Payload perintah diautentikasi pada lapisan aplikasi.", "Command payload is authenticated at the application layer."),
                    T("Cakupan saat ini adalah perubahan mode tingkat tinggi, bukan kendali jarak jauh umum.", "Current scope is high-level mode change, not general remote control."),
                ]),
            ],
            T("Command builder authorization/authentication dan field downlink path.", "Command-builder authorization/authentication and field downlink path."),
        ),
        page(
            T("Koneksi Server ke broker dengan TLS", "Server-to-broker TLS connection"),
            T("Flow yang dihasilkan mendukung koneksi Node-RED ke broker menggunakan credential dan TLS terverifikasi CA.",
              "The generated flow supports a Node-RED-to-broker connection using credentials and CA-verified TLS."),
            "implemented",
            [
                layers([
                    (T("Node-RED", "Node-RED"), T("Klien MQTT", "MQTT client")),
                    (T("Credential", "Credentials"), T("Disediakan saat deployment", "Deployment-provided")),
                    (T("Kepercayaan CA", "CA trust"), T("Verifikasi sertifikat broker", "Broker certificate verification")),
                    (T("Sesi TLS", "TLS session"), T("Server/Node-RED ke broker", "Server/Node-RED to broker")),
                    (T("Broker", "Broker"), T("Batas kepercayaan", "Trust boundary")),
                ], T("Gambar 7. Sesi TLS Server-ke-broker.", "Figure 7. Server-to-broker TLS session.")),
                note(T("Ini adalah sesi TLS terpisah dari Gateway-ke-broker. Tidak boleh disebut TLS end-to-end dari GasleakDetector ke Server.",
                       "This is separate from the Gateway-to-broker TLS session. It must not be described as end-to-end TLS from GasleakDetector to Server."), "caution"),
            ],
            T("Node-RED MQTT TLS generation, CA configuration, dan credential support.", "Node-RED MQTT TLS generation, CA configuration, and credential support."),
        ),
        page(
            T("Persistensi dataset: MySQL dan CSV", "Dataset persistence: MySQL and CSV"),
            T("Perekam dataset engineering memvalidasi rekaman, menulis ke MySQL ketika dikonfigurasi, dan membuat salinan CSV untuk setiap rekaman yang diterima.",
              "The engineering dataset recorder validates records, writes to MySQL when configured, and creates a CSV copy for every accepted record."),
            "implemented",
            [
                diagram([
                    (T("Mode dataset", "Dataset mode"), T("Khusus engineering", "Engineering only")),
                    (T("Masukan MQTT", "MQTT input"), T("Record dataset", "Dataset record")),
                    (T("Validasi", "Validation"), T("Skema + nilai", "Schema + values")),
                    (T("Perekam", "Recorder"), T("Layanan Python", "Python service")),
                    (T("Penyimpanan", "Storage"), "MySQL / CSV"),
                ], [T("publikasi", "publish"), T("urai", "parse"), T("terima", "accept"), T("tulis", "write")],
                   T("Gambar 8. Jalur dataset engineering.", "Figure 8. Engineering dataset path.")),
                table([T("Penyimpanan", "Storage"), T("Status", "Status"), T("Batas", "Boundary")], [
                    ["MySQL", T("Didukung bila driver dan koneksi tersedia", "Supported when the driver and connection are available"), T("Hanya record dataset", "Dataset records only")],
                    ["CSV", T("Salinan paralel; tetap tersedia saat MySQL tidak tersedia", "Parallel copy; remains available when MySQL is unavailable"), T("Dataset engineering", "Engineering dataset")],
                ], [0.20, 0.42, 0.38]),
                note(T("MySQL tidak digeneralisasi sebagai penyimpanan seluruh telemetri, alarm, topologi, atau event operasional.",
                       "MySQL is not generalized as storage for all telemetry, alarms, topology, or operational events."), "caution"),
            ],
            T("Validasi perekam dataset, jalur MySQL, dan salinan CSV paralel.", "Dataset-recorder validation, MySQL path, and parallel CSV copy."),
        ),
        page(
            T("Model penerapan pada VM customer", "Customer VM deployment model"),
            T("Aplikasi ditargetkan untuk dipasang pada virtual machine yang disediakan customer.",
              "The application is targeted for installation on a customer-provided virtual machine."),
            "confirmed",
            [
                table([T("Area", "Area"), T("Spesifikasi penerapan", "Deployment specification")], [
                    [T("Host", "Host"), T("VM pada infrastruktur customer", "VM on customer infrastructure")],
                    [T("OS", "OS"), T("Linux atau Windows, dipilih untuk deployment", "Linux or Windows, selected for the deployment")],
                    [T("Keamanan", "Security"), T("Secret runtime dan kepercayaan broker wajib tersedia", "Runtime secrets and broker trust are required")],
                ], [0.28, 0.72]),
                note(T("Konfigurasi VM, jaringan, broker, dan secret ditetapkan untuk setiap deployment customer.",
                       "VM, network, broker, and secret configuration is established for each customer deployment.")),
            ],
            T("Model penerapan VM dan kebutuhan runtime Server.", "VM deployment model and Server runtime requirements."),
        ),
        page(
            T("Antarmuka web dan engineering UI", "Web and engineering UI"),
            T("Server menyediakan tampilan topologi engineering berbasis Node-RED dan mendukung aplikasi web pada infrastruktur customer.",
              "The Server provides a Node-RED-based engineering topology view and supports a web application on customer infrastructure."),
            "confirmed",
            [
                table([T("Lapisan UI", "UI layer"), T("Implementasi", "Implementation"), T("Cakupan", "Scope")], [
                    [T("Tampilan engineering Node-RED", "Node-RED engineering view"), T("Bagian dari runtime Server", "Part of the Server runtime"), T("Topologi, parent, discovery, rute, status engineering", "Topology, parent, discovery, route, engineering status")],
                    [T("Aplikasi web customer", "Customer web application"), T("Host pada infrastruktur customer", "Hosted on customer infrastructure"), T("Aplikasi antarmuka berbasis web", "Web-based interface application")],
                ], [0.29, 0.35, 0.36]),
                bullets([
                    T("Autentikasi, peran, dukungan browser, dan integrasi jaringan ditetapkan saat deployment.", "Authentication, roles, browser support, and network integration are established during deployment."),
                    T("Tampilan topologi menampilkan parent, discovery, rute, dan status engineering.", "The topology view displays parent, discovery, route, and engineering status."),
                ]),
            ],
            T("Tampilan topologi Node-RED dan model penerapan aplikasi web customer.", "Node-RED topology view and customer web-application deployment model."),
        ),
        page(
            T("Tanggung jawab penerapan dan operasi", "Deployment and operational responsibilities"),
            T("Kesiapan Server bergantung pada boundary antara aplikasi Lab IoT ITB dan infrastruktur customer.",
              "Server readiness depends on the boundary between the Lab IoT ITB application and customer infrastructure."),
            "boundary",
            [
                table([T("Area", "Area"), T("Input/ownership yang diperlukan", "Required input/ownership")], [
                    [T("VM", "VM"), T("Penyediaan, image OS, patching, backup, pemantauan sumber daya", "Provisioning, OS image, patching, backup, resource monitoring")],
                    [T("Broker", "Broker"), T("FQDN/IP, port, credential, CA, ACL, retention policy", "FQDN/IP, port, credentials, CA, ACL, retention policy")],
                    [T("Database", "Database"), T("MySQL endpoint/credential/schema ownership untuk dataset", "MySQL endpoint/credentials/schema ownership for datasets")],
                    [T("Secret", "Secrets"), T("Kunci AES runtime, token otorisasi perintah, credential MQTT", "Runtime AES key, command authorization token, MQTT credentials")],
                    [T("Operasi", "Operations"), T("Pengumpulan log, kebijakan restart, respons insiden, dan retensi log", "Log collection, restart policy, incident response, and log retention")],
                ], [0.24, 0.76]),
                note(T("Operasi VM, broker, database, secret, dan log dikelola sesuai kebijakan infrastruktur customer.",
                       "VM, broker, database, secret, and log operations are managed under customer infrastructure policy.")),
            ],
            T("Deployment prerequisites dan batas ownership aplikasi/infrastruktur.", "Deployment prerequisites and application/infrastructure ownership boundary."),
        ),
        page(
            T("Referensi dan riwayat revisi", "References and revision history"),
            T("Referensi protocol dan runtime melengkapi spesifikasi implementasi Server.",
              "Protocol and runtime references support the Server implementation specification."),
            "reference",
            [
                table([T("Referensi", "Reference"), T("Dokumen", "Document")], [
                    ["R1", "Node-RED - User Guide, nodered.org/docs/user-guide/"],
                    ["R2", "OASIS - MQTT Version 3.1.1, OASIS Standard"],
                    ["R3", "Oracle - MySQL 8.4 Reference Manual"],
                    ["R4", "NIST SP 800-38D - Recommendation for Galois/Counter Mode (GCM)"],
                ], [0.14, 0.86]),
                table([T("Rev", "Rev"), T("Perubahan", "Change")], [
                    ["4.0", T("Pembaruan struktur dan spesifikasi teknis.", "Updated technical structure and specifications.")],
                ], [0.18, 0.82]),
            ],
            T("Dokumentasi runtime/protocol dan revisi teknis saat ini.", "Runtime/protocol documentation and current technical revision."),
        ),
    ]
    return d


def system_document() -> dict[str, Any]:
    d = common_meta(
        slug="Whole-System",
        product="Whole System",
        status=T("Sistem Prototipe Engineering", "Engineering Prototype System"),
        firmware="GasleakDetector 0.8.19 | CH 0.8.0 | Gateway 0.2.0 | Protocol 0.2.0",
        subtitle=T(
            "Arsitektur end-to-end GasleakDetector - CH - CH opsional - Gateway - broker - Server.",
            "End-to-end GasleakDetector - CH - optional CH - Gateway - broker - Server architecture.",
        ),
        cover_nodes=[
            ("GasleakDetector", T("Sensor + alarm", "Sensing + alarm")),
            ("CH", T("STAR ke MESH", "STAR to MESH")),
            (T("CH opsional", "Optional CH"), T("Multi-hop", "Multi-hop")),
            ("Gateway", T("MESH ke MQTT", "MESH to MQTT")),
            ("Server", T("Data + perintah", "Data + command")),
        ],
        cover_links=[T("STAR", "STAR"), T("MESH", "MESH"), T("MESH", "MESH"), T("MQTT", "MQTT")],
        facts=[
            (T("TOPOLOGI", "TOPOLOGY"), T("Multi-hop dinamis", "Dynamic multi-hop")),
            (T("CARRIER", "CARRIER"), "920-923 MHz"),
            (T("UPLINK", "UPLINK"), T("Normal pull + alarm push", "Normal pull + alarm push")),
            (T("DOWNLINK", "DOWNLINK"), T("Perintah melalui broker", "Command via broker")),
        ],
        abbreviations=[
            ("AES-GCM", T("Authenticated encryption pada payload field", "Authenticated encryption on field payloads")),
            ("CH", T("Node komunikasi serving/transit", "Serving/transit communication node")),
            ("E2E", T("End-to-end", "End-to-end")),
            ("MESH", T("Backbone radio CH dan Gateway", "CH and Gateway radio backbone")),
            ("MQTT", T("Messaging transport melalui broker", "Broker-based messaging transport")),
            ("STAR", T("Radio link GasleakDetector ke serving CH", "GasleakDetector-to-serving-CH radio link")),
            ("TLS", T("Transport security pada dua sesi broker terpisah", "Transport security on two separate broker sessions")),
            ("VM", T("Virtual machine customer untuk Server", "Customer virtual machine for Server")),
        ],
    )
    d["chapters"] = [
        page(
            T("Ruang lingkup sistem", "System scope"),
            T("Whole System menghubungkan endpoint sensor, jaringan radio field, bridge IP, broker, dan aplikasi Server.",
              "The Whole System connects sensing endpoints, the field radio network, an IP bridge, a broker, and the Server application."),
            "implemented",
            [
                cards([
                    (T("Endpoint", "Endpoint"), "GasleakDetector"),
                    (T("Jaringan field", "Field network"), T("CH STAR/MESH", "CH STAR/MESH")),
                    (T("Bridge IP", "IP bridge"), "Gateway"),
                    (T("Aplikasi", "Application"), "Server"),
                ]),
                bullets([
                    T("Jalur operasional utama: GasleakDetector ke serving CH, transit CH opsional, Gateway, broker, lalu Server.", "Primary operational path: GasleakDetector to serving CH, optional transit CH, Gateway, broker, then Server."),
                    T("Jalur telemetri normal dan alarm menggunakan perilaku pengiriman yang berbeda.", "Normal telemetry and alarms use different delivery behavior."),
                    T("Perintah kembali melalui broker, Gateway, rute CH, dan jendela penerimaan endpoint.", "Commands return through the broker, Gateway, CH route, and endpoint receive window."),
                    T("Jalur dataset engineering dipisahkan dari jalur alarm operasional.", "The engineering dataset path is separate from the operational alarm path."),
                ]),
            ],
            T("Firmware tiga perangkat, implementasi Server, protocol contract, dan konfigurasi produk.", "Three-device firmware, Server implementation, protocol contract, and product configuration."),
        ),
        page(
            T("Arsitektur operasional dan dataset", "Operational and dataset architecture"),
            T("Jalur operasional dan jalur dataset mempunyai tujuan serta aturan pemrosesan yang berbeda.",
              "The operational path and dataset path have different purposes and processing rules."),
            "implemented",
            [
                diagram([
                    ("GasleakDetector", T("Sensor", "Sensing")),
                    (T("Serving CH", "Serving CH"), T("STAR/MESH", "STAR/MESH")),
                    (T("Transit CH", "Transit CH"), T("0..n", "0..n")),
                    ("Gateway", T("Wi-Fi/MQTT", "Wi-Fi/MQTT")),
                    (T("Broker", "Broker"), T("Batas kepercayaan", "Trust boundary")),
                    ("Server", T("Aplikasi", "Application")),
                ], [T("STAR", "STAR"), T("MESH", "MESH"), T("MESH", "MESH"), T("MQTT", "MQTT"), T("MQTT", "MQTT")],
                   T("Gambar 1. Jalur operasional utama.", "Figure 1. Primary operational path.")),
                diagram([
                    (T("Mode dataset", "Dataset mode"), T("GasleakDetector", "GasleakDetector")),
                    (T("Wi-Fi/MQTT", "Wi-Fi/MQTT"), T("Tautan engineering", "Engineering link")),
                    (T("Perekam dataset", "Dataset recorder"), T("Validasi", "Validation")),
                    (T("Penyimpanan", "Storage"), "MySQL / CSV"),
                ], [T("langsung", "direct"), T("rekam", "record"), T("tulis", "write")],
                   T("Gambar 2. Jalur dataset engineering terpisah.", "Figure 2. Separate engineering dataset path.")),
                note(T("Mode dataset bukan jalur alarm produksi dan tidak menggantikan jalur LoRa operasional.",
                       "Dataset mode is not the production alarm path and does not replace the operational LoRa path."), "caution"),
            ],
            T("Mode operasional/dataset GasleakDetector, routing CH/Gateway, dan perekam dataset Server.", "GasleakDetector operational/dataset modes, CH/Gateway routing, and the Server dataset recorder."),
        ),
        page(
            T("Matriks peran subsistem", "Subsystem responsibility matrix"),
            T("Setiap subsistem mempunyai batas fungsional yang berbeda pada sensor, transport, routing, keamanan, dan aplikasi.",
              "Each subsystem has a distinct functional boundary across sensing, transport, routing, security, and application."),
            "implemented",
            [
                table([T("Subsistem", "Subsystem"), T("Peran utama", "Primary role"), T("Tidak menjadi tanggung jawab", "Not responsible for")], [
                    ["GasleakDetector", T("Sensor 8 channel, inferensi lokal, keluaran alarm, LoRa STAR", "8-channel sensing, local inference, alarm output, LoRa STAR"), T("Routing MESH atau TLS broker", "MESH routing or broker TLS")],
                    [T("Serving CH", "Serving CH"), T("STAR ingress, cache, MESH forwarding", "STAR ingress, cache, MESH forwarding"), T("Payload decryption atau Server application", "Payload decryption or Server application")],
                    [T("Transit CH", "Transit CH"), T("MESH relay dan route continuity", "MESH relay and route continuity"), T("Endpoint sensing", "Endpoint sensing")],
                    ["Gateway", T("MESH-to-Wi-Fi/MQTT bridge", "MESH-to-Wi-Fi/MQTT bridge"), T("Persistent storage atau guaranteed delivery", "Persistent storage or guaranteed delivery")],
                    [T("Broker", "Broker"), T("MQTT session/transport boundary", "MQTT session/transport boundary"), T("Field sensing/inference", "Field sensing/inference")],
                    ["Server", T("Validasi, dekode, routing alarm, topologi, perintah", "Validation, decode, alarm routing, topology, command"), T("Keluaran alarm fisik", "Physical alarm output")],
                ], [0.20, 0.43, 0.37]),
                note(T("Broker adalah dependensi logis deployment dan harus dimasukkan pada desain jaringan walaupun bukan perangkat field.",
                       "The broker is a logical deployment dependency and must be included in the network design even though it is not a field device.")),
            ],
            T("Fungsi firmware/application masing-masing subsistem dan trust boundaries.", "Firmware/application functions and trust boundaries of each subsystem."),
        ),
        page(
            T("Ringkasan antarmuka antar-subsistem", "Inter-subsystem interface summary"),
            T("Tabel berikut merangkum transport, arah komunikasi, dan fungsi publik pada setiap batas subsistem.",
              "The following table summarizes transport, communication direction, and public function at each subsystem boundary."),
            "implemented",
            [
                table([T("Link", "Link"), T("Transport", "Transport"), T("Arah", "Direction"), T("Fungsi", "Function")], [
                    ["GasleakDetector - CH", "LoRa STAR", T("Uplink + receive window", "Uplink + receive window"), T("Telemetry, alarm, dan limited downlink", "Telemetry, alarm, and limited downlink")],
                    ["CH - CH/Gateway", "LoRa MESH", T("Dua arah", "Bidirectional"), T("Multi-hop routing dan relay", "Multi-hop routing and relay")],
                    ["Gateway - network", "Wi-Fi STA", T("Dua arah", "Bidirectional"), T("IP connectivity", "IP connectivity")],
                    ["Gateway - broker", "MQTT / TLS option", T("Dua arah", "Bidirectional"), T("Publish uplink; subscribe command", "Publish uplink; subscribe command")],
                    ["Server - broker", "MQTT / TLS", T("Dua arah", "Bidirectional"), T("Ingestion dan command", "Ingestion and command")],
                    ["GasleakDetector - local", "RS-485 Modbus", T("Read-only", "Read-only"), T("Local data/status integration", "Local data/status integration")],
                ], [0.24, 0.23, 0.18, 0.35]),
                note(T("Konverter Wi-Fi-to-Ethernet eksternal bukan interface native Gateway dan tidak termasuk pada matrix produk.",
                       "An external Wi-Fi-to-Ethernet converter is not a native Gateway interface and is not included in the product matrix."), "caution"),
            ],
            T("Kontrak antarmuka eksternal GasleakDetector, CH, Gateway, dan Server.", "External interface contracts across GasleakDetector, CH, Gateway, and Server."),
        ),
        page(
            T("Urutan telemetri normal", "Normal telemetry sequence"),
            T("Telemetri normal menggunakan cache pada serving CH dan dikirim sebagai respons permintaan server.",
              "Normal telemetry uses a cache at the serving CH and is sent in response to a server pull."),
            "implemented",
            [
                sequence(["GasleakDetector", T("Serving CH", "Serving CH"), T("Transit/Gateway", "Transit/Gateway"), T("Broker", "Broker"), "Server"], [
                    (0, 1, T("Telemetri LoRa STAR", "LoRa STAR telemetry")),
                    (1, 1, T("Perbarui cache node", "Update node cache")),
                    (4, 3, T("Permintaan pull Server", "Server pull request")),
                    (3, 2, T("Gateway downlink", "Gateway downlink")),
                    (2, 1, T("Pull mencapai serving CH", "Pull reaches serving CH")),
                    (1, 2, T("Respons cluster", "Cluster response")),
                    (2, 3, T("Publikasi Gateway", "Gateway publish")),
                    (3, 4, T("Ingestion Server", "Server ingestion")),
                ], T("Gambar 3. Telemetry normal berbasis cache dan pull.", "Figure 3. Cache/pull normal telemetry.")),
                note(T("Pengiriman telemetri normal bersifat pull-based dan mengikuti data yang tersedia pada cache serving CH.",
                       "Normal telemetry delivery is pull-based and follows the data available in the serving-CH cache.")),
            ],
            T("CH node cache/cluster response, server pull, Gateway publish, dan Server ingestion.", "CH node cache/cluster response, server pull, Gateway publish, and Server ingestion."),
        ),
        page(
            T("Urutan alarm dan kembali-normal", "Alarm and return-to-clear sequence"),
            T("Alarm/clear memakai jalur push dan baru menjadi alarm Server setelah payload lolos gerbang integritas.",
              "Alarm/clear uses a push path and becomes a Server alarm only after the payload passes the integrity gate."),
            "implemented",
            [
                sequence(["GasleakDetector", T("Serving CH", "Serving CH"), T("MESH route", "MESH route"), "Gateway", "Server"], [
                    (0, 1, T("STAR alarm/clear", "STAR alarm/clear")),
                    (1, 2, T("Masuk jalur push alarm", "Enter alarm push path")),
                    (2, 3, T("Relay ke root", "Relay to root")),
                    (3, 4, T("Publikasi MQTT", "MQTT publish")),
                    (4, 4, T("Validasi + autentikasi", "Validate + authenticate")),
                    (4, 4, T("Routing alarm", "Alarm routing")),
                ], T("Gambar 4. Alarm push dan integrity gate Server.", "Figure 4. Alarm push and Server integrity gate.")),
                kv([
                    (T("Alarm lokal", "Local alarm"), T("Keluaran steady 24 V pada mode AUTO GasleakDetector.", "Steady 24 V output in GasleakDetector AUTO mode.")),
                    (T("Alarm jaringan", "Network alarm"), T("Event terautentikasi yang dirutekan Server.", "Authenticated event routed by the Server.")),
                ]),
            ],
            T("Frame alarm GasleakDetector, CH push/ACK, publikasi Gateway, serta routing integritas/alarm Server.", "GasleakDetector alarm frames, CH push/ACK, Gateway publication, and Server integrity/alarm routing."),
        ),
        page(
            T("Urutan perintah downlink", "Command downlink sequence"),
            T("Perintah mode tingkat tinggi bergerak dari Server melalui broker dan rute field menuju jendela penerimaan GasleakDetector.",
              "A high-level mode command moves from the Server through the broker and field route to the GasleakDetector receive window."),
            "implemented",
            [
                sequence(["Server", T("Broker", "Broker"), "Gateway", T("Transit/Serving CH", "Transit/Serving CH"), "GasleakDetector"], [
                    (0, 0, T("Otorisasi + autentikasi", "Authorize + authenticate")),
                    (0, 1, T("Publikasi MQTT", "MQTT publish")),
                    (1, 2, T("Pengiriman MQTT", "MQTT deliver")),
                    (2, 3, T("Rute MESH", "MESH route")),
                    (3, 4, T("Kirim dalam jendela penerimaan", "Deliver in receive window")),
                    (4, 4, T("Validasi dan terapkan", "Validate and apply")),
                ], T("Gambar 5. Downlink command menuju endpoint.", "Figure 5. Command downlink to the endpoint.")),
                note(T("Pengiriman perintah ke endpoint baterai dilakukan pada jendela penerimaan setelah transmisi endpoint.",
                       "Command delivery to battery endpoints occurs during the endpoint post-transmission receive window.")),
            ],
            T("Pembentuk perintah Server, jalur broker/Gateway, rute CH, dan penanganan receive window GasleakDetector.", "Server command builder, broker/Gateway path, CH route, and GasleakDetector receive-window handling."),
        ),
        page(
            T("Discovery dan pembentukan rute", "Discovery and route formation"),
            T("CH membentuk rute secara dinamis berdasarkan kandidat yang mempunyai lineage menuju Gateway root.",
              "CH forms routes dynamically from candidates with lineage toward the Gateway root."),
            "implemented",
            [
                diagram([
                    (T("CH tanpa parent", "CH without parent"), T("Mulai discovery", "Discovery start")),
                    (T("Kandidat", "Candidates"), T("CH / Gateway", "CH / Gateway")),
                    (T("Guard", "Guard"), T("Pemeriksaan root + loop", "Root + loop check")),
                    (T("Penilaian", "Scoring"), T("Health + rute", "Health + route")),
                    (T("Pasang", "Install"), T("Parent + alternatif", "Parent + alternate")),
                ], [T("probe", "probe"), T("filter", "filter"), T("peringkat", "rank"), T("commit", "commit")],
                   T("Gambar 6. Discovery sampai pemasangan parent.", "Figure 6. Discovery through parent installation.")),
                bullets([
                    T("Gateway adalah root destination, bukan parent statis semua CH.", "Gateway is the root destination, not every CH's static parent."),
                    T("Lineage guard mencegah routing loop.", "The lineage guard prevents routing loops."),
                    T("Parent aktual tidak dipatok pada identity tertentu.", "The actual parent is not fixed to a specific identity."),
                ]),
            ],
            T("CH discovery, root reachability, lineage guard, scoring, dan installed parent source.", "CH discovery, root reachability, lineage guard, scoring, and installed-parent source."),
        ),
        page(
            T("Multi-hop dan failover", "Multi-hop and failover"),
            T("Parent alternatif dan rediscovery menjaga kontinuitas ketika parent aktif tidak lagi sehat.",
              "An alternate parent and rediscovery maintain continuity when the active parent is no longer healthy."),
            "tested",
            [
                layers([
                    (T("Rute sehat", "Healthy route"), T("Serving CH -> transit -> Gateway", "Serving CH -> transit(s) -> Gateway")),
                    (T("Kegagalan health", "Health failure"), T("Timeout/HELLO ACK/alarm ACK gagal", "Timeout/HELLO ACK/alarm ACK failure")),
                    (T("Parent alternatif", "Alternate parent"), T("Dipakai bila valid", "Used when valid")),
                    (T("Rediscovery", "Rediscovery"), T("Membangun kandidat baru", "Builds new candidates")),
                    (T("Rute pulih", "Recovered route"), T("Parent baru mengikuti discovery", "New parent follows discovery")),
                ], T("Gambar 7. Failover route CH.", "Figure 7. CH route failover.")),
                note(T("Multi-hop dan failover telah divalidasi di Lab IoT ITB. Parent pengganti mengikuti hasil discovery dan tidak ditetapkan ke identity tertentu.",
                       "Multi-hop and failover have been validated at the ITB IoT Lab. The replacement parent follows discovery and is not fixed to a specific identity."), "success"),
            ],
            T("Implementasi multi-hop/failover dan validasi laboratorium internal.", "Multi-hop/failover implementation and internal laboratory validation."),
        ),
        page(
            T("Rencana RF dua domain", "Two-domain RF plan"),
            T("STAR dan MESH berbagi rentang carrier yang diterima 920-923 MHz, tetapi memakai nilai default dan antena berbeda.",
              "STAR and MESH share the 920-923 MHz accepted carrier range but use different defaults and antennas."),
            "implemented",
            [
                table([T("Domain", "Domain"), T("Default", "Default"), T("BW / SF / CR", "BW / SF / CR"), T("TX setting", "TX setting"), T("Antena", "Antenna")], [
                    ["STAR", "920.0 MHz", "125 kHz / SF7 / 4/5", "17 dBm", "3 dBi"],
                    ["MESH", "921.0 MHz", "125 kHz / SF9 / 4/5", "17 dBm", "8 dBi"],
                ], [0.16, 0.20, 0.29, 0.17, 0.18]),
                kv([
                    (T("Carrier yang diterima", "Accepted carrier"), T("920-923 MHz inklusif", "920-923 MHz inclusive")),
                    (T("Konfigurasi aktif", "Active configuration"), T("Diverifikasi melalui pembacaan kembali perangkat.", "Verified through device readback.")),
                ]),
                note(T("Perhitungan nominal sebelum loss: STAR 20 dBm dan MESH 25 dBm.",
                       "Nominal calculation before loss: STAR 20 dBm and MESH 25 dBm.")),
            ],
            T("LoRa STAR/MESH configs, runtime validation, NVS readback, dan konfigurasi antena produk.", "LoRa STAR/MESH configs, runtime validation, NVS readback, and product antenna configuration."),
        ),
        page(
            T("Jaringan IP, broker, dan profil TLS", "IP network, broker, and TLS profile"),
            T("Ketika profil Gateway TLS dipilih, Gateway dan Server masing-masing membentuk sesi TLS sendiri ke broker; broker menjadi batas terminasi/kepercayaan.",
              "When the TLS Gateway profile is selected, the Gateway and Server each establish their own TLS session to the broker; the broker is the termination/trust boundary."),
            "implemented",
            [
                diagram([
                    ("Gateway", T("Klien TLS A", "TLS client A")),
                    (T("Sesi TLS A", "TLS session A"), T("CA terverifikasi", "CA verified")),
                    (T("Broker MQTT", "MQTT broker"), T("Terminasi keduanya", "Terminates both")),
                    (T("Sesi TLS B", "TLS session B"), T("CA terverifikasi", "CA verified")),
                    ("Server", T("Klien TLS B", "TLS client B")),
                ], [T("enkripsi", "encrypt"), T("terminasi", "terminate"), T("sesi baru", "new session"), T("dekripsi", "decrypt")],
                   T("Gambar 8. Dua sesi TLS pada profil deployment TLS.", "Figure 8. Two TLS sessions in the TLS deployment profile.")),
                bullets([
                    T("Profil Gateway TLS membutuhkan Root CA dan waktu sistem yang memenuhi ambang tepercaya.", "The TLS Gateway profile requires a Root CA and a system epoch that meets the trusted-time threshold."),
                    T("Flow Server mendukung credential dan TLS terverifikasi CA ke broker.", "The Server flow supports credentials and CA-verified TLS to the broker."),
                    T("Pada profil TLS, Gateway dan Server menggunakan dua sesi TLS terpisah yang masing-masing berakhir pada broker.", "In the TLS profile, the Gateway and Server use two separate TLS sessions, each terminating at the broker."),
                ]),
            ],
            T("Gateway TLS implementation, Server MQTT TLS generation, dan broker trust boundary.", "Gateway TLS implementation, Server MQTT TLS generation, and broker trust boundary."),
        ),
        page(
            T("Batas keamanan berlapis", "Layered security boundaries"),
            T("Keamanan payload dan keamanan transport melindungi lapisan serta segmen yang berbeda.",
              "Payload security and transport security protect different layers and segments."),
            "implemented",
            [
                table([T("Lapisan", "Layer"), T("Cakupan", "Coverage"), T("Fungsi", "Function"), T("Terminasi", "Termination")], [
                    ["AES-128-GCM", T("Payload GasleakDetector", "GasleakDetector payload"), T("Kerahasiaan + autentikasi", "Confidentiality + authentication"), T("Decoder Server", "Server decoder")],
                    [T("Gateway TLS", "Gateway TLS"), T("Gateway - broker", "Gateway - broker"), T("Perlindungan transport MQTT", "MQTT transport protection"), T("Broker", "Broker")],
                    [T("Server TLS", "Server TLS"), T("Server - broker", "Server - broker"), T("Perlindungan transport MQTT", "MQTT transport protection"), T("Broker", "Broker")],
                    [T("Autentikasi perintah", "Command auth"), T("Downlink tingkat tinggi", "High-level downlink"), T("Otorisasi + autentikasi payload", "Authorization + payload authentication"), T("Aplikasi target", "Target application")],
                ], [0.22, 0.28, 0.30, 0.20]),
                note(T("CH dan Gateway meneruskan payload field terenkripsi; payload didekripsi dan diautentikasi di Server.",
                       "CH and Gateway forward the encrypted field payload; it is decrypted/authenticated at the Server."), "success"),
            ],
            T("Kriptografi frame GasleakDetector, forwarding CH, transport Gateway, dekode Server, dan autentikasi perintah.", "GasleakDetector frame cryptography, CH forwarding, Gateway transport, Server decoding, and command authentication."),
        ),
        page(
            T("Ketersediaan, cache, dan buffering", "Availability, cache, and buffering"),
            T("Data sementara berada pada cache CH atau antrean RAM Gateway; retensi field mengikuti kapasitas dan sifat memori masing-masing.",
              "Temporary data resides in the CH cache or Gateway RAM queue; field retention follows each mechanism's capacity and memory type."),
            "implemented",
            [
                table([T("Lokasi", "Location"), T("Mekanisme", "Mechanism"), T("Persistensi", "Persistence"), T("Batas", "Boundary")], [
                    ["CH", T("Cache node untuk telemetri normal", "Node cache for normal telemetry"), T("Memori/keadaan runtime", "Runtime memory/state"), T("Dikirim saat permintaan server", "Sent on server pull")],
                    ["Gateway", T("Antrean MQTT 8 item, payload 1-1023 B", "8-item MQTT queue, 1-1023 B payload"), T("RAM volatil", "Volatile RAM"), T("Item baru ditolak saat penuh", "New item rejected when full")],
                    ["Server", T("Status anti-replay", "Anti-replay state"), T("Penyimpanan persisten wajib pada deployment", "Persistent storage required in deployment"), T("Dimuat kembali setelah layanan restart", "Reloaded after service restart")],
                    [T("Dataset", "Dataset"), "MySQL / CSV", T("Persistensi engineering", "Engineering persistence"), T("Hanya record dataset", "Dataset records only")],
                ], [0.18, 0.39, 0.21, 0.22]),
            ],
            T("CH cache, Gateway queue, Server replay state, dan dataset storage source.", "CH cache, Gateway queue, Server replay state, and dataset storage source."),
        ),
        page(
            T("Domain daya subsistem", "Subsystem power domains"),
            T("Setiap perangkat mempunyai batas daya berbeda; kemampuan salah satu PCB tidak digeneralisasi ke subsistem lain.",
              "Each device has a different power boundary; one PCB's capability is not generalized to another subsystem."),
            "confirmed",
            [
                table([T("Subsistem", "Subsystem"), T("Konfigurasi", "Configuration"), T("Perilaku monitoring", "Monitoring behavior")], [
                    ["GasleakDetector", T("24 VDC nominal; 7 x 18650 paralel untuk mode baterai", "24 VDC nominal; 7 x parallel 18650 for battery mode"), T("Monitoring tegangan diagnostik", "Diagnostic voltage monitoring")],
                    ["CH", T("1-3 x 18650 paralel; 2 x panel 6 W paralel", "1-3 x parallel 18650; 2 x parallel 6 W panels"), T("VBAT read-only", "VBAT read-only")],
                ], [0.22, 0.50, 0.28]),
                note(T("Firmware CH melaporkan VBAT secara read-only tanpa pemutusan aktif saat tegangan rendah. GasleakDetector juga memantau tegangan tanpa active undervoltage cutoff.",
                       "CH firmware reports VBAT read-only without active low-voltage cutoff. GasleakDetector also monitors voltage without active undervoltage cutoff."), "caution"),
            ],
            T("Konfigurasi daya produk, desain hardware, dan perilaku power-state firmware.", "Product power configurations, hardware designs, and firmware power-state behavior."),
        ),
        page(
            T("Varian perangkat keras dan kompatibilitas firmware", "Hardware variants and firmware compatibility"),
            T("CH dan Gateway mempunyai board Rectangle/Circle; Gateway juga mempunyai pilihan TLS/non-TLS.",
              "CH and Gateway have Rectangle/Circle boards; Gateway also has TLS/non-TLS choices."),
            "implemented",
            [
                table([T("Perangkat", "Device"), T("Board", "Board"), T("Opsi transport", "Transport option"), T("Target firmware", "Firmware target")], [
                    ["GasleakDetector", T("Board produk", "Product board"), T("LoRa STAR + RS-485", "LoRa STAR + RS-485"), T("Firmware GasleakDetector", "GasleakDetector firmware")],
                    ["CH", T("Rectangle", "Rectangle"), T("STAR + MESH", "STAR + MESH"), T("CH Rectangle", "CH Rectangle")],
                    ["CH", T("Circle", "Circle"), T("STAR + MESH", "STAR + MESH"), T("CH Circle", "CH Circle")],
                    ["Gateway", T("Rectangle", "Rectangle"), T("MQTT non-TLS / TLS", "MQTT non-TLS / TLS"), T("Gateway Rectangle - standard / TLS", "Gateway Rectangle - standard / TLS")],
                    ["Gateway", T("Circle", "Circle"), T("MQTT non-TLS / TLS", "MQTT non-TLS / TLS"), T("Gateway Circle - standard / TLS", "Gateway Circle - standard / TLS")],
                    ["Server", T("VM customer", "Customer VM"), T("Klien/aplikasi MQTT", "MQTT client/application"), T("Spesifik deployment", "Deployment-specific")],
                ], [0.20, 0.20, 0.32, 0.28]),
                note(T("Setelah upload, readback perangkat memverifikasi varian board dan transport yang aktif.",
                       "After upload, device readback verifies the active board and transport variant."), "success"),
            ],
            T("Target firmware dan verifikasi varian perangkat melalui Operator Hub.", "Firmware targets and device-variant verification through Operator Hub."),
        ),
        page(
            T("Topologi penerapan", "Deployment topology"),
            T("Deployment membutuhkan perangkat field, Wi-Fi, broker, VM Server, database dataset opsional, dan kepemilikan operasi.",
              "Deployment requires field devices, Wi-Fi, a broker, a Server VM, optional dataset database, and operational ownership."),
            "boundary",
            [
                layers([
                    (T("Lapisan field", "Field layer"), T("GasleakDetector, serving/transit CH, Gateway", "GasleakDetector, serving/transit CH, Gateway")),
                    (T("Jaringan site", "Site network"), T("Wi-Fi, DNS, NTP, VLAN/NAC, firewall", "Wi-Fi, DNS, NTP, VLAN/NAC, firewall")),
                    (T("Pesan", "Messaging"), T("Broker MQTT, rantai CA, ACL, credential", "MQTT broker, CA chain, ACL, credentials")),
                    (T("Aplikasi", "Application"), T("Server Node-RED pada VM customer", "Node-RED Server on customer VM")),
                    (T("Data engineering", "Engineering data"), T("Perekam dataset dan MySQL/CSV bila digunakan", "Dataset recorder and MySQL/CSV when used")),
                ], T("Gambar 9. Lapisan deployment sistem.", "Figure 9. System deployment layers.")),
                note(T("OS image, VM sizing, broker, database, backup, HA, RBAC, dan SSO ditetapkan sesuai deployment customer.",
                       "OS image, VM sizing, broker, database, backup, HA, RBAC, and SSO are specified for each customer deployment.")),
            ],
            T("Model VM Server dan dependensi jaringan deployment.", "Server VM model and deployment network dependencies."),
        ),
        page(
            T("Urutan komisioning", "Commissioning sequence"),
            T("Komisioning harus memverifikasi firmware, identitas, radio, jaringan, keamanan, dan jalur aplikasi secara berurutan.",
              "Commissioning must sequentially verify firmware, identity, radio, network, security, and the application path."),
            "implemented",
            [
                layers([
                    (T("1. Firmware", "1. Firmware"), T("Pilih target perangkat/board/transport yang tepat", "Select exact device/board/transport target")),
                    (T("2. Pembacaan perangkat", "2. Device readback"), T("Versi, identitas, varian board, konfigurasi RF", "Version, identity, board variant, RF configuration")),
                    (T("3. Tautan field", "3. Field link"), T("STAR, MESH, discovery, parent, rute", "STAR, MESH, discovery, parent, route")),
                    (T("4. IP/TLS", "4. IP/TLS"), T("Wi-Fi, DNS/NTP, CA, koneksi broker", "Wi-Fi, DNS/NTP, CA, broker connection")),
                    (T("5. Aplikasi", "5. Application"), T("Dekode, rute alarm, topologi, perintah", "Decode, alarm route, topology, command")),
                    (T("6. Hasil", "6. Record"), T("Log, ID unit, versi, dan kriteria lulus", "Logs, unit IDs, versions, and pass criteria")),
                ], T("Gambar 10. Urutan komisioning engineering.", "Figure 10. Engineering commissioning sequence.")),
                note(T("Setiap tahap komisioning diselesaikan berurutan dan dicatat pada hasil penerimaan deployment.", "Each commissioning stage is completed in sequence and recorded in the deployment acceptance result."), "success"),
            ],
            T("Operator Hub controls, device readback, network/TLS prerequisites, dan Server validation path.", "Operator Hub controls, device readback, network/TLS prerequisites, and Server validation path."),
        ),
        page(
            T("Referensi dan riwayat revisi", "References and revision history"),
            T("Dokumen komponen dan protocol digunakan sebagai referensi spesifikasi sistem.",
              "Component and protocol documents are used as system-specification references."),
            "reference",
            [
                table([T("Referensi", "Reference"), T("Dokumen", "Document")], [
                    ["R1", "GasleakDetector Technical Datasheet, Rev 4.0"],
                    ["R2", "CH Technical Datasheet, Rev 4.0"],
                    ["R3", "Gateway Technical Datasheet, Rev 4.0"],
                    ["R4", "Server Technical Datasheet, Rev 4.0"],
                    ["R5", "Firmware/Protocol baseline: 0.8.19 / 0.8.0 / 0.2.0 / protocol 0.2.0"],
                ], [0.14, 0.86]),
                table([T("Rev", "Rev"), T("Perubahan", "Change")], [
                    ["4.0", T("Pembaruan struktur dan spesifikasi teknis.", "Updated technical structure and specifications.")],
                ], [0.18, 0.82]),
            ],
            T("Datasheet subsistem, baseline protocol, dan revisi teknis saat ini.", "Subsystem datasheets, protocol baseline, and current technical revision."),
        ),
    ]
    return d


def all_documents(lang: str) -> list[dict[str, Any]]:
    docs = [gas_document(), ch_document(), gateway_document(), server_document(), system_document()]
    return [resolve(doc, lang) for doc in docs]


# The remaining product definitions are kept below so all five documents share
# one evidence taxonomy and one bilingual source of truth.
