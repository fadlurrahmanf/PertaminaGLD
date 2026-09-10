from __future__ import annotations

from copy import deepcopy
from typing import Any


Bilingual = tuple[str, str]


def _b(indonesian: str, english: str) -> Bilingual:
    return (indonesian, english)


def _table(
    headers: list[Bilingual],
    rows: list[list[Any]],
    widths: list[float] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "table", "headers": headers, "rows": rows}
    if widths is not None:
        block["widths"] = widths
    return block


def _bullets(items: list[Bilingual]) -> dict[str, Any]:
    return {"type": "bullets", "items": items}


def _note(text: Bilingual, tone: str = "info") -> dict[str, Any]:
    return {"type": "note", "text": text, "tone": tone}


def _section(
    title: Bilingual,
    lead: Bilingual,
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"title": title, "lead": lead, "blocks": blocks}


def _resolve(value: Any, language_index: int) -> Any:
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(item, str) for item in value):
        return value[language_index]
    if isinstance(value, dict):
        return {key: _resolve(item, language_index) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, language_index) for item in value]
    return value


def _gld_sections() -> list[dict[str, Any]]:
    return [
        _section(
            _b("Waktu operasional", "Operational timing"),
            _b(
                "Firmware menjalankan akuisisi, pelaporan radio, dan jendela penerimaan dengan interval tetap berikut.",
                "The firmware runs acquisition, radio reporting, and the receive window at the following fixed intervals.",
            ),
            [
                _table(
                    [_b("Fungsi", "Function"), _b("Nilai", "Value"), _b("Keterangan", "Description")],
                    [
                        [
                            _b("Siklus pemindaian sensor", "Sensor scan cycle"),
                            "500 ms",
                            _b("Interval pemrosesan pengukuran delapan channel.", "Processing interval for the eight-channel measurement."),
                        ],
                        [
                            _b("Pelaporan radio periodik", "Periodic radio report"),
                            "10 s",
                            _b("Interval nominal pengiriman data operasional melalui LoRa STAR.", "Nominal interval for operational data transmission over LoRa STAR."),
                        ],
                        [
                            _b("Jendela penerimaan setelah transmisi", "Post-transmission receive window"),
                            "2 s",
                            _b("Waktu perangkat mempertahankan jalur penerimaan setelah pengiriman.", "Time during which the device keeps the receive path available after transmission."),
                        ],
                        [
                            _b("Pemanasan sensor pada sesi baterai", "Sensor warm-up in battery session"),
                            "30 s",
                            _b("Delapan channel sensor dipanaskan sebelum siklus inferensi pada sesi baterai.", "The eight sensor channels warm up before the battery-session inference cycle."),
                        ],
                    ],
                    [0.31, 0.14, 0.55],
                )
            ],
        ),
        _section(
            _b("Antarmuka Modbus RTU", "Modbus RTU interface"),
            _b(
                "RS-485 menyediakan delapan register 16-bit hanya-baca untuk integrasi dengan pengendali atau sistem akuisisi eksternal.",
                "RS-485 provides eight read-only 16-bit registers for integration with an external controller or acquisition system.",
            ),
            [
                _table(
                    [_b("Parameter", "Parameter"), _b("Spesifikasi", "Specification")],
                    [
                        [_b("Mode", "Mode"), "Modbus RTU / RS-485"],
                        [_b("Alamat unit", "Unit address"), "1"],
                        [_b("Format serial", "Serial format"), "9600 bit/s, 8 data bits, no parity, 1 stop bit (8N1)"],
                        [_b("Fungsi baca", "Read functions"), "03 (Holding Registers), 04 (Input Registers)"],
                        [_b("Akses", "Access"), _b("Hanya-baca", "Read-only")],
                    ],
                    [0.34, 0.66],
                ),
                _table(
                    [_b("Alamat protokol", "Protocol address"), _b("Register", "Register"), _b("Nilai yang dibaca", "Read value")],
                    [
                        ["0 (0x0000)", _b("Status perangkat", "Device status"), _b("Word status 16-bit; definisi bit tersedia di bawah.", "16-bit status word; bit definitions are provided below.")],
                        ["1 (0x0001)", _b("Hasil klasifikasi", "Classification result"), _b("Kode hasil klasifikasi produk dalam uint16.", "Product classification-result code in uint16.")],
                        ["2 (0x0002)", "Confidence", _b("0-100; satuan persen.", "0-100; percent unit.")],
                        ["3 (0x0003)", _b("Tegangan baterai", "Battery voltage"), _b("mV; 0xFFFF berarti nilai tidak tersedia/tidak valid.", "mV; 0xFFFF means unavailable/invalid.")],
                        ["4 (0x0004)", _b("Sumber ST_P", "ST_P source"), _b("1 = 24 V; 0 = baterai.", "1 = 24 V; 0 = battery.")],
                        ["5 (0x0005)", _b("Daya eksternal", "External power"), _b("1 = terdeteksi; 0 = tidak terdeteksi.", "1 = asserted; 0 = not asserted.")],
                        ["6 (0x0006)", _b("Pencacah transmisi LoRa", "LoRa transmission counter"), _b("16 bit bawah dari pencacah transmisi.", "Low 16 bits of the transmission counter.")],
                        ["7 (0x0007)", _b("ID node", "Node ID"), _b("Identitas node dalam uint16.", "Node identity in uint16.")],
                    ],
                    [0.19, 0.28, 0.53],
                ),
                _note(
                    _b(
                        "Alamat di tabel adalah address yang dikirim pada field start-address Modbus, mulai dari 0. Perangkat lunak master yang menampilkan nomor register 1-based harus dipetakan ke address protokol ini; gunakan FC03 atau FC04 dan jangan menulis register.",
                        "The table addresses are the values sent in the Modbus start-address field, beginning at 0. Master software that displays one-based register numbers must be mapped to these protocol addresses; use FC03 or FC04 and do not write registers.",
                    )
                ),
            ],
        ),
        _section(
            _b("Logika keluaran alarm", "Alarm-output logic"),
            _b(
                "Keluaran alarm 24 V memiliki mode AUTO untuk operasi normal dan mode MANUAL untuk pengujian terkontrol.",
                "The 24 V alarm output provides AUTO mode for normal operation and MANUAL mode for controlled testing.",
            ),
            [
                _table(
                    [_b("Mode", "Mode"), _b("Kondisi pengendali", "Control condition"), _b("Keluaran alarm 24 V", "24 V alarm output")],
                    [
                        ["AUTO", _b("Inferensi menetapkan alarm", "Inference asserts alarm"), _b("Aktif", "Active")],
                        ["AUTO", _b("Inferensi tidak menetapkan alarm; penyimpanan status clear berhasil", "Inference does not assert alarm; clear-state persistence succeeds"), _b("Tidak aktif", "Inactive")],
                        ["AUTO fail-safe", _b("Penyimpanan status clear gagal", "Clear-state persistence fails"), _b("Tetap aktif hingga clear valid dapat disimpan", "Remains active until a valid clear can be persisted")],
                        ["MANUAL", _b("Perintah uji ON", "Test command ON"), _b("Aktif", "Active")],
                        ["MANUAL", _b("Perintah uji OFF", "Test command OFF"), _b("Tidak aktif", "Inactive")],
                    ],
                    [0.16, 0.52, 0.32],
                ),
                _note(
                    _b(
                        "Mode MANUAL tidak disimpan sebagai mode operasi permanen. Setelah perangkat dimulai ulang, mode awal adalah AUTO. Kegagalan menyimpan status clear mempertahankan alarm ON secara fail-safe. Ketika keluaran 24 V aktif, pola bunyi dan kedip satu detik ON/satu detik OFF dibentuk oleh perangkat alarm yang diberi catu.",
                        "MANUAL mode is not stored as a permanent operating mode. After a device restart, the initial mode is AUTO. Failure to persist the clear state retains the alarm ON as a fail-safe. When the 24 V output is active, the one-second ON/one-second OFF audible and visual pattern is generated by the powered alarm device.",
                    )
                ),
            ],
        ),
        _section(
            _b("Word status Modbus", "Modbus status word"),
            _b(
                "Register 0 memadatkan kesiapan subsistem, validitas inferensi, alarm, dan sumber daya ke dalam satu word status 16-bit.",
                "Register 0 condenses subsystem readiness, inference validity, alarm state, and power source into one 16-bit status word.",
            ),
            [
                _table(
                    [_b("Bit register 0", "Register 0 bit"), _b("Makna bila bernilai 1", "Meaning when set")],
                    [
                        ["0", "ADS1256 ready"],
                        ["1", "DAC ready"],
                        ["2", "LoRa ready"],
                        ["3", "ML runtime ready"],
                        ["4", _b("Hasil inferensi valid", "Inference result valid")],
                        ["5", _b("Alarm aktif", "Alarm active")],
                        ["6", _b("Sumber ST_P = 24 V", "ST_P source = 24 V")],
                        ["7", _b("Daya eksternal terdeteksi", "External power detected")],
                    ],
                    [0.28, 0.72],
                ),
                _table(
                    [_b("Perilaku protocol", "Protocol behavior"), _b("Ketentuan", "Condition")],
                    [
                        [_b("Format nilai", "Value format"), _b("Seluruh register bernilai unsigned 16-bit; byte paling signifikan dikirim lebih dahulu.", "All register values are unsigned 16-bit; the most significant byte is sent first.")],
                        [_b("Jumlah pembacaan", "Read quantity"), _b("1-8 register berurutan dari address awal yang valid.", "1-8 consecutive registers from a valid start address.")],
                        [_b("Fungsi tulis", "Write functions"), _b("Tidak didukung; respons exception Modbus 01 (illegal function).", "Not supported; Modbus exception response 01 (illegal function).")],
                        [_b("Address tidak valid", "Invalid address"), _b("Respons exception Modbus 02 (illegal data address).", "Modbus exception response 02 (illegal data address).")],
                        [_b("Jumlah tidak valid", "Invalid quantity"), _b("Respons exception Modbus 03 (illegal data value).", "Modbus exception response 03 (illegal data value).")],
                    ],
                    [0.30, 0.70],
                ),
            ],
        ),
        _section(
            _b("Panduan pembacaan Modbus", "Modbus reading guide"),
            _b(
                "Gunakan langkah berikut untuk menghubungkan PLC, HMI, SCADA, atau aplikasi master ke GasleakDetector tanpa menulis konfigurasi perangkat.",
                "Use the following steps to connect a PLC, HMI, SCADA, or master application to GasleakDetector without writing device configuration.",
            ),
            [
                _table(
                    [_b("Langkah", "Step"), _b("Instruksi", "Instruction")],
                    [
                        ["1", _b("Atur port RS-485 master ke 9600 bit/s, 8N1, tanpa parity; gunakan Unit ID 1.", "Set the master RS-485 port to 9600 bit/s, 8N1, no parity; use Unit ID 1.")],
                        ["2", _b("Pilih FC03 atau FC04, lalu kirim start-address 0-7 dan quantity 1-8 yang seluruhnya berada pada rentang tersebut.", "Select FC03 or FC04, then send a start address 0-7 and quantity 1-8 that stays entirely within that range.")],
                        ["3", _b("Baca setiap word sebagai unsigned 16-bit big-endian. Untuk register 3, satuannya mV; untuk register 2, satuannya persen.", "Read each word as unsigned 16-bit big-endian. Register 3 is in mV; register 2 is in percent.")],
                        ["4", _b("Periksa CRC RTU dan respons exception sebelum memakai nilai pada aplikasi pengendali.", "Check the RTU CRC and any exception response before using values in the supervisory application.")],
                    ],
                    [0.11, 0.89],
                ),
                _table(
                    [_b("Contoh", "Example"), _b("Frame RTU lengkap", "Complete RTU frame"), _b("Keterangan", "Description")],
                    [
                        [
                            _b("Baca confidence", "Read confidence"),
                            "01 04 00 02 00 01 90 0A",
                            _b("Request FC04 untuk satu word pada address 2.", "FC04 request for one word at address 2."),
                        ],
                        [
                            _b("Respons confidence", "Confidence response"),
                            "01 04 02 00 52 38 CD",
                            _b("Contoh ilustratif: 0x0052 = 82%, bukan hasil pembacaan unit tertentu.", "Illustrative example: 0x0052 = 82%, not a reading from a specific unit."),
                        ],
                        [
                            _b("Baca seluruh map", "Read complete map"),
                            "01 04 00 00 00 08 F1 CC",
                            _b("Request FC04 untuk address 0 sampai 7; respons membawa 16 byte data register.", "FC04 request for addresses 0 through 7; the response carries 16 data bytes."),
                        ],
                    ],
                    [0.20, 0.34, 0.46],
                ),
                _note(
                    _b(
                        "CRC mengikuti urutan Modbus RTU: low byte lalu high byte. Respons sukses pembacaan seluruh map dimulai `01 04 10`, diikuti 16 byte data dan CRC.",
                        "CRC uses Modbus RTU order: low byte then high byte. A successful full-map read begins `01 04 10`, followed by 16 data bytes and CRC.",
                    )
                ),
            ],
        ),
        _section(
            _b("Pemantauan baterai", "Battery monitoring"),
            _b(
                "Tegangan baterai difilter untuk telemetri dan diagnostik. Ambang berikut adalah ambang pemantauan, bukan fungsi pemutusan daya otomatis.",
                "Battery voltage is filtered for telemetry and diagnostics. The following thresholds are monitoring thresholds, not automatic power-disconnection functions.",
            ),
            [
                _table(
                    [_b("Parameter", "Parameter"), _b("Nilai", "Value"), _b("Fungsi", "Function")],
                    [
                        [_b("Sampel per pembacaan", "Samples per reading"), "16", _b("Perataan pembacaan ADC.", "ADC reading averaging.")],
                        [_b("Rasio pembagi tegangan", "Voltage-divider ratio"), "3.0", _b("Konversi tegangan ADC ke tegangan baterai.", "Conversion from ADC voltage to battery voltage.")],
                        [_b("Batas pembacaan valid", "Valid-reading threshold"), "3.0 V minimum", _b("Menolak pembacaan di bawah batas valid.", "Rejects readings below the validity threshold.")],
                        [_b("Ambang rendah", "Low threshold"), "3.5 V", _b("Status pemantauan baterai rendah.", "Low-battery monitoring state.")],
                        [_b("Ambang kritis", "Critical threshold"), "3.3 V", _b("Status pemantauan baterai kritis.", "Critical-battery monitoring state.")],
                        [_b("Koefisien filter", "Filter coefficient"), "0.20", _b("Exponential moving average.", "Exponential moving average.")],
                    ],
                    [0.31, 0.18, 0.51],
                ),
                _note(
                    _b(
                        "Firmware memantau dan melaporkan tegangan baterai, tetapi tidak mencegah boot, menghentikan transmisi, atau memasuki mode daya-rendah berdasarkan ambang tersebut.",
                        "The firmware monitors and reports battery voltage but does not prevent boot, stop transmission, or enter a low-power mode based on these thresholds.",
                    )
                ),
            ],
        ),
    ]


