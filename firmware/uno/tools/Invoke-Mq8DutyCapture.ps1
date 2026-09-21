[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$SessionName,

    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 60000)]
    [int]$OnMs,

    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 60000)]
    [int]$OffMs,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 180)]
    [int]$DurationMinutes,

    [string]$UnoPort = 'COM5',
    [string]$GldPort = 'COM3',
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
    $OutputDirectory = Join-Path $repositoryRoot 'apps\operator-hub\output\mq8-duty-cycle'
}

if ($OnMs -eq 0 -and $OffMs -eq 0) {
    throw 'ONms dan OFFms tidak boleh keduanya 0.'
}

function Write-ProgressFile {
    param(
        [string]$State,
        [datetime]$StartedAt,
        [datetime]$TargetAt,
        [int]$SampleCount,
        [string]$CsvPath,
        [string]$Detail
    )

    $now = Get-Date
    $remainingSeconds = [Math]::Max(0, [int][Math]::Ceiling(($TargetAt - $now).TotalSeconds))
    $elapsedSeconds = [Math]::Max(0, [int][Math]::Floor(($now - $StartedAt).TotalSeconds))
    $percent = if ($TargetAt -gt $StartedAt) {
        [Math]::Min(100, [Math]::Round(100 * ($elapsedSeconds / ($TargetAt - $StartedAt).TotalSeconds), 1))
    } else { 100 }
    $dutyPct = [Math]::Round(100 * $OnMs / ($OnMs + $OffMs), 3)
    $content = @"
# MQ8 Duty-cycle Test Progress

- Status: **$State**
- Sesi: **$SessionName**
- Mulai: $($StartedAt.ToString('yyyy-MM-dd HH:mm:ss zzz'))
- Target rekam: $($TargetAt.ToString('yyyy-MM-dd HH:mm:ss zzz'))
- Berjalan: $elapsedSeconds detik
- Sisa countdown: $remainingSeconds detik
- Progress sesi: $percent%
- Pola Uno: $($OnMs),$($OffMs) ($dutyPct%)
- Sampel GLD tersimpan: $SampleCount
- CSV aktif: $CsvPath
- Keterangan: $Detail

Catatan: ETA ini hanya untuk sesi perekaman aktif. ETA matriks keseluruhan baru dihitung setelah baseline dan siklus heating/cooldown pertama memiliki durasi nyata.
"@
    # The status file may be open in Explorer/Markdown preview. Its display must
    # never abort a live hardware recording, so retry briefly then continue.
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Set-Content -LiteralPath $script:ProgressPath -Value $content -Encoding utf8
            return
        } catch [System.IO.IOException] {
            if ($attempt -eq 5) { return }
            Start-Sleep -Milliseconds 200
        }
    }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$script:ProgressPath = Join-Path $OutputDirectory 'MQ8_TEST_PROGRESS.md'
$startedAt = Get-Date
$targetAt = $startedAt.AddMinutes($DurationMinutes)
$stamp = $startedAt.ToString('yyyyMMdd_HHmmss')
$csvPath = Join-Path $OutputDirectory ("{0}_{1}.csv" -f $SessionName, $stamp)
$dutyPct = [Math]::Round(100 * $OnMs / ($OnMs + $OffMs), 3)

$uno = [System.IO.Ports.SerialPort]::new($UnoPort, 115200, 'None', 8, 'One')
$gld = [System.IO.Ports.SerialPort]::new($GldPort, 115200, 'None', 8, 'One')
$uno.ReadTimeout = 500
$gld.ReadTimeout = 250
$sampleCount = 0

