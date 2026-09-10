@echo off
setlocal
set "ROOT=%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\tools\start-local-nodered-mqtt.ps1"
exit /b %ERRORLEVEL%
