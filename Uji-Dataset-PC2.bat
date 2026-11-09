@echo off
chcp 65001 >nul
setlocal
title Uji Dataset GLD - PC kedua
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PGL_PYTHON=%~dp0apps\gld-operator\python-embed\python.exe"
set "GLD_CHECK_ID=%~1"
if "%GLD_CHECK_ID%"=="" set "GLD_CHECK_ID=1002"

echo UJI DATASET DI PC KEDUA - GLD %GLD_CHECK_ID%
echo Jalankan setelah git pull saat PC masih memiliki Internet.
echo Commit yang sedang diuji:
git rev-parse --short HEAD
echo.
if not exist "%PGL_PYTHON%" (
  echo GAGAL: runtime Python bawaan tidak ditemukan. Pull repository secara lengkap.
  pause
  exit /b 1
)

echo [1/3] Memverifikasi stack dan histori pada salinan bersih...
"%PGL_PYTHON%" -B "%~dp0tools\verify_handover.py" --repo-root "%~dp0."
if errorlevel 1 (
  echo.
  echo GAGAL: verifikasi handover belum lulus. Kirim report.json dari output\handover-verification.
  pause
  exit /b 1
)

echo.
echo [2/3] Sambungkan PC ini ke GLD-DATASET-%GLD_CHECK_ID%.
echo Pastikan GLD tetap menyala dengan 24 V dan PC pertama sudah melepas hotspot.
echo Hotspot GLD tidak menyediakan Internet; laporan disimpan lokal.
echo Pastikan Hub di PC ini belum merekam, lalu tekan tombol apa saja.
pause >nul
"%PGL_PYTHON%" -B "%~dp0tools\diagnose_gld_wifi.py" --device-id "%GLD_CHECK_ID%" --wait-seconds 60
if errorlevel 1 (
  echo.
  echo GAGAL: koneksi hotspot/protokol belum lulus. Kirim JSON dari output\diagnostics.
  pause
  exit /b 1
)

echo.
echo [3/3] Diagnostik lulus. Membuka Operator Hub di terminal ini...
echo Buka http://127.0.0.1:5173/ di browser Codex pada PC ini.
echo Di Dataset: Scan, pilih GLD-%GLD_CHECK_ID%, Connect, pilih CSV, Lock, Start, lalu Stop.
echo Periksa 8 sensor, interval sekitar 500 ms dan file CSV. PIN Operator: 1234.
echo Hasil fungsi nyata baru lulus setelah CSV diverifikasi pada PC ini.
echo.
call "%~dp0start-handover.bat" --no-browser
set "PGL_HUB_EXIT=%ERRORLEVEL%"
echo.
echo Kirim report.json dari output\handover-verification dan JSON dari output\diagnostics.
echo Sertakan CSV hasil rekaman atau jumlah baris setelah Stop.
if not "%PGL_HUB_EXIT%"=="0" pause
endlocal & exit /b %PGL_HUB_EXIT%
