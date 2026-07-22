@echo off
setlocal
cd /d "%~dp0"
call "%~dp0..\operator-hub\run-operator-hub.bat"
endlocal
