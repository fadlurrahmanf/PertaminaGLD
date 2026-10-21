Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$outputDir = 'D:\Github\PertaminaGLD\outputs\gld1-mcp-sweep-20261020'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function Get-BridgeContext {
    $health = Invoke-RestMethod 'http://127.0.0.1:5174/api/health' -TimeoutSec 8
    return @{ Headers = @{ 'X-GLD-Bridge-Token' = [string]$health.csrfToken } }
}

function Get-RecentLines($headers) {
    return Invoke-RestMethod 'http://127.0.0.1:5174/api/serial/recent' -Headers $headers -TimeoutSec 20
}

function Send-Line($headers, [string]$line) {
    $body = @{ line = $line; slot = 1 } | ConvertTo-Json
    Invoke-RestMethod 'http://127.0.0.1:5174/api/serial/write' -Method POST -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 15 | Out-Null
}

$ctx = Get-BridgeContext
$headers = $ctx.Headers
$status = Invoke-RestMethod 'http://127.0.0.1:5174/api/serial/status' -Headers $headers -TimeoutSec 8
if (-not $status.connected -or $status.port -ne 'COM7') { throw 'COM7 bridge is not connected' }

$all = @()
$summary = @()
$stopCodeByChannel = @(560, 650, 900, 880, 820, 1050, 880, 100)
for ($channel = 0; $channel -lt 8; $channel++) {
    $before = Get-RecentLines $headers
    $lastSequence = [int]$before.sequence
    $rows = @()
    $baselineRows = @()
    $cancelSent = $false
    $completed = $false
    $deadline = (Get-Date).AddSeconds(($stopCodeByChannel[$channel] * 0.22) + 45)
    Send-Line $headers ('RUN_FULLSCALE_SWEEP_JSON {{"channel":{0}}}' -f $channel)

    while (-not $completed) {
        if ((Get-Date) -gt $deadline) { throw "sweep timeout channel=$channel" }
        Start-Sleep -Milliseconds 750
        $recent = Get-RecentLines $headers
        $newLines = @($recent.lines | Where-Object { [int]$_.sequence -gt $lastSequence })
        foreach ($entry in $newLines) {
            $line = [string]$entry.line
            if ($line -match '^FULLSCALE_STEP ch=(\d+) sensor=([^ ]+) code=(\d+) voltage=([-+0-9.Ee]+) valid=(\d+) write=(\d+)$') {
                if ([int]$matches[1] -ne $channel) { continue }
                $row = [pscustomobject]@{
                    channel = $channel
                    sensor = $matches[2]
                    dacCode = [int]$matches[3]
                    voltageV = [double]$matches[4]
                    valid = ([int]$matches[5] -eq 1)
                    writeOk = ([int]$matches[6] -eq 1)
                    crossing = $false
                }
                $rows += $row
                if ($row.dacCode -le 10 -and $row.valid -and $row.writeOk) { $baselineRows += $row }
                if ($row.dacCode -ge $stopCodeByChannel[$channel] -and -not $cancelSent) {
                    Send-Line $headers 'CANCEL_FULLSCALE_SWEEP'
                    $cancelSent = $true
                }
            }
            if (($line -match '^FULLSCALE_(CANCELLED|DONE) ch=(\d+)') -and [int]$matches[2] -eq $channel) {
                $completed = $true
            }
        }
        $lastSequence = [int]$recent.sequence
    }

    if ($rows.Count -eq 0) { throw "no sweep points channel=$channel" }
    $sensor = $rows[0].sensor
    $baseline = if ($baselineRows.Count -eq 11) { ($baselineRows | Measure-Object -Property voltageV -Average).Average } else { $null }
    $target = if ($null -ne $baseline) { $baseline + [math]::Max([math]::Abs($baseline) * 0.5, 0.00001) } else { $null }
    $cross = @()
    if ($null -ne $target) {
        $cross = @($rows | Where-Object { $_.valid -and $_.writeOk -and $_.dacCode -gt 10 -and $_.voltageV -ge $target } | Select-Object -First 1)
        if ($cross.Count) { $cross[0].crossing = $true }
    }
    $summary += [pscustomobject]@{
        channel = $channel; sensor = $sensor; pointCount = $rows.Count; baselineV = $baseline; targetV = $target
        firstCrossingCode = if ($cross.Count) { $cross[0].dacCode } else { $null }
        firstCrossingV = if ($cross.Count) { $cross[0].voltageV } else { $null }
    }
    $all += $rows
}

$all | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 "$outputDir\sweep-points.json"
$summary | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 "$outputDir\sweep-summary.json"
$summary | ConvertTo-Csv -NoTypeInformation | Set-Content -Encoding utf8 "$outputDir\sweep-summary.csv"
$summary | ConvertTo-Json -Depth 3