def _ch_sections() -> list[dict[str, Any]]:
    return [
        _section(
            _b("Kapasitas sumber daya firmware", "Firmware resource capacities"),
            _b(
                "Tabel berikut menyatakan batas jumlah entri yang dapat dipertahankan secara bersamaan oleh layanan routing dan transport CH.",
                "The following table states the number of entries that can be retained concurrently by the CH routing and transport services.",
            ),
            [
                _table(
                    [_b("Sumber daya", "Resource"), _b("Kapasitas", "Capacity"), _b("Penggunaan", "Use")],
                    [
                        [_b("Kandidat parent", "Parent candidates"), "8", _b("Kandidat hasil discovery yang dinilai untuk pemilihan parent.", "Discovery candidates evaluated for parent selection.")],
                        [_b("Cache node", "Node cache"), "32", _b("Informasi node yang dikenal oleh CH.", "Information about nodes known to the CH.")],
                        [_b("Antrean alarm", "Alarm queue"), "8", _b("Alarm yang menunggu pemrosesan transport.", "Alarms awaiting transport processing.")],
                        [_b("Antrean transmisi", "Transmission queue"), "8", _b("Item yang menunggu pengiriman radio.", "Items awaiting radio transmission.")],
                        [_b("Downlink tertunda", "Pending downlink"), "16", _b("Perintah atau respons downlink yang masih menunggu penyelesaian.", "Downlink commands or responses awaiting completion.")],
                    ],
                    [0.28, 0.15, 0.57],
                )
            ],
        ),
        _section(
            _b("Status operasi CH", "CH operating states"),
            _b(
                "State machine memisahkan inisialisasi, pembentukan rute, operasi terhubung, failover, dan pemulihan.",
                "The state machine separates initialization, route establishment, connected operation, failover, and recovery.",
            ),
            [
                _table(
                    [_b("Status", "State"), _b("Fungsi", "Function"), _b("Profil produk", "Product profile")],
                    [
                        [_b("Startup", "Startup"), _b("Memulai layanan dan konfigurasi dasar.", "Starts services and base configuration."), _b("Aktif", "Active")],
                        [_b("Menunggu baterai", "Battery-wait state"), _b("Dimasuki singkat saat boot; profil baca-saja melewati ambang kesiapan.", "Entered briefly at boot; the read-only profile bypasses the readiness threshold."), _b("Lanjut langsung ke inisialisasi radio", "Proceeds directly to radio initialization")],
                        [_b("Inisialisasi radio", "Radio initialization"), _b("Menginisialisasi radio STAR dan MESH.", "Initializes the STAR and MESH radios."), _b("Aktif", "Active")],
                        [_b("Discovery jaringan", "Network discovery"), _b("Melakukan discovery dan memilih parent.", "Performs discovery and selects a parent."), _b("Aktif", "Active")],
                        [_b("Terhubung", "Connected"), _b("Meneruskan trafik dengan rute yang telah dipilih.", "Forwards traffic using the selected route."), _b("Aktif", "Active")],
                        [_b("Daya rendah", "Low-power state"), _b("Status tersedia untuk operasi daya-rendah.", "State available for low-power operation."), _b("Tidak dipicu otomatis oleh pembacaan baterai", "Not triggered automatically by the battery reading")],
                        [_b("Failover parent", "Parent failover"), _b("Mencari pengganti ketika parent tidak lagi layak.", "Searches for a replacement when the parent is no longer eligible."), _b("Aktif", "Active")],
                        [_b("Pemulihan", "Recovery"), _b("Memulihkan layanan radio dan routing setelah gangguan.", "Restores radio and routing services after a disturbance."), _b("Aktif", "Active")],
                    ],
                    [0.18, 0.51, 0.31],
                ),
                _note(
                    _b(
                        "Profil produk membaca tegangan baterai untuk telemetri. Nilai tersebut tidak digunakan untuk mencegah boot, menghentikan transmisi, atau mengaktifkan status daya-rendah secara otomatis.",
                        "The product profile reads battery voltage for telemetry. The value is not used to prevent boot, stop transmission, or activate the low-power state automatically.",
                    )
                ),
            ],
        ),
        _section(
            _b("Batas pemilihan parent", "Parent-selection constraints"),
            _b(
                "Pemilihan parent bersifat dinamis berdasarkan hasil discovery dan menerapkan pembatas stabilitas untuk menghindari perpindahan rute yang terlalu cepat.",
                "Parent selection is dynamic and discovery-driven, with stability constraints that prevent excessively rapid route changes.",
            ),
            [
                _table(
                    [_b("Parameter", "Parameter"), _b("Nilai", "Value"), _b("Dampak operasional", "Operational effect")],
                    [
                        [_b("Kapasitas kandidat", "Candidate capacity"), "8", _b("Membatasi jumlah kandidat yang dinilai pada satu waktu.", "Limits the number of candidates evaluated at one time.")],
                        [_b("Batas kesehatan parent", "Parent health timeout"), "16 min", _b("Parent yang tidak terlihat selama interval ini memicu evaluasi failover pada profil produk normal.", "A parent not seen within this interval triggers failover evaluation in the normal product profile.")],
                        [_b("Waktu minimum pada parent", "Minimum parent dwell"), "5 min", _b("Menahan perpindahan rutin sebelum waktu minimum terpenuhi.", "Prevents routine switching before the minimum time has elapsed.")],
                        [_b("Margin perpindahan", "Switch margin"), "15 dB", _b("Kandidat pengganti harus memberikan perbaikan yang cukup untuk perpindahan rutin.", "A replacement candidate must provide sufficient improvement for a routine switch.")],
                        [_b("Discovery stabil", "Stable discoveries"), "4", _b("Berlaku untuk perpindahan rutin di background dan persistensi parent/alternatif; bukan gate initial join atau failover.", "Applies to routine background switching and parent/alternate persistence; it is not an initial-join or failover gate.")],
                    ],
                    [0.31, 0.17, 0.52],
                ),
                _note(
                    _b(
                        "Parent pengganti tidak statis; saat failover, CH memilih kandidat yang memenuhi discovery dan kelayakan aktif.",
                        "The replacement parent is not static; failover selects an eligible discovery candidate.",
                    )
                ),
            ],
        ),
        _section(
            _b("Retensi routing dan transport", "Routing and transport retention"),
            _b(
                "Data routing dan downlink dibatasi oleh masa simpan agar informasi lama tidak dipakai tanpa batas waktu.",
                "Routing and downlink data have bounded retention periods so that old information is not used indefinitely.",
            ),
            [
                _table(
                    [_b("Data", "Data"), _b("Masa simpan", "Retention"), _b("Batas jumlah", "Entry limit")],
                    [
                        [_b("Parent tanpa pembaruan", "Parent without refresh"), "16 min", "1 active parent"],
                        [_b("Downlink tertunda", "Pending downlink"), _b("Default 30 min; TTL perintah dapat mengganti", "Default 30 min; command TTL overrides"), "16"],
                        [_b("Cache node", "Node cache"), "60 min", "32"],
                    ],
                    [0.42, 0.25, 0.33],
                ),
                _bullets(
                    [
                        _b("Antrean dan cache memiliki kapasitas tetap; jumlah entri yang disimpan tidak melampaui batas tabel.", "Queues and caches have fixed capacities; the number of retained entries does not exceed the tabulated limits."),
                        _b("Failover menggunakan hasil discovery yang tersedia, bukan daftar parent pengganti yang diprogram tetap.", "Failover uses the available discovery results, not a programmed fixed replacement-parent list."),
                        _b("Radio STAR dan MESH diproses sebagai antarmuka terpisah agar penerimaan node dan forwarding MESH dapat dikelola independen.", "The STAR and MESH radios are handled as separate interfaces so that node reception and MESH forwarding can be managed independently."),
                    ]
                ),
            ],
        ),
    ]


