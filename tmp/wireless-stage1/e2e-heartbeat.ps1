param([string]$Action = 'Preparing isolated PC simulation and browser QA')
$trackerPath = 'D:/Github/PertaminaGLD/docs/GLD-WIRELESS-DATASET-GOAL-TRACKER.md'
$now = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'SE Asia Standard Time')
$text = Get-Content -LiteralPath $trackerPath -Raw
$text = $text -replace 'Last tracker heartbeat: .*', ('Last tracker heartbeat: '+$now.ToString('yyyy-MM-dd HH:mm:ss')+' Asia/Jakarta')
$text = [regex]::Replace($text, '\| Root \| (3\.2 Codex browser end-to-end QA) \| ([^|]+) \| [^|]+ \|([^|]+)\|[^|]+\|', {
    param($m)
    $start = [DateTime]::ParseExact(($m.Groups[2].Value.Trim() -replace ' Asia/Jakarta$', ''), 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
    return '| Root | '+$m.Groups[1].Value+' | '+$m.Groups[2].Value.Trim()+' | '+($now-$start).ToString('hh\:mm\:ss')+' |'+$m.Groups[3].Value+'| '+$Action+' |'
})
Set-Content -LiteralPath $trackerPath -Value $text