try {
    $uno.Open()
    $uno.DiscardInBuffer()
    $uno.WriteLine("$OnMs,$OffMs")
    Start-Sleep -Milliseconds 150
    $unoReply = $uno.ReadExisting().Trim()
    if ($unoReply -notmatch 'DUTY onMs=') {
        throw "UNO tidak mengonfirmasi duty. Respons: $unoReply"
    }

    $gld.Open()
    $writer = [System.IO.StreamWriter]::new($csvPath, $false, [System.Text.UTF8Encoding]::new($false))
    $writer.WriteLine('timestamp_local,elapsed_s,session_name,on_ms,off_ms,duty_pct,mq8_v,status_json')
    Write-ProgressFile -State 'RECORDING' -StartedAt $startedAt -TargetAt $targetAt -SampleCount $sampleCount -CsvPath $csvPath -Detail 'Uno dan GLD terhubung; perekaman berjalan.'

    while ((Get-Date) -lt $targetAt) {
        $gld.DiscardInBuffer()
        $gld.WriteLine('GET_STATUS')
        $deadline = (Get-Date).AddSeconds(2)
        $status = $null
        while ((Get-Date) -lt $deadline -and $null -eq $status) {
            try { $line = $gld.ReadLine().Trim() } catch [System.TimeoutException] { continue }
            if ($line.StartsWith('GLD_STATUS_JSON ')) {
                try { $status = $line.Substring(16) | ConvertFrom-Json } catch { $status = $null }
            }
        }
        if ($null -ne $status) {
            $mq8 = $null
            # GLD status keeps values in telemetry.sensorVoltage, ordered by telemetry.featureOrder.
            if ($null -ne $status.telemetry -and $null -ne $status.telemetry.sensorVoltage -and $null -ne $status.telemetry.featureOrder) {
                $mq8Index = [array]::IndexOf([string[]]$status.telemetry.featureOrder, 'MQ8')
                if ($mq8Index -ge 0 -and $mq8Index -lt $status.telemetry.sensorVoltage.Count) {
                    $mq8 = $status.telemetry.sensorVoltage[$mq8Index]
                }
            }
            $elapsed = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)
            $jsonCompact = $status | ConvertTo-Json -Compress -Depth 12
            $mq8Text = ''
            if ($null -ne $mq8) {
                $mq8Text = ([double]$mq8).ToString('R', [Globalization.CultureInfo]::InvariantCulture)
            }
            $fields = @(
                (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff zzz'),
                $elapsed.ToString([Globalization.CultureInfo]::InvariantCulture),
                $SessionName,
                $OnMs,
                $OffMs,
                $dutyPct.ToString([Globalization.CultureInfo]::InvariantCulture),
                $mq8Text,
                $jsonCompact
            )
            $writer.WriteLine(($fields | ForEach-Object { '"' + ([string]$_ -replace '"', '""') + '"' }) -join ',')
            $writer.Flush()
            $sampleCount++
        }
        Write-ProgressFile -State 'RECORDING' -StartedAt $startedAt -TargetAt $targetAt -SampleCount $sampleCount -CsvPath $csvPath -Detail 'Mengambil GET_STATUS dari GLD; nilai MQ8 tersimpan bila respons valid.'
        Start-Sleep -Milliseconds 300
    }
    Write-ProgressFile -State 'FINALIZING' -StartedAt $startedAt -TargetAt $targetAt -SampleCount $sampleCount -CsvPath $csvPath -Detail 'Perekaman selesai; IO8 sedang dikembalikan ke LOW.'
}
catch {
    Write-ProgressFile -State 'FAILED' -StartedAt $startedAt -TargetAt $targetAt -SampleCount $sampleCount -CsvPath $csvPath -Detail $_.Exception.Message
    throw
}
finally {
    if ($null -ne $writer) { $writer.Dispose() }
    if ($uno.IsOpen) {
        try { $uno.WriteLine('0,1000'); Start-Sleep -Milliseconds 100 } catch {}
        $uno.Close()
    }
    if ($gld.IsOpen) { $gld.Close() }
    $uno.Dispose()
    $gld.Dispose()
    if ($sampleCount -gt 0) {
        Write-ProgressFile -State 'COMPLETE_IO8_LOW' -StartedAt $startedAt -TargetAt $targetAt -SampleCount $sampleCount -CsvPath $csvPath -Detail 'CSV tertutup dan Uno telah diperintahkan `0,1000`.'
    }
}

Write-Output "CSV=$csvPath"
Write-Output "SAMPLES=$sampleCount"
