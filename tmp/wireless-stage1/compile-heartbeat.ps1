param([string]$Note = 'Three isolated builds active; monitor compiler diagnostics')
$tracker = 'D:/Github/PertaminaGLD/docs/GLD-WIRELESS-DATASET-GOAL-TRACKER.md'
$now = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'SE Asia Standard Time')
$value = Get-Content -LiteralPath $tracker -Raw
$value = $value -replace 'Last tracker heartbeat: .*', ('Last tracker heartbeat: '+$now.ToString('yyyy-MM-dd HH:mm:ss')+' Asia/Jakarta')
$value = [regex]::Replace($value, '\| (GLD_Agent|Server_Agent|Integration_Agent) \| (4\.1 Compile Model[123] hotspot) \| ([^|]+) \| [^|]+ \| ([^|]+) \| ([^|]+) \|', {
    param($m)
    $started = [DateTime]::ParseExact(($m.Groups[3].Value.Trim() -replace ' Asia/Jakarta$', ''), 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
    return '| '+$m.Groups[1].Value+' | '+$m.Groups[2].Value+' | '+$m.Groups[3].Value.Trim()+' | '+($now-$started).ToString('hh\:mm\:ss')+' | '+$m.Groups[4].Value.Trim()+' | '+$Note+' |'
})
Set-Content -LiteralPath $tracker -Value $value