def _gateway_sections() -> list[dict[str, Any]]:
    return [
        _section(
            _b("Batas konfigurasi jaringan", "Network configuration limits"),
            _b(
                "Gateway memvalidasi panjang setiap bidang konfigurasi sebelum menyimpan dan mengaktifkannya.",
                "The Gateway validates the length of each configuration field before storing and activating it.",
            ),
            [
                _table(
                    [_b("Bidang", "Field"), _b("Batas", "Limit"), _b("Ketentuan", "Requirement")],
                    [
                        ["Wi-Fi SSID", "1-32 bytes", _b("Wajib untuk koneksi Wi-Fi.", "Required for Wi-Fi connectivity.")],
                        [_b("Kata sandi Wi-Fi", "Wi-Fi password"), "0-64 bytes", _b("Nilai kosong diperbolehkan untuk jaringan yang memang tidak memakai kata sandi.", "An empty value is allowed for a network that intentionally has no password.")],
                        ["MQTT host", "1-64 bytes", _b("Host harus terisi ketika MQTT diaktifkan.", "The host must be set when MQTT is enabled.")],
                        ["MQTT user", "0-32 bytes", _b("Digunakan sesuai kebijakan autentikasi broker.", "Used according to the broker authentication policy.")],
                        ["MQTT password", "0-64 bytes", _b("Digunakan sesuai kebijakan autentikasi broker.", "Used according to the broker authentication policy.")],
                        [_b("Port MQTT", "MQTT port"), "1-65535", _b("Nilai nol ditolak.", "Zero is rejected.")],
                        ["NTP host", "1-64 bytes", _b("Wajib untuk varian TLS dan tidak boleh mengandung spasi.", "Required for the TLS variant and must not contain whitespace.")],
                        ["CA certificate (PEM)", "256-3900 bytes", _b("Wajib untuk verifikasi sertifikat pada varian TLS.", "Required for certificate verification on the TLS variant.")],
                    ],
                    [0.28, 0.20, 0.52],
                )
            ],
        ),
        _section(
            _b("Gerbang kesiapan TLS", "TLS readiness gates"),
            _b(
                "Varian TLS hanya membuka koneksi MQTT setelah seluruh prasyarat kepercayaan dan waktu terpenuhi.",
                "The TLS variant opens the MQTT connection only after all trust and time prerequisites have been satisfied.",
            ),
            [
                _table(
                    [_b("Pemeriksaan", "Check"), _b("Syarat diterima", "Acceptance condition"), _b("Jika gagal", "On failure")],
                    [
                        [_b("Sertifikat CA", "CA certificate"), _b("PEM 256-3900 byte, memiliki penanda awal dan akhir sertifikat, tanpa data tambahan setelah penanda akhir.", "A 256-3900-byte PEM value with certificate begin/end markers and no trailing data after the end marker."), _b("Koneksi MQTT diblokir.", "MQTT connection is blocked.")],
                        ["NTP host", _b("Tidak kosong, maksimum 64 byte, tanpa whitespace.", "Non-empty, no more than 64 bytes, without whitespace."), _b("Sinkronisasi waktu tidak dimulai dan MQTT diblokir.", "Time synchronization is not started and MQTT is blocked.")],
                        [_b("Waktu tepercaya", "Trusted time"), _b("Epoch sistem memenuhi ambang firmware: 1.577.836.800 atau lebih besar.", "The system epoch meets the firmware threshold: 1,577,836,800 or greater."), _b("Verifikasi sertifikat dan MQTT tetap diblokir.", "Certificate verification and MQTT remain blocked.")],
                        [_b("Transport", "Transport"), _b("Sertifikat server diverifikasi menggunakan CA yang disediakan.", "The server certificate is verified using the supplied CA."), _b("Tidak ada mode verifikasi-dinonaktifkan.", "No verification-disabled mode is used.")],
                    ],
                    [0.22, 0.55, 0.23],
                )
            ],
        ),
        _section(
            _b("Antrean publikasi MQTT", "MQTT publication queue"),
            _b(
                "Ketika publikasi langsung belum dapat dilakukan, Gateway dapat menahan sejumlah kecil pesan pada antrean volatil.",
                "When immediate publication is not possible, the Gateway can retain a small number of messages in a volatile queue.",
            ),
            [
                _table(
                    [_b("Karakteristik", "Characteristic"), _b("Nilai", "Value"), _b("Perilaku", "Behavior")],
                    [
                        [_b("Kapasitas antrean", "Queue capacity"), "8 messages", _b("Maksimum delapan publikasi tertunda.", "Up to eight deferred publications.")],
                        [_b("Ukuran item", "Item size"), "1024 bytes storage", _b("Panjang payload yang diterima kurang dari 1024 byte; maksimum 1023 byte.", "Accepted payload length is less than 1024 bytes; maximum 1023 bytes.")],
                        [_b("Retensi", "Retention"), _b("Volatil", "Volatile"), _b("Isi antrean tidak dipertahankan setelah perangkat dimulai ulang.", "Queue contents are not retained across a device restart.")],
                        [_b("Antrean penuh", "Full queue"), _b("Item baru ditolak", "New item rejected"), _b("Item yang sudah ada tidak ditimpa oleh item baru.", "Existing items are not overwritten by a new item.")],
                        [_b("Pengosongan antrean", "Queue draining"), _b("Satu slot per iterasi layanan", "One slot per service iteration"), _b("Urutan pengiriman tidak dijamin setelah slot digunakan kembali.", "Delivery order is not guaranteed after slots are reused.")],
                    ],
                    [0.28, 0.23, 0.49],
                )
            ],
        ),
        _section(
            _b("Pembaruan konfigurasi transaksional", "Transactional configuration update"),
            _b(
                "Perubahan jaringan tidak langsung mengganti konfigurasi aktif. Gateway menyelesaikan penyimpanan dan verifikasi kandidat sebelum mengaktifkannya.",
                "A network change does not immediately replace the active configuration. The Gateway completes candidate storage and verification before activation.",
            ),
            [
                _table(
                    [_b("Tahap", "Stage"), _b("Tindakan", "Action"), _b("Hasil", "Result")],
                    [
                        ["1", _b("Validasi seluruh bidang kandidat.", "Validate all candidate fields."), _b("Kandidat tidak valid ditolak sebelum penyimpanan.", "An invalid candidate is rejected before storage.")],
                        ["2", _b("Tulis kandidat ke area konfigurasi yang tidak aktif.", "Write the candidate to the inactive configuration area."), _b("Konfigurasi aktif tetap tersedia selama penulisan.", "The active configuration remains available during the write.")],
                        ["3", _b("Baca kembali dan bandingkan hasil penyimpanan.", "Read back and compare the stored result."), _b("Aktivasi hanya dilanjutkan jika hasil identik.", "Activation continues only if the result is identical.")],
                        ["4", _b("Aktifkan kandidat sebagai konfigurasi terbaru.", "Activate the candidate as the latest configuration."), _b("Penanda konfigurasi aktif diperbarui terakhir.", "The active-configuration indicator is updated last.")],
                        ["5", _b("Batalkan kandidat jika salah satu tahap gagal.", "Discard the candidate if any stage fails."), _b("Konfigurasi aktif sebelumnya dipertahankan.", "The previous active configuration is retained.")],
                    ],
                    [0.10, 0.49, 0.41],
                )
            ],
        ),
        _section(
            _b("Varian produk Gateway", "Gateway product variants"),
            _b(
                "Fungsi Gateway tersedia pada dua bentuk PCB. Masing-masing bentuk mendukung profil transport standar dan TLS.",
                "Gateway functionality is available on two PCB forms. Each form supports standard and TLS transport profiles.",
            ),
            [
                _table(
                    [_b("Bentuk perangkat", "Device form"), _b("Profil standar", "Standard profile"), _b("Profil TLS", "TLS profile"), _b("Radio aktif", "Active radio")],
                    [
                        [_b("Rectangle (kecil)", "Rectangle (small)"), _b("MQTT tanpa TLS", "MQTT without TLS"), "MQTT over TLS", "LoRa MESH"],
                        [_b("Circle (besar)", "Circle (large)"), _b("MQTT tanpa TLS", "MQTT without TLS"), "MQTT over TLS", "LoRa MESH"],
                    ],
                    [0.28, 0.25, 0.25, 0.22],
                ),
                _note(
                    _b(
                        "Pemilihan bentuk PCB dan profil transport dilakukan pada saat penyiapan firmware. Radio LoRa STAR tidak digunakan pada peran Gateway.",
                        "PCB form and transport profile are selected during firmware preparation. The LoRa STAR radio is not used in the Gateway role.",
                    )
                ),
            ],
        ),
    ]


