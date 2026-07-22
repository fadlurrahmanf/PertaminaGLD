@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY_EXE=%~dp0..\gld-operator\python-embed\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
"%PY_EXE%" bridge.py --host 127.0.0.1 --port 5173 --open-browser
endlocal
