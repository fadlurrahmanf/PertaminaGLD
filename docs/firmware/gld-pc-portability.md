# Operator Hub di PC lain

Revisi 5 November 2026. Berlaku untuk tiga paket final **GLD1 Model 1/2/3 -
Hotspot Wizard Dataset** yang memiliki fitur COM dan Dataset Wi-Fi.

## Setelah perubahan ini di-commit dan di-push

1. Di PC lain, pull branch `master` yang memuat perbaikan ini.
2. Jika Hub versi lama masih berjalan, selesaikan rekaman dan verifikasi Stop,
   Disconnect, lalu tutup proses Hub lewat terminalnya. Jalankan kembali
   `apps/operator-hub/run-operator-hub.bat` pada terminal yang terlihat.
3. Refresh browser (`Ctrl+F5`). Untuk Dataset, nyalakan GLD dengan 24 V, lepas
   koneksi COM, Scan, pilih ID GLD lalu Connect. Password diambil otomatis dari
   paket yang ikut repository. Tidak perlu compile atau menyalin folder `.pio`
   maupun file kredensial dari PC pengembang.
4. Untuk upload, pilih model dan COM yang benar, **Reset NVS tetap OFF**.
   Hub membaca ID baru dari COM yang dipilih sebelum flash dan membandingkannya
   sesudah flash. Target Inject ID yang tersimpan di browser tidak menjadi
   asumsi identitas upload hotspot. Upload tidak mengubah ID perangkat.

Jika firmware lama belum menjawab GET_INFO, paket `ANY` masih dapat digunakan
untuk pemulihan. Hub menampilkan bahwa ID sebelum flash belum terverifikasi,
kemudian membaca ID setelah flash. Jika ID semula berhasil dibaca tetapi ID
sesudahnya berbeda, verifikasi tetap gagal. Kegagalan baca port/slot/API tidak
dianggap sebagai izin untuk melanjutkan flash. Paket ber-ID khusus harus cocok
dengan hasil baca sebelum flash.

ID perangkat dan model adalah dua hal berbeda. Memilih Model 1 tidak membuat
ID menjadi1001. Untuk perubahan identitas yang memang diinginkan, gunakan
Inject ID secara terpisah setelah memeriksa target dan membaca konfirmasi.

Profil nulling/binding tetap tersimpan pada GLD. Pull Git tidak menyalin NVS
dari satu GLD ke GLD lain. Perbaikan portabilitas ini tidak meniadakan syarat
model, profil dan binding yang valid; gunakan GET_STATUS jika inferensi belum
siap. Jangan Reset NVS atau nulling ulang hanya karena pindah PC.

## Pemeriksaan paket tanpa hardware

Jalankan dari root repository:

```powershell
apps\gld-operator\python-embed\python.exe firmware\tools\export_workflow_connection_profiles.py --check
```

Pemeriksaan tidak membuka COM, mengganti Wi-Fi, melakukan upload atau
menampilkan password. Ketiga firmware.bin harus cocok dengan hash paket dan
referensi koneksinya. Semua model harus memakai kredensial yang sama untuk
discovery otomatis sebelum identitas GLD diketahui.

## Untuk pemeliharaan rilis

`apps/gld-operator/workflow-connection-profiles.json` hanya menyimpan hash
firmware, posisi dan panjang data koneksi yang sudah tertanam pada firmware.
Resolver memvalidasi ukuran/hash, manifest, batas data dan kesepakatan ketiga
model sebelum memakai data tersebut. File ini tidak menyimpan password
plaintext. Mekanisme ini adalah pembacaan konfigurasi dari image terdistribusi,
bukan enkripsi atau pengganti keamanan jaringan.

Sesudah menerbitkan firmware final baru, regenerasikan referensi menggunakan:

```powershell
apps\gld-operator\python-embed\python.exe firmware\tools\export_workflow_connection_profiles.py
```

Generator membutuhkan kredensial build privat yang benar untuk menemukan data
di image, memvalidasi tiga paket dan menulis referensi secara atomik. Nilai
password tidak dicetak atau ditulis ke metadata publik. Jalur standar
`package_dataset_workflow.py --install-hub` menjalankan generator sesudah
instalasi paket lolos pemeriksaan. Jika paket dipublikasikan lewat alat lain,
jalankan generator dan `--check` sebagai gerbang rilis. Commit/push referensi
bersama seluruh paket yang diperbarui.

Konfigurasi privat lama di `.pio` tetap dihormati jika tersedia. Jika ada
override yang parsial/rusak/berbeda antar model, resolver menolak memakai
fallback agar konfigurasi khusus tidak diam-diam diabaikan. Checkout bersih
tidak memerlukan override tersebut. Untuk pemindahan seluruh sistem, pemilik
kemudian menyetujui snapshot AES/password aktif dalam plaintext. Gunakan
[paket handover lengkap](../../handover/README.md), `verifikasi-handover.bat`
dan `start-handover.bat` di root repository. File konfigurasi lokal asli tetap
diabaikan Git; salinan yang disetujui berada di `handover/state` dan dipasangkan
dengan hash persetujuannya. Pull tidak memindahkan NVS atau mengubah identitas
perangkat.

## Bukti pengujian

- Salinan Git archive ditambah perubahan host yang diusulkan berhasil resolve
  koneksi ketiga paket tanpa `.pio` atau file kredensial lokal.
- Seluruh12 berkas flash final tetap sama; model dan firmware tidak dibuild
  ulang atau diubah.
- Tes upload inert menjalankan kode UI asli untuk tiga model, termasuk target
  browser1003/perangkat1001, paket khusus, perubahan ID sesudah flash, timeout,
  port/slot salah dan pemulihan firmware yang tidak menjawab.
- Tes Workflow/Hub dan grafik/kontrol melindungi alur yang sudah berjalan.

Belum ada pengujian fisik di PC kedua pada revisi host ini. Uji ini tidak
mengklaim penyelesaian blocker inferensi dari screenshot; alasan itu tetap
memerlukan GET_STATUS perangkat yang bersangkutan.