def _server_sections() -> list[dict[str, Any]]:
    return [
        _section(
            _b("Model data aplikasi", "Application data model"),
            _b(
                "Server mengubah data perangkat menjadi bidang aplikasi yang dapat digunakan oleh penyimpanan, tampilan topologi, dan alarm.",
                "The Server converts device data into application fields used by storage, topology display, and alarms.",
            ),
            [
                _table(
                    [_b("Bidang", "Field"), _b("Arti", "Meaning"), _b("Penggunaan", "Use")],
                    [
                        ["node ID", _b("Pengenal node sumber.", "Source-node identifier."), _b("Korelasi perangkat dan topologi.", "Device and topology correlation.")],
                        ["gas class / gas name", _b("Hasil klasifikasi dan nama tampilannya.", "Classification result and its display name."), _b("Status deteksi pada aplikasi.", "Detection status in the application.")],
                        ["confidence", _b("Nilai kepercayaan hasil inferensi.", "Inference-result confidence value."), _b("Konteks untuk interpretasi hasil.", "Context for result interpretation.")],
                        ["battery mV", _b("Tegangan baterai yang dilaporkan perangkat.", "Battery voltage reported by the device."), _b("Pemantauan daya.", "Power monitoring.")],
                        ["alarm", _b("Status alarm perangkat.", "Device alarm state."), _b("Indikasi alarm pada antarmuka aplikasi.", "Alarm indication in the application interface.")],
                        ["external power", _b("Status sumber daya eksternal.", "External power-source state."), _b("Diagnostik catu daya.", "Power-supply diagnostics.")],
                        ["sequence", _b("Nomor urut pesan sumber.", "Source message sequence number."), _b("Pengurutan dan deteksi pengulangan.", "Ordering and repetition detection.")],
                        ["gateway", _b("Gateway yang menerima data.", "Gateway that received the data."), _b("Korelasi jalur komunikasi.", "Communication-path correlation.")],
                        ["last seen", _b("Waktu terakhir data diterima.", "Time at which data was last received."), _b("Status keterhubungan pada aplikasi.", "Connectivity state in the application.")],
                    ],
                    [0.24, 0.42, 0.34],
                )
            ],
        ),
        _section(
            _b("Skema rekaman dataset", "Dataset record schema"),
            _b(
                "Perekam dataset menyimpan identitas, konteks akuisisi, delapan nilai sensor, gain, status sensor, dan kunci idempotensi dalam satu rekaman.",
                "The dataset recorder stores identity, acquisition context, eight sensor values, gain, sensor status, and an idempotency key in each record.",
            ),
            [
                _table(
                    [_b("Kelompok", "Group"), _b("Bidang", "Fields"), _b("Keterangan", "Description")],
                    [
                        [_b("Identitas", "Identity"), _b("Identitas perangkat, node, dan rekaman unik", "Device, node, and unique-record identity"), _b("Identitas sumber dan kunci unik rekaman.", "Source identity and unique record key.")],
                        [_b("Konteks", "Context"), _b("Mode, urutan, waktu, label, dan profil nulling", "Mode, sequence, time, label, and nulling profile"), _b("Konteks akuisisi untuk tiap rekaman.", "Acquisition context for each record.")],
                        [_b("Tegangan sensor", "Sensor voltages"), _b("Delapan nilai sensor tervalidasi", "Eight validated sensor values"), _b("Satu nilai untuk setiap channel.", "One value for each channel.")],
                        ["Gain", _b("Gain per channel", "Per-channel gain"), _b("Gain akuisisi untuk setiap channel.", "Acquisition gain for each channel.")],
                        [_b("Kesehatan sensor", "Sensor health"), _b("Status validitas delapan channel", "Eight-channel validity state"), _b("Status validitas setiap channel sensor.", "Validity state for each sensor channel.")],
                        [_b("Urutan fitur", "Feature order"), _b("Urutan sensor kanonik", "Canonical sensor order"), _b("Menjaga konsistensi struktur dataset.", "Preserves dataset-structure consistency.")],
                    ],
                    [0.23, 0.39, 0.38],
                ),
                _note(
                    _b(
                        "Setiap rekaman memiliki pengenal unik 64 karakter sehingga pengiriman ulang rekaman yang sama tidak menghasilkan duplikasi pada penyimpanan utama.",
                        "Each record has a unique 64-character identifier so that resubmission of the same record does not create a duplicate in primary storage.",
                    )
                ),
            ],
        ),
        _section(
            _b("Aturan penerimaan dataset", "Dataset admission rules"),
            _b(
                "Rekaman hanya diterima jika seluruh syarat integritas data terpenuhi sebelum penulisan ke penyimpanan.",
                "A record is accepted only when all data-integrity requirements are satisfied before storage.",
            ),
            [
                _table(
                    [_b("Pemeriksaan", "Check"), _b("Syarat", "Requirement")],
                    [
                        [_b("Mode", "Mode"), _b("Rekaman harus menggunakan mode dataset engineering.", "The record must use engineering dataset mode.")],
                        [_b("Identitas sumber", "Source identity"), _b("Identitas perangkat harus valid, konsisten dengan jalur masuk, dan cocok dengan identitas node rekaman.", "The device identity must be valid, consistent with the ingress path, and match the record node identity.")],
                        [_b("Urutan dan waktu", "Sequence and time"), _b("Nomor urut dan timestamp harus berada pada rentang bilangan bulat 32-bit tanpa tanda.", "Sequence and timestamp must be within the unsigned 32-bit integer range.")],
                        [_b("Profil nulling", "Nulling profile"), _b("Pengenal profil berada pada rentang 1-255.", "The profile identifier is within the 1-255 range.")],
                        [_b("Label", "Label"), _b("Wajib terisi, menggunakan karakter aman, dan maksimum 31 karakter.", "Required, limited to safe characters, and no more than 31 characters.")],
                        [_b("Jumlah nilai sensor", "Sensor-value count"), _b("Tepat delapan nilai tegangan yang semuanya finite.", "Exactly eight voltage values, all finite.")],
                        ["Gain", _b("Setiap gain adalah salah satu dari 1, 2, 4, 8, 16, 32, atau 64.", "Each gain is one of 1, 2, 4, 8, 16, 32, or 64.")],
                        [_b("Status sensor", "Sensor status"), _b("Seluruh status sensor bernilai valid.", "All sensor status values indicate valid.")],
                        [_b("Urutan fitur", "Feature order"), _b("Harus sama dengan urutan kanonik MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2.", "Must match the canonical MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 order.")],
                        [_b("Idempotensi", "Idempotency"), _b("Kunci rekaman diperiksa sebelum penulisan agar rekaman yang sama tidak digandakan.", "The record key is checked before writing so that the same record is not duplicated.")],
                    ],
                    [0.31, 0.69],
                )
            ],
        ),
        _section(
            _b("Penyimpanan dan ketahanan layanan", "Storage and service resilience"),
            _b(
                "Perekam dataset engineering menggunakan jalur penyimpanan yang dikonfigurasi. MySQL digunakan hanya apabila driver dan koneksi tersedia; CSV adalah keluaran perekam dataset, bukan jalur fallback otomatis untuk MySQL.",
                "The engineering dataset recorder uses the configured storage path. MySQL is used only when its driver and connection are available; CSV is a dataset-recorder output, not an automatic MySQL fallback path.",
            ),
            [
                _table(
                    [_b("Komponen", "Component"), _b("Peran", "Role"), _b("Perilaku", "Behavior")],
                    [
                        ["MySQL Server", _b("Penyimpanan dataset bila dikonfigurasi", "Dataset storage when configured"), _b("Menegakkan keunikan pengenal rekaman pada jalur MySQL yang aktif.", "Enforces unique record identifiers on the active MySQL path.")],
                        ["CSV", _b("Keluaran perekam dataset", "Dataset-recorder output"), _b("Dihasilkan setelah jalur perekaman yang berlaku berhasil; tidak diperlakukan sebagai pengganti otomatis MySQL.", "Generated after the applicable recording path succeeds; not treated as an automatic MySQL replacement.")],
                        [_b("Tampilan topologi", "Topology view"), _b("Tampilan engineering Node-RED", "Node-RED engineering view"), _b("Menampilkan informasi topologi, parent, discovery, rute, dan status engineering yang diproses flow.", "Shows topology, parent, discovery, route, and engineering-status information processed by the flow.")],
                    ],
                    [0.24, 0.27, 0.49],
                )
            ],
        ),
        _section(
            _b("Persyaratan keamanan penerapan", "Deployment security requirements"),
            _b(
                "Server dipasang pada infrastruktur customer. Kontrol berikut berlaku saat layanan tidak dibatasi hanya pada antarmuka loopback.",
                "The Server is installed on customer infrastructure. The following controls apply when services are not restricted to a loopback interface.",
            ),
            [
                _bullets(
                    [
                        _b("Koneksi broker menggunakan TLS dan autentikasi yang sesuai dengan kebijakan customer.", "Broker connections use TLS and authentication consistent with customer policy."),
                        _b("Kredensial dan material kriptografi disediakan melalui environment runtime atau secret store, bukan ditanamkan pada berkas aplikasi.", "Credentials and cryptographic material are supplied through the runtime environment or a secret store, not embedded in application files."),
                        _b("Deployment wajib mengonfigurasi penyimpanan persisten untuk status anti-replay agar perlindungan dapat dipulihkan setelah layanan dimulai ulang.", "The deployment must configure persistent anti-replay storage so protection can be restored after a service restart."),
                        _b("Akses database, broker, dan aplikasi web dibatasi oleh kontrol jaringan serta akun layanan customer.", "Database, broker, and web-application access is restricted by customer network controls and service accounts."),
                        _b("Pencadangan, retensi, patching sistem operasi, dan pemantauan VM menjadi bagian dari operasi infrastruktur customer.", "Backup, retention, operating-system patching, and VM monitoring form part of customer infrastructure operations."),
                    ]
                ),
                _table(
                    [_b("Area", "Area"), _b("Perilaku aplikasi Server", "Server application behavior"), _b("Tanggung jawab penerapan", "Deployment responsibility")],
                    [
                        [
                            _b("Runtime VM", "VM runtime"),
                            _b("Menjalankan layanan Node-RED dan antarmuka aplikasi.", "Runs the Node-RED services and application interface."),
                            _b("Customer menyediakan VM serta memilih Linux atau Windows.", "The customer provides the VM and selects Linux or Windows."),
                        ],
                        [
                            _b("Broker MQTT", "MQTT broker"),
                            _b("Membentuk sesi terautentikasi dengan verifikasi TLS.", "Establishes an authenticated session with TLS verification."),
                            _b("Customer menyediakan endpoint broker, CA, credential, dan kebijakan akses.", "The customer provides the broker endpoint, CA, credentials, and access policy."),
                        ],
                        [
                            _b("Penyimpanan", "Storage"),
                            _b("Memvalidasi rekaman dan menggunakan jalur penyimpanan dataset yang dikonfigurasi.", "Validates records and uses the configured dataset-storage path."),
                            _b("Customer mengelola layanan database, akses, backup, dan retensi.", "The customer manages the database service, access, backup, and retention."),
                        ],
                        [
                            _b("Anti-replay", "Anti-replay"),
                            _b("Memuat dan memperbarui status replay persisten yang dikonfigurasi.", "Loads and updates the configured persistent replay state."),
                            _b("Customer menyediakan lokasi penyimpanan persisten saat deployment.", "The customer provides persistent storage at deployment."),
                        ],
                        [
                            _b("Tampilan topologi", "Topology view"),
                            _b("Menyediakan tampilan engineering Node-RED untuk topologi dan status yang diproses flow.", "Provides a Node-RED engineering view for topology and status processed by the flow."),
                            _b("Customer membatasi jaringan dan paparan runtime sesuai kebijakan infrastruktur.", "The customer restricts network access and runtime exposure under infrastructure policy."),
                        ],
                    ],
                    [0.18, 0.40, 0.42],
                ),
            ],
        ),
    ]


