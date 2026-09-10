@echo off
setlocal
set "ROOT=%~dp0.."
set "PY_EXE=%ROOT%\apps\gld-operator\python-embed\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
"%PY_EXE%" "%ROOT%\tools\local_mqtt_broker.py" --host 127.0.0.1 --port 1884
endlocal
