@echo off
setlocal
cd /d "%~dp0"
python bridge.py --host 127.0.0.1 --port 5173
endlocal
