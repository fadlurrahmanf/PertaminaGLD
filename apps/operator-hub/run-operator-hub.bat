@echo off
setlocal
title Operator_Hub
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY_EXE=%~dp0..\gld-operator\python-embed\python.exe"
if not exist "%PY_EXE%" (
  echo ERROR: Bundled Operator Python was not found:
  echo        "%PY_EXE%"
  echo Operator Hub was not started. Do not fall back to system Python because it may not include pyserial.
  pause
  exit /b 1
)

"%PY_EXE%" -c "import serial; print('OPERATOR_RUNTIME_OK pyserial=' + getattr(serial, '__version__', 'unknown'))"
if errorlevel 1 (
  echo ERROR: The bundled Operator Python cannot import pyserial.
  echo Operator Hub was not started, so it cannot show a misleading bridge status.
  pause
  exit /b 1
)

echo Starting Operator Hub and verified GLD/CH/Gateway bridges...
"%PY_EXE%" bridge.py --host 127.0.0.1 --port 5173 --open-browser
endlocal
