param([string]$Action = 'Implement additive UI/API; firmware and collector workers active')
$trackerPath = 'D:/Github/PertaminaGLD/docs/GLD-WIRELESS-DATASET-GOAL-TRACKER.md'
$now = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'SE Asia Standard Time')
$content = Get-Content -LiteralPath $trackerPath -Raw
$content = $content -replace 'Last tracker heartbeat: .*', ('Last tracker heartbeat: ' + $now.ToString('yyyy-MM-dd HH:mm:ss') + ' Asia/Jakarta')
$content = $content -replace '\| Root \| 3.2 Additive wireless controls and eight-channel chart.*', ('| Root | 3.2 Additive wireless controls and eight-channel chart | 2026-11-02 12:28 Asia/Jakarta | ' + ($now - [DateTime]'2026-11-02 12:28').ToString('hh\:mm\:ss') + ' | 10% | ' + $Action + ' |')
Set-Content -LiteralPath $trackerPath -Value $content
