@echo off
if "%~1"=="-Z1" (
  "C:\Windows\System32\tar.exe" -tf "%~2"
  exit /b %ERRORLEVEL%
)
if "%~1"=="-p" (
  "C:\Windows\System32\tar.exe" -xOf "%~2" "%~3"
  exit /b %ERRORLEVEL%
)
echo Unsupported unzip arguments 1>&2
exit /b 2
