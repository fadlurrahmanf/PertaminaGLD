@echo off
setlocal
TITLE GLD Dataset - Connection Check
cd /d "%~dp0..\.."
"apps\gld-operator\python-embed\python.exe" -u "tmp\wifi-connect-audit-20261103\diagnose_local.py"
endlocal
