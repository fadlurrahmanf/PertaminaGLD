@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY_EXE=%~dp0python-embed\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
"%PY_EXE%" bridge.py --host 127.0.0.1 --port 5174 --mqtt-broker-host 0.0.0.0 --mqtt-broker-port 1884 --mqtt-broker-user pgl_operator --mqtt-broker-password xw2O0FyNgJP96V5IFZYQ0Vtwho0Eu97V
endlocal
