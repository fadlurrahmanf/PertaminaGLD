"""Slide-by-slide content for the Operator Hub guide (Bahasa Indonesia)."""

from pptx import Presentation
from pptx.util import Inches

from deck import (OUT_DIR, OUT_PPTX, SH, SW, slide_cover, slide_section,
                        slide_shot, slide_text)


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH

    # ================================================================= INTRO
    slide_cover(
        prs,
        "Panduan Operator Hub",
        "Konsol operator GLD, ClusterHead, dan Gateway — dari upload firmware\n"
        "sampai pengambilan dataset, nulling, QC, dan monitoring mesh.",
        "apps/operator-hub  ·  Pertamina GLD  ·  Dokumen operasional",
    )

    slide_text(
        prs, "Pendahuluan", "Apa itu Operator Hub",
        "Satu pintu masuk untuk tiga konsol operator yang sudah ada.",
        [
            ("Peran Hub", [
                "Operator Hub tidak menggantikan aplikasi mana pun. Hub "
                "menjalankan bridge.py masing-masing konsol sebagai proses "
                "anak di port sendiri, lalu menampilkannya di dalam satu "
                "jendela lewat tab.",
                "",
                "• Hub — port 5173",
                "• GLD Operator — port 5174",
                "• CH Operator — port 5273",
                "• Gateway Operator — port 5373",
            ]),
            ("Cara menjalankan", [
                "Jalankan berkas:",
                "run-operator-hub.bat",
                "",
                "Browser otomatis terbuka ke:",
                "http://127.0.0.1:5173/",
                "",
                "Menutup jendela Hub (atau Ctrl+C di konsolnya) otomatis "
                "menghentikan ketiga bridge anak yang dijalankannya.",
            ]),
            ("Preflight saat start", [
                "Sebelum menjalankan konsol anak, Hub melakukan pemeriksaan "
                "read-only:",
                "• Python runtime Hub dan CH",
                "• Uploader Espressif di apps/lib/esptool*",
                "• Paket firmware offline + hash-nya",
                "• Driver CH340 Windows",
                "• Port lokal yang dibutuhkan",
                "",
                "Preflight tidak pernah mengunduh, memasang driver, membuka "
                "COM, atau menulis firmware — hanya melaporkan.",
            ]),
        ],
        note="Titik hijau pada setiap tab menyala saat bridge konsol tersebut "
             "menjawab /api/health. Hub yang melakukan polling ini, karena "
             "browser tidak bisa memeriksa lintas-origin.",
    )

    slide_shot(
        prs, "Pendahuluan", "Halaman awal Operator Hub",
        "Hub selalu terbuka di halaman pemilihan konsol.",
        "00-hub-landing",
        [
            ("1", "Tab bar. Pindah konsol kapan saja; titik hijau = bridge sehat."),
            ("2", "Kartu GLD — Gas Leak Detector (sensor, dataset, kalibrasi)."),
            ("3", "Kartu CH — Cluster Head (LoRa, serial, routing, firmware)."),
            ("4", "Kartu GW — Gateway (Wi-Fi, MQTT, topologi).", "blue"),
            ("5", "Status preflight: siap / ada yang kurang.", "blue"),
            ("6", "Klik judul \"Operator Hub\" untuk kembali ke halaman ini.", "blue"),
        ],
        note="Setiap konsol tetap bisa dijalankan sendiri lewat "
             "run-gld-operator.bat / run-ch-operator.bat / run-gw-operator.bat.",
    )

    slide_text(
        prs, "Pendahuluan", "Tentang tangkapan layar di dokumen ini",
        "Supaya panel tidak kosong, layar diisi data contoh.",
        [
            ("Kondisi pengambilan", [
                "Semua tangkapan layar diambil tanpa perangkat keras "
                "terhubung.",
                "",
                "• GLD memakai simulator bawaan aplikasi — badge di kanan "
                "atas tertulis \"mock\".",
                "• CH dan Gateway diisi contoh telemetri yang formatnya sama "
                "dengan yang dikirim firmware.",
            ]),
            ("Baris status upload", [
                "Layar \"upload berjalan\" dan \"upload selesai\" adalah "
                "contoh tampilan status, bukan hasil flashing nyata.",
                "",
                "Teksnya persis sama dengan yang ditulis aplikasi pada "
                "kondisi tersebut.",
            ]),
            ("Angka pada layar", [
                "COM, ID perangkat, RSSI, SSID, dan alamat broker pada "
                "gambar adalah contoh.",
                "",
                "Di lapangan nilainya mengikuti perangkat dan jaringan "
                "yang dipakai.",
            ]),
        ],
    )

    # =================================================================== GLD
    slide_section(
        prs, "1", "GLD — Gas Leak Detector",
        "Konsol sensor: firmware, mode operasi, dataset, nulling, dan QC.",
        [
            "Upload firmware (pilih ENV dan COM, tunggu sampai selesai)",
            "Mode Running — telemetri 8 kanal MQ secara langsung",
            "Mode Dataset — perekaman data berlabel lewat MQTT",
            "Mode Nulling — pencarian titik nol tiap kanal",
            "QC — verdict Pass/Fail per kanal, tersimpan di NVS GLD",
            "Log, Ops Panel, Expert Terminal",
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 1", "Pilih menu GLD",
        "Dari halaman awal Hub, klik kartu GLD (atau tab GLD di atas).",
        "00-hub-landing",
        [
            ("2", "Klik kartu Gas Leak Detector untuk masuk konsol GLD."),
            ("1", "Atau langsung lewat tab GLD di tab bar.", "blue"),
            ("5", "Pastikan status preflight sudah \"ready\" sebelum mulai "
                  "flashing — kalau ada dependensi upload yang kurang, "
                  "dashboard tetap terbuka tetapi tombol flashing "
                  "ditandai tidak tersedia.", "blue"),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 2", "Kenali layar konsol GLD",
        "Header berisi status live dan empat tombol utama.",
        "gld-01-shell",
        [
            ("1", "Badge status: koneksi serial, bridge, port aktif, ID "
                  "perangkat, dan mode saat ini."),
            ("2", "Ops Panel — slot armada, perintah cepat, ganti mode."),
            ("3", "Firmware Upload — dialog flashing (langkah berikutnya)."),
            ("4", "Port Setup — pilih dan sambungkan COM."),
            ("5", "Enam tab kerja: Running, Dataset, Nulling, QC, Log, Expert.",
             "blue"),
        ],
    )

    slide_shot(
        prs, "GLD · Prasyarat", "Port Setup — sambungkan COM lebih dulu",
        "Semua perintah serial memerlukan koneksi COM yang aktif.",
        "gld-02-portsetup",
        [
            ("1", "Daftar COM hasil pemindaian bridge. Pilih port GLD."),
            ("2", "Scan — pindai ulang kalau kabel baru dicolok."),
            ("3", "Kalau port tidak muncul, ketik manual (mis. COM10) lalu "
                  "tekan Use Manual."),
            ("4", "Connect Serial — baud tetap 115200."),
            ("5", "Detail port terpilih ditampilkan di sini.", "blue"),
        ],
        note="Upload firmware akan memutus koneksi serial ini sendiri, lalu "
             "menyambung ulang secara otomatis setelah flashing selesai.",
    )

    slide_shot(
        prs, "GLD · Langkah 3 & 4", "Firmware Upload — pilih ENV, pilih COM, klik Upload",
        "Tombol Firmware Upload membuka dialog ini dan memuat paket firmware "
        "bawaan.",
        "gld-03-fwdialog",
        [
            ("1", "Firmware environment — pilih gld atau gldFieldtest. "
                  "Mengganti pilihan langsung memuat ulang paketnya."),
            ("2", "Target COM — port yang akan di-flash."),
            ("3", "Reset NVS? Tidak dicentang: semua parameter NVS "
                  "dipertahankan. Dicentang: NVS dihapus, perangkat boot "
                  "dengan seluruh default firmware termasuk GLD ID 1001."),
            ("4", "Baris status memberi tahu apakah dialog sudah siap.", "blue"),
            ("5", "Klik Upload untuk memulai flashing."),
        ],
        note="Nama paket yang dimuat tampil di atas (contoh: \"Package: gld "
             "v0.8.14\"). Kalau tertulis \"Package belum tersedia\", paket "
             "firmware offline-nya belum ada.",
    )

    slide_shot(
        prs, "GLD · Langkah 5", "Tunggu sampai upload selesai",
        "Selama proses berjalan, tombol dialog dikunci agar tidak terputus.",
        "gld-04-fwprogress",
        [
            ("1", "Baris status berjalan: aplikasi memutus serial lebih dulu, "
                  "baru mengirim firmware ke COM tujuan."),
            ("2", "Upload dan Cancel dinonaktifkan, checkbox Reset NVS "
                  "dikunci. Jangan cabut kabel pada tahap ini.", "blue"),
        ],
        note="Contoh tampilan status — proses upload sebenarnya butuh "
             "perangkat GLD yang terhubung.",
    )

    slide_shot(
        prs, "GLD · Langkah 5", "Upload selesai dan tersambung kembali",
        "Aplikasi otomatis menyambung ulang ke COM yang sama.",
        "gld-05-fwdone",
        [
            ("1", "Status akhir menyebut apakah NVS dipertahankan atau "
                  "direset, lalu hasil reconnect ke COM.", "green"),
        ],
        note="Kalau reconnect gagal, statusnya berbunyi \"Upload berhasil, "
             "tetapi reconnect gagal. Periksa Port Setup\" — buka Port Setup "
             "dan sambungkan manual.",
    )

    slide_shot(
        prs, "GLD · Langkah 6", "Mode Running — telemetri sensor",
        "Tab default. Menampilkan 8 kanal MQ secara langsung.",
        "gld-06-running",
        [
            ("1", "Empat kartu ringkas: Device (ID + versi firmware), Mode "
                  "(+ sumber daya), Gas (+ confidence), LoRa (+ baterai)."),
            ("2", "Toolbar: Switch to Running, rentang grafik (10 detik – "
                  "1 jam), Poll, Clear, Export CSV."),
            ("3", "Kanal 1–4: tegangan dan gain tiap sensor.", "blue"),
            ("4", "Grafik gabungan 8 kanal.", "blue"),
            ("5", "Kanal 5–8.", "blue"),
            ("6", "Ikon gerigi membuka Running Settings (langkah 7)."),
        ],
        note="Urutan kanal CH1–CH8 adalah MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, "
             "MQ6, MQ2.",
    )

    slide_shot(
        prs, "GLD · Langkah 6", "Running — Power dan Boot Health",
        "Bagian lipat di bawah grafik, untuk memastikan IC terbaca saat boot.",
        "gld-07-running-boot",
        [
            ("1", "Power: sumber eksternal dan baterai. Boot Health: status "
                  "ADS (ADC), MCP (DAC gain), DAC, dan ML."),
        ],
        note="Kalau salah satu tertulis tidak siap, jalankan Run Boot Check "
             "dari Running Settings sebelum melanjutkan ke nulling atau QC.",
    )

    slide_shot(
        prs, "GLD · Langkah 7", "Konfigurasi mode Running (1/2)",
        "Poll interval, sumbu Y grafik, identitas perangkat, dan alamat CH.",
        "gld-08-runsettings-a",
        [
            ("1", "Poll Interval — default 500 ms, sama dengan laju scan "
                  "sensor GLD (GLD_SCAN_INTERVAL_MS). Polling lebih cepat "
                  "hanya mengulang balasan lama."),
            ("2", "Fix Y-axis — default mati (auto-scale). Aktifkan untuk "
                  "mengunci rentang tegangan agar grafik berhenti "
                  "menyesuaikan skala."),
            ("3", "Target GLD ID, rentang 1001–FEFF. Tombol Inject ID baru "
                  "aktif setelah Expert Terminal dibuka."),
            ("4", "Target CH Address, rentang 0010–0FFF, dan tidak boleh "
                  "sama dengan ID GLD itu sendiri."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 7", "Konfigurasi mode Running (2/2)",
        "Radio LoRa STAR dan pemeriksaan sensor MQ.",
        "gld-09-runsettings-b",
        [
            ("1", "LoRa STAR: frekuensi 920–923 MHz, bandwidth, SF 5–12, "
                  "CR 5–8, sync word, TX power −9…22 dBm, preamble, tegangan "
                  "TCXO/XTAL."),
            ("2", "Apply LoRa. Nilai ini harus sama persis dengan radio STAR "
                  "di CH, kalau tidak link berhenti membawa data."),
            ("3", "MQ Sensor Check + Boot IC Report: Refresh Status, Run Boot "
                  "Check, dan status kehadiran tiap kanal MQ.", "blue"),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 8", "Mode Dataset — sesi perekaman",
        "Perekaman bersifat manual seperti perekam video: mulai saat Start, "
        "berhenti saat Stop.",
        "gld-10-dataset",
        [
            ("1", "Switch to Dataset — memindahkan GLD ke mode dataset lalu "
                  "membuka Dataset Settings."),
            ("2", "Ikon gerigi membuka Dataset Settings kapan saja."),
            ("3", "Wizard 6 langkah: Switch Mode → Confirm Config → Start → "
                  "Capturing → Stop → Save.", "blue"),
            ("4", "Kartu status: state sesi, jumlah baris terekam, waktu "
                  "berjalan, dan nama berkas keluaran.", "blue"),
            ("5", "Start Dataset baru aktif setelah Confirm Config berhasil."),
            ("6", "Stop Dataset mengakhiri sesi.", "blue"),
        ],
        note="Tidak ada batas jumlah sampel maupun durasi — sesi berjalan "
             "sampai Anda menekan Stop.",
    )

    slide_shot(
        prs, "GLD · Langkah 8", "Dataset — baris terbaru dan berkas keluaran",
        "Berkas di disk sudah ditulis langsung selama perekaman.",
        "gld-11-dataset-rows",
        [
            ("1", "Tabel baris terakhir: waktu, sumber, sequence, label, dan "
                  "delapan kolom MQ."),
            ("2", "Download Snapshot hanya mengunduh salinan baris yang "
                  "tampil di layar."),
            ("3", "Open Folder membuka direktori hasil di disk."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 9", "Konfigurasi mode Dataset (1/2) — Wi-Fi dan MQTT",
        "Data dataset dikirim lewat MQTT, jadi bagian ini wajib berhasil "
        "lebih dulu.",
        "gld-12-datasetsettings",
        [
            ("1", "SSID dan password Wi-Fi yang akan dipakai GLD."),
            ("2", "Host, port, user, password broker, dan topic root."),
            ("3", "Apply GLD Settings — mengirim konfigurasi ke perangkat."),
            ("4", "Use this PC mengisi host dengan alamat PC ini; Test Broker "
                  "memeriksa apakah broker bisa dihubungi."),
        ],
        note="Tombol Confirm Config di bawah tetap terkunci sampai Apply GLD "
             "Settings berhasil.",
    )

    slide_shot(
        prs, "GLD · Langkah 9", "Konfigurasi mode Dataset (2/2) — parameter dan konfirmasi",
        "Parameter perekaman lalu pembuatan berkas.",
        "gld-13-datasetsettings-b",
        [
            ("1", "Label — nama kelas data, ikut jadi bagian nama berkas."),
            ("2", "Interval Ms, Fan On Ms, dan Post Fan Settle Ms."),
            ("3", "Run nulling before dataset — default mati. Aktifkan hanya "
                  "kalau GLD ini perlu profil nulling baru sebelum merekam."),
            ("4", "Confirm Config & Create File — membuat berkas CSV dan "
                  "membuka kunci tombol Start Dataset."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 10", "Mode Nulling — pencarian titik nol",
        "Setiap kanal dicari kode DAC-nya sampai tegangan mendekati target.",
        "gld-14-nulling",
        [
            ("1", "Switch to Nulling — memindahkan GLD ke mode nulling."),
            ("2", "Ringkasan proses dan meta: retry armed, jumlah percobaan.",
             "blue"),
            ("3", "Satu kartu per kanal: tahap berjalan, meter sweep DAC, "
                  "nilai baseline dan after, serta detail tiap tahap "
                  "(baseline → eksponensial → biner → konfirmasi).", "blue"),
            ("4", "Ikon gerigi membuka Nulling Settings."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 10", "Nulling — log mentah",
        "Semua baris NULLING_* dari firmware tampil apa adanya.",
        "gld-15-nullinglog",
        [
            ("1", "Log ini yang menjadi sumber tampilan kartu di atasnya — "
                  "berguna saat satu kanal gagal dan perlu ditelusuri."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 10", "Nulling Settings — ambang batas",
        "Ambang mengikuti baseline tiap kanal.",
        "gld-16-nullingsettings",
        [
            ("1", "Minimum Delta Threshold (V). Target tiap kanal dihitung "
                  "sebagai baseline + max(|baseline| / 2, ambang minimum ini)."),
            ("2", "Apply Thresholds — nilai berlaku pada proses nulling "
                  "berikutnya dan tersimpan di GLD."),
            ("3", "Refresh from GLD — membaca ulang nilai yang tersimpan di "
                  "perangkat."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 11", "QC — verdict per kanal",
        "Kanal harus lulus nulling dulu, baru operator memberi Pass/Fail.",
        "gld-17-qc",
        [
            ("1", "Grup QC: MQ dan TPL."),
            ("2", "Sub-tab: All Sensor plus delapan kanal MQ.", "blue"),
            ("3", "QC-OFF / QC-ON — menampilkan grafik sensor langsung supaya "
                  "operator bisa menilai Pass/Fail secara visual."),
            ("4", "Kartu tiap kanal: status nulling, status pengujian, dan "
                  "tombol verdict.", "blue"),
        ],
        note="Verdict disimpan di NVS GLD sendiri, jadi bertahan setelah "
             "aplikasi disambung ulang atau kabel dicabut. GET_QC_STATUS "
             "selalu menjadi acuan, bukan ingatan aplikasi.",
    )

    slide_shot(
        prs, "GLD · Langkah 11", "QC — panel satu kanal",
        "Sub-tab per sensor memberi kendali khusus untuk kanal itu saja.",
        "gld-18-qc-channel",
        [
            ("1", "Di panel per kanal tersedia Pass/Fail, nulling untuk satu "
                  "kanal saja, Reset verdict, dan Full Scale MCP Sweep "
                  "(menyapu DAC 0–4095 lalu bisa diekspor ke CSV)."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 12", "Log — aliran serial mentah",
        "Semua baris yang dikirim dan diterima lewat serial.",
        "gld-19-log",
        [
            ("1", "Pause menahan tampilan (jumlah baris tertahan ikut "
                  "dihitung); tekan lagi untuk melanjutkan."),
            ("2", "Download Log menyimpan lewat browser."),
            ("3", "Save Log to Disk menyimpan lewat bridge ke folder sesi."),
            ("4", "Isi log — sumber pertama saat menelusuri masalah.", "blue"),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 13", "Ops Panel",
        "Laci samping untuk armada, perintah cepat, dan penggantian mode.",
        "gld-20-ops",
        [
            ("1", "Fleet — sampai 8 slot GLD. Slot aktif menentukan port dan "
                  "data yang ditampilkan seluruh tab."),
            ("2", "+ Add Slot menambah GLD lain ke sesi yang sama."),
            ("3", "Perintah cepat: Ping, Info, Status, Restart GLD.", "blue"),
            ("4", "Device Mode: Running, Dataset, Nulling — jalan pintas "
                  "mengganti mode tanpa pindah tab."),
        ],
    )

    slide_shot(
        prs, "GLD · Langkah 14", "Expert Terminal dan timeout",
        "Bagian lanjutan, terkunci PIN.",
        "gld-21-expert",
        [
            ("1", "Unlock — PIN lokal. Ini hanya penghalang, bukan pengaman "
                  "sungguhan. Membuka kunci juga mengaktifkan Inject ID dan "
                  "Apply CH Address."),
            ("2", "Kirim perintah serial bebas, mis. GET_STATUS."),
            ("3", "Timeout: respons serial, kesiapan dataset, dan ambang "
                  "dataset dianggap macet.", "blue"),
        ],
    )

    slide_text(
        prs, "GLD · Ringkasan", "Apa lagi yang ada di konsol GLD",
        "Fitur yang tidak masuk urutan langkah utama tetapi sering dipakai.",
        [
            ("Header dan navigasi", [
                "• Dark Mode — ganti tema terang/gelap.",
                "• Badge bridge menunjukkan apakah bridge lokal hidup; tanpa "
                "bridge, upload firmware tidak bisa dijalankan.",
                "• Banner peringatan muncul di bawah header dan bisa "
                "ditutup dengan Dismiss.",
            ]),
            ("Alat bantu kalibrasi", [
                "• Full Scale MCP Sweep — menyapu kode DAC 0–4095 untuk satu "
                "kanal, menampilkan grafik dan tabel, lalu diekspor ke CSV.",
                "• Run Boot Check — menjalankan ulang pemeriksaan IC saat "
                "boot dari Running Settings.",
                "• Export CSV pada tab Running dan Dataset menyimpan isi "
                "grafik yang sedang tampil.",
            ]),
            ("Urutan kerja yang disarankan", [
                "1. Port Setup → Connect",
                "2. Firmware Upload (bila perlu)",
                "3. Running → cek Boot Health",
                "4. Nulling → semua kanal OK",
                "5. QC → verdict per kanal",
                "6. Dataset → Confirm → Start/Stop",
                "7. Log → simpan bukti sesi",
            ]),
        ],
    )

    # ==================================================================== CH
    slide_section(
        prs, "2", "CH — ClusterHead",
        "Penghubung antara GLD (radio STAR) dan Gateway (radio MESH). "
        "Hanya lewat serial USB — tanpa Wi-Fi maupun MQTT.",
        [
            "Upload firmware (ENV ch atau chFieldtest)",
            "Overview — keadaan CH, radio, keepalive, dan pull request",
            "CH Settings — identitas dan dua radio LoRa",
            "Nodes (GLD) — daftar GLD yang melapor ke CH ini",
            "Mesh / Parent — kandidat parent dan failover",
            "Log dan Expert Terminal",
        ],
    )

    slide_shot(
        prs, "CH · Langkah 1 & 2", "Pilih menu CH, lalu kenali layarnya",
        "Dari Hub klik kartu Cluster Head atau tab CH.",
        "ch-01-shell",
        [
            ("1", "Badge: link serial, bridge, port, CH ID, state, parent "
                  "aktif, dan tegangan baterai."),
            ("2", "CH Settings — identitas dan konfigurasi radio."),
            ("3", "Firmware Upload — dialog flashing."),
            ("4", "Port Setup — pilih dan sambungkan COM."),
            ("5", "Lima tab: Overview, Nodes (GLD), Mesh / Parent, Log, "
                  "Expert.", "blue"),
        ],
    )

    slide_shot(
        prs, "CH · Prasyarat", "Port Setup CH",
        "Sama seperti GLD: COM harus tersambung sebelum perintah apa pun.",
        "ch-02-portsetup",
        [
            ("1", "Pilih COM milik CH dari hasil pemindaian."),
            ("2", "Atau ketik manual lalu tekan Use."),
            ("3", "Connect — baud tetap 115200."),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 3 & 4", "Firmware Upload — pilih ENV, pilih COM, klik Upload",
        "Alurnya identik dengan GLD.",
        "ch-03-fwdialog",
        [
            ("1", "Firmware environment — ch atau chFieldtest."),
            ("2", "Target COM."),
            ("3", "Reset NVS? Dicentang berarti NVS dihapus dan perangkat "
                  "boot dengan default firmware, termasuk CH ID 0010 dan "
                  "Gateway 0001."),
            ("4", "Baris status kesiapan dialog.", "blue"),
            ("5", "Klik Upload."),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 5", "Tunggu sampai upload selesai",
        "Aplikasi berpindah ke tab Log agar prosesnya terlihat.",
        "ch-04-fwprogress",
        [
            ("1", "Status berjalan: serial diputus dulu, lalu firmware "
                  "dikirim ke COM tujuan. Setelah selesai aplikasi menyambung "
                  "ulang dan menampilkan versi firmware yang terpasang."),
        ],
        note="Contoh tampilan status — proses upload sebenarnya butuh "
             "perangkat CH yang terhubung.",
    )

    slide_shot(
        prs, "CH · Langkah 6", "Overview (1/3) — keadaan dasar",
        "Refresh mengirim GET_INFO dan GET_STATUS; Start polling mengulanginya "
        "berkala.",
        "ch-05-overview-a",
        [
            ("1", "Refresh — sekali ambil."),
            ("2", "Start polling — ambil berulang."),
            ("3", "State: keadaan CH (mis. JOINED) beserta alasannya."),
            ("4", "Battery: tegangan dalam mV; badge berubah peringatan di "
                  "bawah 3150 mV."),
            ("5", "Uptime sejak boot."),
            ("6", "Nodes seen: jumlah GLD di cache, plus jumlah yang belum "
                  "terkirim."),
            ("7", "Identity: CH ID, root gateway, versi firmware/protokol, "
                  "capabilities.", "blue"),
            ("8", "Active parent: ID parent, RSSI, SNR, dan kedalaman mesh.",
             "blue"),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 6", "Overview (2/3) — keepalive, discovery, radio",
        "Kartu-kartu ini menjelaskan kenapa CH sedang dalam keadaan tersebut.",
        "ch-06-overview-b",
        [
            ("9", "CH_HELLO: hasil hello terakhir (ACK diterima / menunggu / "
                  "gagal), hitung mundur hello berikutnya, dan jumlah "
                  "kegagalan terhadap ambangnya."),
            ("10", "CH_CONFIG: hasil pencarian parent terakhir dan kejadian "
                   "berikutnya. Saat CH sudah JOINED, yang ditampilkan adalah "
                   "hitung mundur pemeriksaan kesehatan parent."),
            ("11", "STAR radio — link ke GLD. Menampilkan hasil begin(), "
                   "frekuensi, BW/SF/CR, dan sync word.", "blue"),
            ("12", "MESH radio — link ke Gateway, format sama.", "blue"),
            ("13", "Pull request dari Gateway, dilacak dalam tiga langkah.",
             "green"),
        ],
        note="Nilai STAR di sini harus sama dengan LoRa STAR di GLD, dan "
             "nilai MESH harus sama dengan MESH LoRa di Gateway.",
    )

    slide_shot(
        prs, "CH · Langkah 6", "Overview (3/3) — pull request dan tren baterai",
        "CH tidak pernah membuat pull request; CH hanya melayani atau "
        "meneruskannya.",
        "ch-07-overview-c",
        [
            ("1", "Tiga langkah: (a) permintaan diterima, (b) sedang "
                  "diproses, (c) balasan dikirim. Bila permintaan ternyata "
                  "bukan untuk CH ini, langkah 2 dan 3 ditandai dilewati dan "
                  "labelnya berubah menjadi \"Not for this CH\"."),
            ("2", "Tren baterai dari nilai CH_BATT_MV yang terkumpul selama "
                  "sesi.", "blue"),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 7", "CH Settings (1/2) — identitas",
        "Setiap Apply membuat CH melakukan reboot.",
        "ch-08-settings-a",
        [
            ("1", "CH ID, rentang 0010–0FFF."),
            ("2", "Root gateway ID, rentang 0001–000F."),
            ("3", "Apply CH ID / Apply gateway — keduanya memicu reboot."),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 7", "CH Settings (2/2) — dua radio LoRa",
        "CH memakai dua radio yang berbeda perannya.",
        "ch-09-settings-b",
        [
            ("1", "STAR radio (ke GLD): frekuensi, BW, SF, CR, sync word, TX "
                  "dBm. Harus sama dengan pengaturan LoRa STAR di setiap GLD "
                  "di klaster ini."),
            ("2", "MESH radio (ke Gateway): parameter sama, tetapi harus "
                  "cocok dengan MESH LoRa di Gateway dan seluruh CH lain."),
        ],
        note="Bagian Maintenance di bawahnya berisi RESTART, DEBUG_ON, dan "
             "DEBUG_OFF.",
    )

    slide_text(
        prs, "CH · Langkah 8", "Alur kerja CH",
        "Urutan yang biasanya diikuti saat memasang atau memeriksa satu CH.",
        [
            ("Pemasangan awal", [
                "1. Port Setup → Connect ke COM CH.",
                "2. Firmware Upload bila firmware perlu diperbarui.",
                "3. CH Settings → set CH ID dan Root gateway (CH reboot).",
                "4. CH Settings → samakan STAR LoRa dengan GLD, MESH LoRa "
                "dengan Gateway (CH reboot lagi).",
            ]),
            ("Verifikasi bergabung", [
                "5. Overview → Refresh, lalu Start polling.",
                "6. Perhatikan kartu CH_CONFIG: CH mengirim permintaan "
                "discovery selama JOINING atau PARENT_FAILOVER.",
                "7. Setelah parent terpilih, State berubah JOINED dan kartu "
                "Active parent terisi.",
                "8. Kartu CH_HELLO harus menunjukkan \"ACK received\" secara "
                "berkala.",
            ]),
            ("Verifikasi data", [
                "9. Tab Nodes → GLD yang mengirim uplink STAR akan muncul.",
                "10. Tab Mesh / Parent → periksa kandidat parent dan kualitas "
                "link.",
                "11. Saat Gateway mengirim pull request, stepper di Overview "
                "berjalan sampai \"Response sent\".",
            ]),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 9", "Nodes (GLD) — GLD yang melapor ke CH ini",
        "Isinya berasal dari NodeCache di RAM CH.",
        "ch-10-nodes",
        [
            ("1", "Refresh (GET_NODES) — minta isi cache terbaru."),
            ("2", "Kolom: Node ID, Alarm, Power, Unsent, RSSI, SNR, Last "
                  "update, Freshness.", "blue"),
            ("3", "Satu baris per GLD. \"Last update\" dihitung dari uplink "
                  "STAR terakhir; node yang lebih tua dari 300 detik ditandai "
                  "stale.", "blue"),
        ],
        note="RSSI/SNR hanya mencerminkan paket STAR terakhir dan tidak "
             "disimpan firmware — node yang belum mengirim ulang pada sesi "
             "ini tampil tanpa nilai.",
    )

    slide_shot(
        prs, "CH · Langkah 10", "Mesh / Parent — pemilihan parent",
        "Kandidat parent yang terdengar CH lewat radio MESH.",
        "ch-11-mesh",
        [
            ("1", "Send hello — memaksa satu keepalive ke parent."),
            ("2", "Clear parent NVS — menghapus parent tersimpan dan memaksa "
                  "pencarian ulang."),
            ("3", "Force failover — memicu perpindahan parent."),
            ("4", "Tabel kandidat: parent-nya sendiri, depth, RSSI, SNR, "
                  "baterai, capabilities, dan mana yang sedang aktif.",
             "blue"),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 10", "Mesh / Parent — detail pull request terakhir",
        "Rincian permintaan terakhir dari Gateway yang dilihat CH ini.",
        "ch-12-mesh-pull",
        [
            ("1", "Kapan terlihat, Request ID, status, status data, jumlah "
                  "record dan ukurannya, serta apakah balasannya diantrikan "
                  "ke parent."),
        ],
        note="MSG_SERVER_PULL_REQUEST datang lewat MESH dari Gateway root "
             "(atau diteruskan ke CH lain). CH tidak punya perintah serial "
             "untuk membuatnya sendiri.",
    )

    slide_shot(
        prs, "CH · Langkah 11", "Log CH",
        "Seluruh baris CH_* dari firmware.",
        "ch-13-log",
        [
            ("1", "Pause menahan tampilan."),
            ("2", "Download menyimpan lewat browser."),
            ("3", "Save to disk menyimpan lewat bridge."),
            ("4", "Isi log — dari sinilah semua kartu Overview, Nodes, dan "
                  "Mesh dibentuk.", "blue"),
        ],
    )

    slide_shot(
        prs, "CH · Langkah 12", "Expert Terminal CH",
        "Terkunci PIN, sama seperti di GLD.",
        "ch-14-expert",
        [
            ("1", "Unlock / Lock dengan PIN lokal."),
            ("2", "Kirim baris perintah bebas ke CH."),
            ("3", "Perintah cepat: APP_PING, GET_INFO, GET_STATUS, GET_NODES, "
                  "GET_PARENTS, DEBUG_ON, DEBUG_OFF, RESTART.", "blue"),
        ],
        note="Di bawahnya ada bagian Firmware upload versi lanjutan, untuk "
             "memuat folder paket firmware secara manual.",
    )

    # =============================================================== GATEWAY
    slide_section(
        prs, "3", "Gateway",
        "Jembatan antara mesh LoRa dan broker MQTT di sisi server.",
        [
            "Upload firmware (profil gw atau gw_hello_ack_fieldtest)",
            "Gateway Setup bertahap: COM → Wi-Fi → MQTT",
            "Overview — Wi-Fi, MQTT, antrean uplink, radio MESH",
            "Uplinks — setiap frame MESH yang diterima dan diteruskan",
            "Topology — keadaan tiap CH dan umpan event mentah",
            "Commands, Boot Log, Firmware",
        ],
    )

    slide_shot(
        prs, "GW · Langkah 1", "Pilih menu Gateway dan kenali layarnya",
        "Dari Hub klik kartu Gateway atau tab Gateway.",
        "gw-01-shell",
        [
            ("1", "Badge. Perhatikan dua badge MQTT yang berbeda: \"monitor "
                  "MQTT\" adalah koneksi PC ini ke broker, \"gateway MQTT\" "
                  "adalah koneksi perangkat Gateway ke broker yang sama."),
            ("2", "Gateway Setup — laci konfigurasi bertahap."),
            ("3", "Firmware Upload."),
            ("4", "Enam tab: Overview, Uplinks, Topology, Commands, Boot Log, "
                  "Firmware.", "blue"),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 2 & 3 & 4", "Firmware Upload — pilih COM, klik Upload",
        "Gateway tidak punya pilihan ENV di dialog ini; profilnya diatur di "
        "tab Firmware.",
        "gw-02-fwdialog",
        [
            ("1", "Target COM — port Gateway."),
            ("2", "Reset NVS? Tidak dicentang: Wi-Fi, MQTT, mesh, dan "
                  "parameter NVS lain dipertahankan. Dicentang: NVS dihapus "
                  "dan perangkat boot dengan default firmware."),
            ("3", "Baris status kesiapan.", "blue"),
            ("4", "Klik Upload."),
        ],
        note="GATEWAY_ID adalah konstanta compile-time (firmware/config/"
             "GwConfig.h) — tidak ada perintah untuk menggantinya saat "
             "runtime, berbeda dengan ID CH dan GLD.",
    )

    slide_shot(
        prs, "GW · Langkah 5", "Tunggu sampai upload selesai",
        "Serial diputus dulu, lalu firmware dikirim.",
        "gw-03-fwprogress",
        [
            ("1", "Baris status berjalan sampai flashing selesai dan koneksi "
                  "COM disambung ulang."),
        ],
        note="Contoh tampilan status — proses upload sebenarnya butuh "
             "perangkat Gateway yang terhubung.",
    )

    slide_shot(
        prs, "GW · Langkah 6", "Gateway Setup (1/3) — COM lalu Wi-Fi",
        "Setiap langkah membuka kunci langkah berikutnya. Urutannya disengaja.",
        "gw-04-setup-a",
        [
            ("1", "Langkah 1 — Gateway serial COM. Sambungkan dulu; Wi-Fi dan "
                  "MQTT tetap terkunci sampai koneksi ini berhasil."),
            ("2", "Langkah 2 — Gateway Wi-Fi. Simpan kredensial (Gateway "
                  "reboot), sambungkan ulang COM bila perlu, lalu jalankan "
                  "Test Gateway Wi-Fi. Tombol \"Use this PC Wi-Fi\" mengisi "
                  "SSID dari profil Windows yang sedang aktif.", "blue"),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 6", "Gateway Setup (2/3) — MQTT",
        "MQTT terbuka hanya setelah Gateway sendiri melaporkan alamat IP.",
        "gw-05-setup-b",
        [
            ("3", "Langkah 3 — MQTT. Broker diisi sekali, lalu dipakai dua "
                  "klien: perangkat Gateway dan monitor operator di PC ini. "
                  "Tombolnya: Save & connect Gateway, Test broker from this "
                  "PC, Connect operator monitor, Disconnect monitor."),
        ],
        note="Topic root terkunci di gld/gateway. Tombol \"Use Hub Broker\" "
             "mengisi host dengan broker yang dijalankan Hub.",
    )

    slide_shot(
        prs, "GW · Langkah 6", "Gateway Setup (3/3) — MESH LoRa",
        "Bagian ini hanya butuh COM, tidak menunggu Wi-Fi maupun MQTT.",
        "gw-06-setup-c",
        [
            ("4", "MESH LoRa: frekuensi, BW, SF, CR, sync word, TX dBm. Nilai "
                  "divalidasi, disimpan ke NVS Gateway, dibaca ulang, lalu "
                  "diterapkan setelah reboot otomatis. Semua radio MESH di "
                  "setiap CH harus memakai nilai yang sama."),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 7", "Overview (1/2) — keadaan Gateway",
        "Seluruh isi tab ini berasal dari pesan status yang diterbitkan "
        "Gateway sendiri.",
        "gw-07-overview-a",
        [
            ("1", "Refresh."),
            ("2", "State beserta Gateway ID."),
            ("3", "Last status — umur pesan status terakhir. Gateway "
                  "menerbitkannya sekitar tiap 10 detik.", "blue"),
            ("4", "WiFi / MQTT / Mesh ready.", "blue"),
            ("5", "Antrean uplink: depth, kapasitas, jumlah yang dibuang, dan "
                  "jumlah yang sudah diterbitkan.", "blue"),
            ("6", "Identity: Gateway ID, firmware, protokol, uptime, IP.",
             "green"),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 7", "Overview (2/2) — Wi-Fi, MQTT, radio MESH",
        "Rincian koneksi perangkat.",
        "gw-08-overview-b",
        [
            ("7", "Gateway Wi-Fi: SSID, kekuatan sinyal, kanal, MAC."),
            ("8", "Gateway MQTT: broker, state, autentikasi, subscription, "
                  "topic root."),
            ("9", "MESH radio: frekuensi, bandwidth, SF/CR, sync word, TX "
                  "power, preamble.", "blue"),
        ],
        note="Kalau tab ini kosong, monitor MQTT di PC belum tersambung ke "
             "broker — buka Gateway Setup langkah 3 dan tekan Connect "
             "operator monitor.",
    )

    slide_shot(
        prs, "GW · Langkah 8", "Uplinks — frame MESH yang diteruskan",
        "Setiap frame LoRa MESH yang diterima Gateway lalu diterbitkan ke "
        "MQTT, terbaru di atas.",
        "gw-09-uplinks",
        [
            ("1", "Kolom: waktu, tipe pesan, source, destination, sequence, "
                  "panjang payload, RSSI/SNR, dan status parsing.", "blue"),
            ("2", "Tipe pesan diterjemahkan dari ID protokol, mis. CH_HELLO, "
                  "SENSOR_DATA, CLUSTER_DATA_RESPONSE, SERVER_PULL_REQUEST.",
             "blue"),
            ("3", "Clear mengosongkan tabel di layar saja."),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 9", "Topology — bentuk mesh",
        "Diturunkan dari event CH_HELLO, CH_CONFIG_REQUEST, dan "
        "CH_CONFIG_RESPONSE.",
        "gw-10-topology",
        [
            ("1", "Tabel atas: keadaan terakhir yang diketahui untuk tiap CH "
                  "— parent, baterai, RSSI/SNR, jenis laporan, capabilities, "
                  "dan umur data."),
            ("2", "Tabel bawah: umpan event mentah, urut waktu.", "blue"),
        ],
        note="Baris yang lebih tua dari 300 detik ditandai sebagai stale.",
    )

    slide_shot(
        prs, "GW · Langkah 10", "Commands — perintah turun ke mesh",
        "Dua jenis perintah yang bisa dikirim operator lewat MQTT.",
        "gw-11-commands",
        [
            ("1", "Pull request → {topicRoot}/cmd/pull. Membentuk "
                  "MSG_SERVER_PULL_REQUEST, dikirim ke hop pertama atau "
                  "dirutekan berdasarkan cluster."),
            ("2", "Node command → {topicRoot}/cmd/node. Membentuk "
                  "MSG_SERVER_NODE_COMMAND untuk satu GLD di balik sebuah CH; "
                  "isi cluster, node ID, TTL, dan payload hex."),
            ("3", "Log perintah yang sudah dikirim beserta topic dan "
                  "payload-nya.", "blue"),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 11", "Boot Log dan tab Firmware",
        "Log serial 115200 baud, dan flashing versi lanjutan.",
        "gw-12-bootlog",
        [
            ("1", "Log runtime Gateway. Koneksi COM yang sama juga dipakai "
                  "alur provisioning Wi-Fi/MQTT di Gateway Setup.", "blue"),
            ("2", "Pause, Download, Save to disk, Clear."),
        ],
    )

    slide_shot(
        prs, "GW · Langkah 11", "Tab Firmware",
        "Untuk memuat folder paket firmware secara manual.",
        "gw-13-firmware",
        [
            ("1", "Lock / Unlock dengan PIN lokal."),
            ("2", "Profil firmware: gw atau gw_hello_ack_fieldtest."),
            ("3", "Choose package folder — memuat paket dari folder."),
            ("4", "Upload & flash."),
        ],
        note="Tidak ada langkah provisioning setelah flashing, karena "
             "GATEWAY_ID ditetapkan saat kompilasi.",
    )

    # ================================================================ CLOSING
    slide_text(
        prs, "Penutup", "Urutan komisioning satu klaster",
        "Ringkasan end-to-end dari perangkat kosong sampai data mengalir.",
        [
            ("A. Gateway lebih dulu", [
                "1. Flash firmware Gateway.",
                "2. Gateway Setup: COM → Wi-Fi (simpan, reboot, test) → MQTT "
                "(simpan ke perangkat, sambungkan monitor).",
                "3. Setel MESH LoRa dan catat nilainya.",
                "4. Overview harus ONLINE dengan Wi-Fi dan MQTT up.",
            ]),
            ("B. ClusterHead", [
                "5. Flash firmware CH.",
                "6. CH Settings: CH ID dan Root gateway.",
                "7. MESH LoRa CH = MESH LoRa Gateway.",
                "8. Tentukan STAR LoRa untuk klaster ini.",
                "9. Tunggu State menjadi JOINED dan CH_HELLO ber-ACK.",
                "10. Di Gateway, CH ini muncul di tab Topology.",
            ]),
            ("C. GLD", [
                "11. Flash firmware GLD.",
                "12. Running Settings: GLD ID, CH Address, LoRa STAR "
                "(= STAR LoRa CH).",
                "13. Boot Health semua siap.",
                "14. Nulling sampai seluruh kanal OK.",
                "15. QC: beri verdict tiap kanal.",
                "16. GLD muncul di tab Nodes pada CH.",
            ]),
        ],
        note="Aturan pencocokan radio: STAR menghubungkan GLD ↔ CH, MESH "
             "menghubungkan CH ↔ CH ↔ Gateway. Nilai di kedua ujung harus "
             "sama persis.",
    )

    slide_text(
        prs, "Penutup", "Kalau ada yang tidak jalan",
        "Titik pemeriksaan yang paling sering menyelesaikan masalah.",
        [
            ("Tidak bisa connect COM", [
                "• Pastikan driver CH340 terpasang (dicek preflight Hub).",
                "• Tutup aplikasi lain yang memegang port yang sama.",
                "• Coba isi COM manual di Port Setup.",
                "• Periksa badge bridge — tanpa bridge, upload firmware "
                "tidak tersedia.",
            ]),
            ("GLD tidak muncul di CH", [
                "• Samakan LoRa STAR GLD dengan STAR radio CH: frekuensi, "
                "BW, SF, CR, sync word.",
                "• Periksa CH Address di GLD menunjuk ke CH yang benar.",
                "• Di tab Nodes CH, node lebih tua dari 300 detik ditandai "
                "stale.",
            ]),
            ("CH tidak JOINED", [
                "• Samakan MESH LoRa CH dengan Gateway.",
                "• Lihat kartu CH_CONFIG: apakah discovery menemukan "
                "kandidat.",
                "• Coba Clear parent NVS lalu biarkan mencari ulang.",
                "• Periksa hasil begin() radio MESH — kode −2 berarti chip "
                "SX1262 tidak terdeteksi lewat SPI.",
            ]),
        ],
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prs.save(OUT_PPTX)
    print(f"saved {OUT_PPTX}  slides={len(prs.slides.__iter__.__self__._sldIdLst)}")


if __name__ == "__main__":
    build()
