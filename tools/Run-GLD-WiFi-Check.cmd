@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "GLD_CHECK_ID=%~1"
if "%GLD_CHECK_ID%"=="" set /p "GLD_CHECK_ID=Masukkan ID GLD (contoh 1002): "
"%REPO_ROOT%\apps\gld-operator\python-embed\python.exe" "%~dp0diagnose_gld_wifi.py" --device-id "%GLD_CHECK_ID%"
set "CHECK_EXIT=%ERRORLEVEL%"
echo.
echo Pemeriksaan selesai. Lihat laporan di output\diagnostics.
pause
exit /b %CHECK_EXIT%
