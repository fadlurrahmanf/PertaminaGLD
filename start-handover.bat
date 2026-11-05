@echo off
setlocal
title Pertamina GLD - Full Handover
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0apps\gld-operator\python-embed\python.exe" "%~dp0tools\handover_stack.py" %*
set "HANDOVER_EXIT=%ERRORLEVEL%"
if not "%HANDOVER_EXIT%"=="0" pause
endlocal & exit /b %HANDOVER_EXIT%
