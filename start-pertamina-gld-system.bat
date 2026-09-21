@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-pertamina-gld-system.ps1" %*
set "PGL_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %PGL_EXIT_CODE%
