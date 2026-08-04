[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LiveDataPath,
    [Parameter(Mandatory = $true)][string]$ProgressPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $LiveDataPath)) { exit 0 }

function Read-SharedText([string]$Path) {
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false), $true)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}
try { $rows = @(Read-SharedText $LiveDataPath | ConvertFrom-Csv) } catch { exit 0 }
$points = @($rows | Where-Object { $_.mq8_v -ne '' -and $null -ne $_.mq8_v } | ForEach-Object {
    [pscustomobject]@{ X = [double]$_.elapsed_s; Y = 1000.0 * [double]$_.mq8_v; Duty = [double]$_.duty_pct; Phase = $_.phase }
})
if ($points.Count -lt 2) { exit 0 }

$width = 1200; $height = 620; $left = 78; $right = 32; $top = 78; $bottom = 82
$plotWidth = $width - $left - $right; $plotHeight = $height - $top - $bottom
$minX = 0.0; $maxX = [Math]::Max(60.0, $points[-1].X)
$minY = ($points | Measure-Object -Property Y -Minimum).Minimum; $maxY = ($points | Measure-Object -Property Y -Maximum).Maximum
$pad = [Math]::Max(0.1, ($maxY - $minY) * 0.1); $minY -= $pad; $maxY += $pad
if ($maxY -le $minY) { $maxY = $minY + 1.0 }
function PX([double]$x) { return $left + (($x - $minX) / ($maxX - $minX)) * $plotWidth }
function PY([double]$y) { return $top + (1.0 - (($y - $minY) / ($maxY - $minY))) * $plotHeight }

$ci = [Globalization.CultureInfo]::InvariantCulture
$polyline = ($points | ForEach-Object { '{0},{1}' -f (PX $_.X).ToString('F1',$ci), (PY $_.Y).ToString('F1',$ci) }) -join ' '
$latest = $points[-1]
$status = ''
if (Test-Path -LiteralPath $ProgressPath) { $status = (Get-Content -LiteralPath $ProgressPath -Raw) -replace '&','&amp;' -replace '<','&lt;' }
$statusLine = (($status -split "`r?`n") | Where-Object { $_ -match 'Duty aktif' } | Select-Object -First 1)
$phaseLine = (($status -split "`r?`n") | Where-Object { $_ -match 'Keterangan' } | Select-Object -First 1)

$grid = New-Object System.Text.StringBuilder
for ($i = 0; $i -le 5; $i++) {
    $x = $left + ($i / 5.0) * $plotWidth; $minutes = (($i / 5.0) * $maxX / 60.0)
    [void]$grid.Append("<line x1='$($x.ToString('F1',$ci))' y1='$top' x2='$($x.ToString('F1',$ci))' y2='$($top+$plotHeight)' stroke='#3c3526' stroke-width='1'/><text x='$($x.ToString('F1',$ci))' y='$($top+$plotHeight+30)' fill='#cfc8b8' text-anchor='middle' font-size='14'>$($minutes.ToString('F1',$ci)) min</text>")
    $y = $top + ($i / 5.0) * $plotHeight; $value = $maxY - ($i / 5.0) * ($maxY-$minY)
    [void]$grid.Append("<line x1='$left' y1='$($y.ToString('F1',$ci))' x2='$($left+$plotWidth)' y2='$($y.ToString('F1',$ci))' stroke='#3c3526' stroke-width='1'/><text x='$($left-12)' y='$(($y+5).ToString('F1',$ci))' fill='#cfc8b8' text-anchor='end' font-size='14'>$($value.ToString('F2',$ci)) mV</text>")
}

# Group by phase as well as duty: recovery-to-baseline has several 100% phases
# and each must appear as a separate boundary on the live graph.
$dutyMarks = @($points | Group-Object { "$($_.Phase)|$($_.Duty)" } | ForEach-Object { $_.Group[0] } | Sort-Object X)
$marks = foreach ($mark in $dutyMarks) { "<line x1='$((PX $mark.X).ToString('N1',[Globalization.CultureInfo]::InvariantCulture))' y1='$top' x2='$((PX $mark.X).ToString('N1',[Globalization.CultureInfo]::InvariantCulture))' y2='$($top+$plotHeight)' stroke='#f0ad4e' stroke-width='1' stroke-dasharray='5,5'/><text x='$((PX $mark.X+1).ToString('N1',[Globalization.CultureInfo]::InvariantCulture))' y='$($top+18)' fill='#f0ad4e' font-size='13'>$($mark.Phase) ($($mark.Duty)%)</text>" }
$svg = @"
<svg xmlns="http://www.w3.org/2000/svg" width="$width" height="$height" viewBox="0 0 $width $height">
<rect width="100%" height="100%" fill="#15120e"/>
<text x="$left" y="34" fill="#f5f0df" font-family="Segoe UI,Arial" font-weight="bold" font-size="25">MQ8 Hot Duty Sweep — Live</text>
<text x="$left" y="58" fill="#cfc8b8" font-family="Segoe UI,Arial" font-size="15">$statusLine | Sampel: $($points.Count) | MQ8 terakhir: $($latest.Y.ToString('N3')) mV</text>
$grid
$marks
<polyline points="$polyline" fill="none" stroke="#ffd166" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
<text x="$left" y="$($height-24)" fill="#cfc8b8" font-family="Segoe UI,Arial" font-size="14">$phaseLine — garis vertikal putus-putus = awal duty baru</text>
</svg>
"@
$temp = "$OutputPath.tmp"
[IO.File]::WriteAllText($temp, $svg, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temp -Destination $OutputPath -Force
