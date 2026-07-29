[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$CsvPath,

    [ValidateRange(1, 600)]
    [int]$BinSeconds = 30
)

$ErrorActionPreference = 'Stop'
$source = Import-Csv -LiteralPath $CsvPath
$valid = foreach ($row in $source) {
    $elapsed = 0.0
    $mq8 = 0.0
    if ([double]::TryParse($row.elapsed_s, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$elapsed) -and
        [double]::TryParse($row.mq8_v, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$mq8)) {
        [pscustomobject]@{ elapsed_s = $elapsed; mq8_v = $mq8 }
    }
}
if (@($valid).Count -eq 0) { throw 'Tidak ada sampel MQ8 valid dalam CSV.' }

$groups = $valid | Group-Object { [Math]::Floor($_.elapsed_s / $BinSeconds) }
$summary = foreach ($group in $groups) {
    $values = @($group.Group | ForEach-Object { $_.mq8_v })
    $mean = ($values | Measure-Object -Average).Average
    $min = ($values | Measure-Object -Minimum).Minimum
    $max = ($values | Measure-Object -Maximum).Maximum
    [pscustomobject]@{
        bin_start_s = [int]$group.Name * $BinSeconds
        bin_end_s = ([int]$group.Name + 1) * $BinSeconds
        sample_count = $values.Count
        mq8_mean_v = $mean.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
        mq8_min_v = $min.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
        mq8_max_v = $max.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
        mq8_range_v = ($max - $min).ToString('R', [Globalization.CultureInfo]::InvariantCulture)
    }
}

$previousMean = $null
foreach ($row in $summary) {
    $mean = [double]::Parse($row.mq8_mean_v, [Globalization.CultureInfo]::InvariantCulture)
    if ($null -eq $previousMean) {
        $row | Add-Member -NotePropertyName mq8_mean_delta_v -NotePropertyValue ''
        $row | Add-Member -NotePropertyName slope_v_per_min -NotePropertyValue ''
    } else {
        $delta = $mean - $previousMean
        $row | Add-Member -NotePropertyName mq8_mean_delta_v -NotePropertyValue $delta.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
        $row | Add-Member -NotePropertyName slope_v_per_min -NotePropertyValue (($delta * 60.0 / $BinSeconds).ToString('R', [Globalization.CultureInfo]::InvariantCulture))
    }
    $previousMean = $mean
}

$directory = Split-Path -Parent $CsvPath
$baseName = [IO.Path]::GetFileNameWithoutExtension($CsvPath)
$outputPath = Join-Path $directory ("{0}_{1}s_summary.csv" -f $baseName, $BinSeconds)
$summary | Export-Csv -LiteralPath $outputPath -NoTypeInformation -Encoding utf8
Write-Output "SUMMARY=$outputPath"
