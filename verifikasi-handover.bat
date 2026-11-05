@echo off
chcp 65001 >nul
setlocal
title Verifikasi_Handover_GLD
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PGL_VERIFY_PYTHON=%~dp0apps\gld-operator\python-embed\python.exe"
if not exist "%PGL_VERIFY_PYTHON%" (
  echo ERROR: Runtime Python bawaan tidak ditemukan. Pull repository secara lengkap.
  pause
  exit /b 1
)
"%PGL_VERIFY_PYTHON%" -B "%~dp0tools\verify_handover.py" --repo-root "%~dp0." %*
set "PGL_VERIFY_EXIT=%ERRORLEVEL%"
title Verifikasi_Handover_GLD
echo.
echo Pemeriksaan selesai. Baca hasil dan lokasi laporan di atas.
pause
endlocal & exit /b %PGL_VERIFY_EXIT%
