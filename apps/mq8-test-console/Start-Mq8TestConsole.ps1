[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$port = 5188
$url = "http://127.0.0.1:$port/"
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "MQ8 Test Console sudah berjalan di $url (PID $($existing.OwningProcess))."
  Start-Process $url
  exit 0
}

$python = Get-Command python.exe -ErrorAction Stop
$bridge = Join-Path $PSScriptRoot 'bridge.py'
& $python.Source -B $bridge --host 127.0.0.1 --port $port --open-browser
