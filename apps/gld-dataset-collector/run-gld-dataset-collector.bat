@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
python server.py --host 127.0.0.1 --port 8081
endlocal
