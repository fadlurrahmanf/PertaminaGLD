@echo off
cd /d "%~dp0"
pio run -t upload
if errorlevel 1 (echo UPLOAD GAGAL & pause & exit /b 1)
pio device monitor