def _system_sections() -> list[dict[str, Any]]:
    return [
        _section(
            _b("Kontrak antarmuka sistem", "System interface contract"),
            _b(
                "Setiap batas antarsubsistem menggunakan profil komunikasi yang tetap agar GasleakDetector, CH, Gateway, dan Server dapat diintegrasikan secara konsisten.",
                "Each subsystem boundary uses a fixed communication profile so that the GasleakDetector, CH, Gateway, and Server can be integrated consistently.",
            ),
            [
                _table(
                    [_b("Batas", "Boundary"), _b("Antarmuka", "Interface"), _b("Profil", "Profile")],
                    [
                        ["GasleakDetector - CH", "LoRa STAR", "920.0 MHz; SF7; BW 125 kHz; CR 4/5; TX power setting 17 dBm; antenna 3 dBi"],
                        ["CH - CH / Gateway", "LoRa MESH", "921.0 MHz; SF9; BW 125 kHz; CR 4/5; TX power setting 17 dBm; antenna 8 dBi"],
                        ["Gateway - MQTT broker", "Wi-Fi STA / MQTT", _b("MQTT over TLS pada profil TLS; verifikasi sertifikat dan sinkronisasi waktu wajib.", "MQTT over TLS on the TLS profile; certificate verification and time synchronization are mandatory.")],
                        ["Server - MQTT broker", "MQTT", _b("Sesi TLS Server-ke-broker terpisah menggunakan autentikasi deployment customer.", "A separate Server-to-broker TLS session uses customer-deployment authentication.")],
                        ["Server - Database", "MySQL", _b("Penyimpanan dataset engineering dengan pemeriksaan idempotensi.", "Engineering-dataset storage with idempotency checks.")],
                        ["GasleakDetector - controller", "RS-485 / Modbus RTU", _b("Unit 1; 9600 bit/s; 8N1; FC03/FC04; address 0-7; 8 register 16-bit hanya-baca. Lihat datasheet GasleakDetector untuk map dan contoh frame.", "Unit 1; 9600 bit/s; 8N1; FC03/FC04; addresses 0-7; eight read-only 16-bit registers. See the GasleakDetector datasheet for the map and frame examples.")],
                    ],
                    [0.27, 0.23, 0.50],
                ),
                _note(
                    _b(
                        "Band operasi produk dibatasi pada 920-923 MHz. Nilai frekuensi nominal STAR dan MESH berada di dalam band tersebut.",
                        "The product operating band is limited to 920-923 MHz. The nominal STAR and MESH frequencies are within this band.",
                    )
                ),
            ],
        ),
        _section(
            _b("Batas kapasitas subsistem", "Subsystem capacity limits"),
            _b(
                "Kapasitas berikut adalah batas implementasi yang perlu diperhitungkan saat merancang jumlah node, aliran downlink, dan pemulihan koneksi.",
                "The following capacities are implementation limits to consider when designing node counts, downlink flows, and connection recovery.",
            ),
            [
                _table(
                    [_b("Subsistem", "Subsystem"), _b("Sumber daya", "Resource"), _b("Batas", "Limit")],
                    [
                        ["GasleakDetector", _b("Channel sensor", "Sensor channels"), "8"],
                        ["GasleakDetector", _b("Register Modbus", "Modbus registers"), _b("8 register 16-bit hanya-baca, address 0-7", "Eight read-only 16-bit registers, addresses 0-7")],
                        ["CH", _b("Kandidat parent", "Parent candidates"), "8"],
                        ["CH", _b("Cache node", "Node cache"), "32 entries"],
                        ["CH", _b("Antrean alarm / transmisi", "Alarm / transmission queue"), "8 / 8 entries"],
                        ["CH", _b("Downlink tertunda", "Pending downlink"), "16 entries"],
                        ["Gateway", _b("Antrean publikasi MQTT", "MQTT publication queue"), "8 volatile messages"],
                        ["Gateway", _b("Payload publikasi tertunda", "Deferred-publication payload"), "1023 bytes maximum"],
                        ["Server", _b("Nilai sensor per rekaman dataset", "Sensor values per dataset record"), "8"],
                    ],
                    [0.27, 0.49, 0.24],
                )
            ],
        ),
        _section(
            _b("Perilaku saat gangguan", "Failure behavior"),
            _b(
                "Respons setiap subsistem terhadap gangguan dibuat eksplisit agar keterbatasan pemulihan dan retensi data dapat diperhitungkan pada desain penerapan.",
                "Each subsystem response to a disturbance is explicit so that recovery and data-retention limitations can be considered in deployment design.",
            ),
            [
                _table(
                    [_b("Gangguan", "Disturbance"), _b("Respons sistem", "System response"), _b("Batas", "Limitation")],
                    [
                        [_b("Parent CH tidak lagi layak", "CH parent no longer eligible"), _b("CH menjalankan discovery dan memilih kandidat parent yang memenuhi aturan saat itu.", "The CH performs discovery and selects a parent candidate that satisfies the current rules."), _b("Parent pengganti tidak ditetapkan secara statis.", "The replacement parent is not statically assigned.")],
                        [_b("Wi-Fi atau broker tidak tersedia", "Wi-Fi or broker unavailable"), _b("Gateway mencoba mempublikasikan kembali dan menggunakan antrean lokal bila item dapat diterima.", "The Gateway retries publication and uses the local queue when an item can be admitted."), _b("Antrean bersifat volatil, maksimum delapan item.", "The queue is volatile and holds at most eight items.")],
                        [_b("Prasyarat TLS tidak lengkap", "TLS prerequisite incomplete"), _b("Gateway memblokir koneksi MQTT.", "The Gateway blocks the MQTT connection."), _b("Tidak ada fallback ke transport TLS tanpa verifikasi.", "There is no fallback to a TLS transport without verification.")],
                        [_b("Penyimpanan MySQL tidak tersedia", "MySQL storage unavailable"), _b("Jalur perekaman dataset yang aktif gagal dan harus dipulihkan sesuai konfigurasi deployment.", "The active dataset-recording path fails and must be restored according to the deployment configuration."), _b("CSV tidak diperlakukan sebagai pengganti otomatis MySQL; status perlu dimonitor dan direkonsiliasi oleh operator Server.", "CSV is not treated as an automatic MySQL replacement; status must be monitored and reconciled by the Server operator.")],
                        [_b("Rekaman dataset tidak valid", "Invalid dataset record"), _b("Server menolak rekaman sebelum penyimpanan.", "The Server rejects the record before storage."), _b("Rekaman harus memenuhi semua aturan penerimaan.", "The record must satisfy every admission rule.")],
                        [_b("Tegangan baterai rendah", "Low battery voltage"), _b("GasleakDetector dan CH melaporkan hasil pemantauan.", "The GasleakDetector and CH report the monitoring result."), _b("Firmware tidak melakukan pemutusan atau low-power otomatis berdasarkan ambang ini.", "Firmware does not automatically disconnect power or enter low-power mode based on this threshold.")],
                    ],
                    [0.25, 0.49, 0.26],
                )
            ],
        ),
        _section(
            _b("Batas keamanan", "Security boundaries"),
            _b(
                "Keamanan end-to-end dibentuk oleh kontrol radio, validasi pesan aplikasi, transport Gateway-Server, dan kontrol infrastruktur Server.",
                "End-to-end security is formed by radio controls, application-message validation, Gateway-to-Server transport, and Server infrastructure controls.",
            ),
            [
                _table(
                    [_b("Batas", "Boundary"), _b("Kontrol", "Control"), _b("Tanggung jawab operasi", "Operational responsibility")],
                    [
                        [_b("Hop radio field", "Field radio hop"), _b("Identitas node, urutan pesan, panjang, dan CRC diperiksa pada protokol radio aplikasi.", "Node identity, message sequence, length, and CRC are checked by the radio application protocol."), _b("Identitas perangkat dan konfigurasi radio dikelola saat provisioning.", "Device identities and radio configuration are managed during provisioning.")],
                        [_b("Aplikasi Server", "Server application"), _b("Server melakukan autentikasi AES-GCM dan penolakan replay; status persisten wajib pada deployment.", "The Server performs AES-GCM authentication and replay rejection; persistent state is required in deployment."), _b("Material keamanan dan penyimpanan anti-replay dikelola pada deployment Server.", "Security material and anti-replay storage are managed in the Server deployment.")],
                        [_b("Gateway / Server - broker", "Gateway / Server - broker"), _b("Pada deployment profil TLS yang dikonfigurasi, Gateway dan Server dapat memakai dua sesi MQTT over TLS terpisah dengan validasi sertifikat.", "In a configured TLS-profile deployment, the Gateway and Server can use two separate MQTT-over-TLS sessions with certificate validation."), _b("Customer menyediakan CA, endpoint waktu, broker, dan kebijakan autentikasi.", "The customer supplies the CA, time endpoint, broker, and authentication policy.")],
                        [_b("Layanan Server", "Server services"), _b("Kredensial berada pada environment runtime atau secret store; penyimpanan anti-replay persisten wajib dikonfigurasi.", "Credentials reside in the runtime environment or a secret store; persistent anti-replay storage must be configured."), _b("Customer mengelola akses jaringan, akun layanan, pencadangan, patching, dan monitoring VM.", "The customer manages network access, service accounts, backup, patching, and VM monitoring.")],
                        [_b("Penyimpanan", "Storage"), _b("Pengenal rekaman unik mencegah duplikasi dataset pada penyimpanan utama.", "A unique record identifier prevents dataset duplication in primary storage."), _b("Retensi, backup, dan rekonsiliasi ditetapkan dalam prosedur operasi customer.", "Retention, backup, and reconciliation are defined in customer operating procedures.")],
                    ],
                    [0.20, 0.47, 0.33],
                )
            ],
        ),
    ]


