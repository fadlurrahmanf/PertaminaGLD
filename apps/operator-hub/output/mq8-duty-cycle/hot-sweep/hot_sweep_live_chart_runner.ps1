$ErrorActionPreference='SilentlyContinue'
while ($true) {
  & 'D:\Github\PertaminaGLD\firmware\uno\tools\Update-HotDutySweepLiveChart.ps1' -LiveDataPath 'D:\Github\PertaminaGLD\apps\operator-hub\output\mq8-duty-cycle\hot-sweep\HOT_DUTY_SWEEP_20260730_141100_live.csv' -ProgressPath 'D:\Github\PertaminaGLD\apps\operator-hub\output\mq8-duty-cycle\hot-sweep\HOT_DUTY_SWEEP_PROGRESS.md' -OutputPath 'D:\Github\PertaminaGLD\apps\operator-hub\output\mq8-duty-cycle\hot-sweep\HOT_DUTY_SWEEP_LIVE.svg'
  $text = if (Test-Path -LiteralPath 'D:\Github\PertaminaGLD\apps\operator-hub\output\mq8-duty-cycle\hot-sweep\HOT_DUTY_SWEEP_PROGRESS.md') { Get-Content -LiteralPath 'D:\Github\PertaminaGLD\apps\operator-hub\output\mq8-duty-cycle\hot-sweep\HOT_DUTY_SWEEP_PROGRESS.md' -Raw } else { '' }
  if ($text -match 'Status: \*\*(COMPLETE|FAILED)') { break }
  Start-Sleep -Seconds 10
}
