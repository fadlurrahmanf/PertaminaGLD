[CmdletBinding()]
param(
    [string]$UnoPort = 'COM5',
    [string]$GldPort = 'COM3',
    [ValidateRange(1, 15)][int]$BaselineMinutes = 3,
    [ValidateRange(1, 15)][int]$StepMinutes = 5,
    [ValidateRange(1, 25)][int]$StepPercent = 5,
    [string]$OutputDirectory = '',
    [string]$SessionStamp = ''
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
    $OutputDirectory = Join-Path $repositoryRoot 'apps\operator-hub\output\mq8-duty-cycle\hot-sweep'
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$startedAt = Get-Date
$stamp = if ([string]::IsNullOrWhiteSpace($SessionStamp)) { $startedAt.ToString('yyyyMMdd_HHmmss') } else { $SessionStamp }
$csvPath = Join-Path $OutputDirectory ("HOT_DUTY_SWEEP_{0}.csv" -f $stamp)
$summaryPath = Join-Path $OutputDirectory ("HOT_DUTY_SWEEP_{0}_summary.csv" -f $stamp)
$liveDataPath = Join-Path $OutputDirectory ("HOT_DUTY_SWEEP_{0}_live.csv" -f $stamp)
$progressPath = Join-Path $OutputDirectory 'HOT_DUTY_SWEEP_PROGRESS.md'
$stopReason = 'not_started'
$samples = 0
$summaryRows = New-Object System.Collections.Generic.List[object]

function Write-Progress {
    param([string]$State, [string]$Detail, [int]$Duty, [int]$StepIndex, [int]$TotalSteps, [int]$FailStreak)
    $content = @"
# MQ8 Hot Duty Sweep

- Status: **$State**
- Mulai: $($startedAt.ToString('yyyy-MM-dd HH:mm:ss zzz'))
- Duty aktif: **$Duty%**
- Tahap: $StepIndex dari $TotalSteps
- Durasi baseline: $BaselineMinutes menit; durasi per step: $StepMinutes menit; langkah: $StepPercent%
- Sampel tersimpan: $samples
- Streak MQ8 tidak terdeteksi: $FailStreak / 10
- CSV raw: $csvPath
- Ringkasan: $summaryPath
- Keterangan: $Detail

Kriteria berhenti: MQ8 hilang/tidak-finite, sensorStatus MQ8 bukan 0, atau telemetry.valid=false selama 10 respons berturut-turut.
"@
    try { Set-Content -LiteralPath $progressPath -Value $content -Encoding utf8 } catch {}
}

function Send-Duty {
    param([int]$Duty)
    $onMs = [int]($Duty * 10)
    $offMs = [int](1000 - $onMs)
    $command = ('{0},{1}' -f $onMs, $offMs)
    $uno.DiscardInBuffer()
    $uno.WriteLine($command)
    Start-Sleep -Milliseconds 160
    $reply = $uno.ReadExisting().Trim()
    if ($reply -notmatch 'DUTY onMs=') { throw "UNO tidak mengonfirmasi duty $Duty%: $reply" }
    return @{ On = $onMs; Off = $offMs; Reply = $reply }
}

function Get-Status {
    $gld.DiscardInBuffer()
    $gld.WriteLine('GET_STATUS')
    $deadline = (Get-Date).AddSeconds(2)
    while ((Get-Date) -lt $deadline) {
        try { $line = $gld.ReadLine().Trim() } catch [System.TimeoutException] { continue }
        if ($line.StartsWith('GLD_STATUS_JSON ')) {
            try { return ($line.Substring(16) | ConvertFrom-Json) } catch { return $null }
        }
    }
    return $null
}

function InvariantText { param($Value) if ($null -eq $Value) { return '' }; return ([double]$Value).ToString('R', [Globalization.CultureInfo]::InvariantCulture) }

function Write-LiveData {
    param([System.Collections.Generic.List[string]]$Rows)
    # The live graph reads this separate snapshot only. It never opens the raw
    # recording file, so visualisation cannot lock or interrupt acquisition.
    $snapshot = "timestamp_local,elapsed_s,phase,duty_pct,mq8_v`r`n" + ($Rows -join "`r`n")
    [IO.File]::WriteAllText($liveDataPath, $snapshot, [Text.UTF8Encoding]::new($false))
}

$uno = [System.IO.Ports.SerialPort]::new($UnoPort, 115200, 'None', 8, 'One')
$gld = [System.IO.Ports.SerialPort]::new($GldPort, 115200, 'None', 8, 'One')
$uno.ReadTimeout = 500
$gld.ReadTimeout = 250

try {
    $uno.Open(); $gld.Open()
    $writer = [System.IO.StreamWriter]::new($csvPath, $false, [Text.UTF8Encoding]::new($false))
    $writer.WriteLine('timestamp_local,elapsed_s,phase,duty_pct,on_ms,off_ms,telemetry_valid,mq8_status,mq8_v,mq135_v,mq3_v,mq5_v,mq4_v,mq7_v,mq6_v,mq2_v,status_json')
    $liveRows = [System.Collections.Generic.List[string]]::new()
    $duties = @(100) + (95..0 | Where-Object { $_ % $StepPercent -eq 0 })
    $totalSteps = $duties.Count
    $lost = $false

    for ($index = 0; $index -lt $duties.Count -and -not $lost; $index++) {
        $duty = [int]$duties[$index]
        $pattern = Send-Duty -Duty $duty
        $phase = if ($index -eq 0) { 'HOT_BASELINE_100' } else { "HOT_SWEEP_$duty" }
        $minutes = if ($index -eq 0) { $BaselineMinutes } else { $StepMinutes }
        $until = (Get-Date).AddMinutes($minutes)
        $phaseSamples = 0; $validMq8Samples = 0; $lossStreak = 0
        $startMq8 = $null; $endMq8 = $null
        Write-Progress -State 'RECORDING' -Detail "$phase selama $minutes menit." -Duty $duty -StepIndex ($index + 1) -TotalSteps $totalSteps -FailStreak $lossStreak

        while ((Get-Date) -lt $until -and -not $lost) {
            $status = Get-Status
            if ($null -ne $status) {
                $telemetry = $status.telemetry
                $values = @(); $statuses = @(); $mq8Index = -1
                if ($null -ne $telemetry) {
                    $values = @($telemetry.sensorVoltage)
                    $statuses = @($telemetry.sensorStatus)
                    $mq8Index = [array]::IndexOf([string[]]$telemetry.featureOrder, 'MQ8')
                }
                $mq8 = if ($mq8Index -ge 0 -and $mq8Index -lt $values.Count) { $values[$mq8Index] } else { $null }
                $mq8Status = if ($mq8Index -ge 0 -and $mq8Index -lt $statuses.Count) { [int]$statuses[$mq8Index] } else { 255 }
                $telemetryValid = ($null -ne $telemetry -and [bool]$telemetry.valid)
                $mq8Finite = $null -ne $mq8 -and -not [double]::IsNaN([double]$mq8) -and -not [double]::IsInfinity([double]$mq8)
                $mq8Detected = $telemetryValid -and $mq8Finite -and $mq8Status -eq 0
                if ($mq8Detected) { $lossStreak = 0; $validMq8Samples++; if ($null -eq $startMq8) { $startMq8 = [double]$mq8 }; $endMq8 = [double]$mq8 } else { $lossStreak++ }
                $elapsed = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)
                $json = $status | ConvertTo-Json -Compress -Depth 12
                $sensorText = 0..7 | ForEach-Object { if ($_ -lt $values.Count) { InvariantText $values[$_] } else { '' } }
                $fields = @((Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff zzz'), $elapsed.ToString([Globalization.CultureInfo]::InvariantCulture), $phase, $duty, $pattern.On, $pattern.Off, [int]$telemetryValid, $mq8Status) + $sensorText + @($json)
                $writer.WriteLine(($fields | ForEach-Object { '"' + ([string]$_ -replace '"', '""') + '"' }) -join ',')
                $writer.Flush(); $samples++; $phaseSamples++
                $liveRows.Add(('"{0}","{1}","{2}","{3}","{4}"' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff zzz'), $elapsed.ToString([Globalization.CultureInfo]::InvariantCulture), $phase, $duty, (InvariantText $mq8)))
                if (($samples % 10) -eq 0) { try { Write-LiveData -Rows $liveRows } catch {} }
                if ($lossStreak -ge 10) { $lost = $true; $stopReason = "mq8_not_detected_at_${duty}pct" }
            }
            Write-Progress -State 'RECORDING' -Detail "$phase; perekaman aktif." -Duty $duty -StepIndex ($index + 1) -TotalSteps $totalSteps -FailStreak $lossStreak
            Start-Sleep -Milliseconds 350
        }
        $summaryRows.Add([pscustomobject]@{ DutyPct=$duty; Phase=$phase; DurationMinutes=$minutes; Samples=$phaseSamples; ValidMq8Samples=$validMq8Samples; StartMq8V=$startMq8; EndMq8V=$endMq8; LossStreak=$lossStreak; DetectionLost=$lost })
    }
    if (-not $lost) { $stopReason = 'reached_0pct_without_telemetry_loss' }
    $summaryRows | Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding utf8
    try { Write-LiveData -Rows $liveRows } catch {}
    Write-Progress -State 'COMPLETE' -Detail $stopReason -Duty 0 -StepIndex $totalSteps -TotalSteps $totalSteps -FailStreak 0
}
catch {
    $stopReason = "failed_$($_.Exception.Message)"
    Write-Progress -State 'FAILED' -Detail $_.Exception.Message -Duty 0 -StepIndex 0 -TotalSteps 0 -FailStreak 0
    throw
}
finally {
    if ($null -ne $writer) { $writer.Dispose() }
    if ($uno.IsOpen) { try { $uno.WriteLine('0,1000'); Start-Sleep -Milliseconds 100 } catch {}; $uno.Close() }
    if ($gld.IsOpen) { $gld.Close() }
    $uno.Dispose(); $gld.Dispose()
}

Write-Output "STOP_REASON=$stopReason"
Write-Output "CSV=$csvPath"
Write-Output "SUMMARY=$summaryPath"
Write-Output "LIVE_DATA=$liveDataPath"