_FACTORIES = {
    "gld": _gld_sections,
    "ch": _ch_sections,
    "gateway": _gateway_sections,
    "server": _server_sections,
    "system": _system_sections,
}


_GROUP_TITLES = {
    "gld": _b("Parameter operasional dan antarmuka", "Operational parameters and interfaces"),
    "ch": _b("Routing dan kapasitas operasional", "Routing and operational capacities"),
    "gateway": _b("Jaringan, TLS, dan konfigurasi", "Networking, TLS, and configuration"),
    "server": _b("Model data, penyimpanan, dan keamanan", "Data model, storage, and security"),
    "system": _b("Kontrak integrasi dan batas sistem", "Integration contract and system limits"),
}


_SLUG_ALIASES = {
    "gld": "gld",
    "gasleakdetector": "gld",
    "gas-leak-detector": "gld",
    "ch": "ch",
    "gateway": "gateway",
    "gw": "gateway",
    "server": "server",
    "system": "system",
    "whole-system": "system",
    "whole_system": "system",
    "whole system": "system",
}


def supplement_groups(slug: str, lang: str) -> list[dict[str, Any]]:
    """Return resolved, customer-facing supplemental datasheet groups.

    Each returned dictionary has a ``title`` and ``subsections``. Every
    subsection has ``title``, ``lead``, and ``blocks`` keys. Blocks use the same
    ``table``, ``bullets``, and ``note`` shapes as the main technical-datasheet
    content module. ``slug`` accepts the public document slugs as well as the
    short names gld, ch, gateway, server, and system.
    """

    normalized_slug = slug.strip().casefold()
    canonical_slug = _SLUG_ALIASES.get(normalized_slug)
    if canonical_slug is None:
        supported = ", ".join(sorted(_FACTORIES))
        raise ValueError(f"Unknown supplement slug {slug!r}; expected one of: {supported}")

    normalized_lang = lang.strip().upper()
    if normalized_lang not in {"ID", "EN"}:
        raise ValueError(f"Unknown language {lang!r}; expected 'ID' or 'EN'")

    language_index = 0 if normalized_lang == "ID" else 1
    sections = deepcopy(_FACTORIES[canonical_slug]())
    if canonical_slug == "gld":
        sections = [
            section for section in sections
            if section["title"][0] != "Pemantauan baterai"
        ]
    group = {
        "title": _GROUP_TITLES[canonical_slug],
        "subsections": sections,
    }
    return [_resolve(group, language_index)]


__all__ = ["supplement_groups"]
