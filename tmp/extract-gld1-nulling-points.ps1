$ErrorActionPreference = 'Stop'
$outputDir = 'D:\Github\PertaminaGLD\outputs\gld1-mcp-sweep-20261020'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$health = Invoke-RestMethod 'http://127.0.0.1:5174/api/health' -TimeoutSec 8
$headers = @{ 'X-GLD-Bridge-Token' = [string]$health.csrfToken }
$recent = Invoke-RestMethod 'http://127.0.0.1:5174/api/serial/recent' -Headers $headers -TimeoutSec 20
$start = 6304
$end = 6759
$points = @()
foreach ($entry in $recent.lines) {
    $sequence = [int]$entry.sequence
    if ($sequence -lt $start -or $sequence -gt $end) { continue }
    $line = [string]$entry.line
    $phase = $null
    $target = $null
    $validFlag = $false
    if ($line -match '^NULLING_BASELINE_STEP ch=(\d+) sensor=(\S+) code=(\d+) voltage=([-+0-9.Ee]+) valid=(\d+) samples=(\d+)$') {
        $phase = 'Baseline'; $sampleCount = [int]$matches[6]; $validFlag = ([int]$matches[5] -eq 1)
    } elseif ($line -match '^NULLING_EXP_STEP ch=(\d+) sensor=(\S+) code=(\d+) voltage=([-+0-9.Ee]+) target=([-+0-9.Ee]+) valid=(\d+)$') {
        $phase = 'Exponential'; $sampleCount = 8; $target = [double]$matches[5]; $validFlag = ([int]$matches[6] -eq 1)
    } elseif ($line -match '^NULLING_BIN_STEP ch=(\d+) sensor=(\S+) code=(\d+) voltage=([-+0-9.Ee]+) target=([-+0-9.Ee]+) valid=(\d+)$') {
        $phase = 'Binary'; $sampleCount = 8; $target = [double]$matches[5]; $validFlag = ([int]$matches[6] -eq 1)
    } elseif ($line -match '^NULLING_CONFIRM_STEP ch=(\d+) sensor=(\S+) code=(\d+) voltage=([-+0-9.Ee]+) target=([-+0-9.Ee]+) valid=(\d+)$') {
        $phase = 'Confirm'; $sampleCount = 10; $target = [double]$matches[5]; $validFlag = ([int]$matches[6] -eq 1)
    } else { continue }
    $points += [pscustomobject]@{
        sequence = $sequence
        channel = [int]$matches[1]
        sensor = $matches[2]
        phase = $phase
        dacCode = [int]$matches[3]
        voltageV = [double]$matches[4]
        targetV = if ($null -ne $target) { $target } else { $null }
        valid = $validFlag
        sampleCount = $sampleCount
    }
}
$points | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 "$outputDir\nulling-measured-points.json"
$points.Count
