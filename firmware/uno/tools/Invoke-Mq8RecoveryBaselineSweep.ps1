[CmdletBinding()]
param(
  [string]$UnoPort = 'COM5',
  [string]$GldPort = 'COM3',
  [ValidateRange(0, 60)][int]$MinimumMinutes = 0,
  [ValidateRange(0, 30)][int]$StableHoldMinutes = 0,
  [string]$OutputDirectory = '',
  [string]$SessionStamp = '',
  [ValidateRange(0, 100)][double]$FinalDutyPct = 100
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
  $root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
  $OutputDirectory = Join-Path $root 'apps\operator-hub\output\mq8-duty-cycle\recovery-baseline'
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$startedAt = Get-Date
$stamp = if ($SessionStamp) { $SessionStamp } else { $startedAt.ToString('yyyyMMdd_HHmmss') }
$rawPath = Join-Path $OutputDirectory "MQ8_RECOVERY_BASELINE_$stamp.csv"
$summaryPath = Join-Path $OutputDirectory "MQ8_RECOVERY_BASELINE_${stamp}_summary.csv"
$livePath = Join-Path $OutputDirectory "MQ8_RECOVERY_BASELINE_${stamp}_live.csv"
$progressPath = Join-Path $OutputDirectory 'HOT_DUTY_SWEEP_PROGRESS.md'
$svgPath = Join-Path $OutputDirectory 'HOT_DUTY_SWEEP_LIVE.svg'
$chartUpdater = Join-Path $PSScriptRoot 'Update-HotDutySweepLiveChart.ps1'
$testDuties = @(95,90,85,80,75,70,65,60,55,50)
$phases = [System.Collections.Generic.List[object]]::new()
$phases.Add([pscustomobject]@{ Name='BASELINE_100'; Duty=100; Role='BASELINE' })
foreach ($duty in $testDuties) {
  $phases.Add([pscustomobject]@{ Name=("TEST_{0}" -f $duty); Duty=$duty; Role='TEST' })
  if ($duty -ne $testDuties[-1]) { $phases.Add([pscustomobject]@{ Name=("RECOVERY_100_AFTER_{0}" -f $duty); Duty=100; Role='RECOVERY' }) }
}

function Invariant([object]$v) { if ($null -eq $v) { return '' }; return ([double]$v).ToString('R',[Globalization.CultureInfo]::InvariantCulture) }
function CsvLine([object[]]$items) { return (($items | ForEach-Object { '"' + ([string]$_ -replace '"','""') + '"' }) -join ',') }
function Send-Duty([double]$duty) {
  $on = [int][Math]::Round($duty * 10.0, 0, [MidpointRounding]::AwayFromZero); $off = 1000 - $on
  $uno.DiscardInBuffer(); $uno.WriteLine("$on,$off"); Start-Sleep -Milliseconds 160
  $reply = $uno.ReadExisting().Trim()
  if ($reply -notmatch 'DUTY onMs=') { throw "UNO tidak mengonfirmasi $duty%: $reply" }
  return [pscustomobject]@{ On=$on; Off=$off; Reply=$reply }
}
function Get-Status {
  $gld.DiscardInBuffer(); $gld.WriteLine('GET_STATUS'); $until=(Get-Date).AddSeconds(2)
  while ((Get-Date) -lt $until) {
    try { $line=$gld.ReadLine().Trim() } catch [System.TimeoutException] { continue }
    if ($line.StartsWith('GLD_STATUS_JSON ')) { try { return $line.Substring(16) | ConvertFrom-Json } catch { return $null } }
  }
  return $null
}
function Write-Live([System.Collections.Generic.List[string]]$rows) {
  # A chart viewer may briefly lock its snapshot. That must skip only this
  # refresh, never abort the acquisition or its final IO8 safety command.
  try { [IO.File]::WriteAllText($livePath, "timestamp_local,elapsed_s,phase,duty_pct,mq8_v`r`n" + ($rows -join "`r`n"), [Text.UTF8Encoding]::new($false)) } catch { return }
  if (Test-Path -LiteralPath $chartUpdater) { try { & $chartUpdater -LiveDataPath $livePath -ProgressPath $progressPath -OutputPath $svgPath } catch {} }
}
function Write-Progress([string]$state, $phase, [int]$index, [int]$count, [string]$gate, [double]$span, [double]$spanLimit, [double]$trend, [double]$trendLimit, [double]$stableSeconds, [int]$lost) {
  $details = "Fase $($phase.Name) ($($phase.Role)); gate=$gate; rentang 60dtk=$([Math]::Round($span,3))/$([Math]::Round($spanLimit,3)) mV; tren 1m=$([Math]::Round($trend,3))/$([Math]::Round($trendLimit,3)) mV/menit; evaluasi mengikuti tabel Operator."
  $text = @"
# MQ8 Recovery-to-Baseline Sweep

- Status: **$state**
- Mulai: $($startedAt.ToString('yyyy-MM-dd HH:mm:ss zzz'))
- Duty aktif: **$($phase.Duty)%**
- Fase: **$($phase.Name)** ($($phase.Role))
- Tahap: $index dari $count
- Status MQ8: **$gate**
- Sampel tersimpan: $script:samples
- Streak MQ8 tidak terdeteksi: $lost / 10
- CSV gabungan: $rawPath
- CSV fase: $script:phasePath
- Ringkasan: $summaryPath
- SVG live: $svgPath
- Keterangan: $details

Gate pindah fase mengikuti evaluasi stabilitas tabel Operator pada range default 60 detik: minimal 5 sampel; telemetry valid/MQ8 status=0; rentang <= max(0,20 mV; 1,5% |MQ8|); |tren 1m| <= max(0,10 mV/menit; 0,6% |MQ8|). Status tabel arah 5 detik tidak dipakai sebagai gate.
"@
  # Progress is observational only; a viewer lock must never stop the bench run.
  try { [IO.File]::WriteAllText($progressPath, $text, [Text.UTF8Encoding]::new($false)) } catch {}
}

$uno=[System.IO.Ports.SerialPort]::new($UnoPort,115200,'None',8,'One'); $gld=[System.IO.Ports.SerialPort]::new($GldPort,115200,'None',8,'One')
$uno.ReadTimeout=500; $gld.ReadTimeout=250; $writer=$null; $samples=0; $live=[System.Collections.Generic.List[string]]::new(); $summary=[System.Collections.Generic.List[object]]::new(); $stopReason='not_started'
try {
  $uno.Open(); Start-Sleep -Milliseconds 1200; $uno.DiscardInBuffer(); $gld.Open()
  $writer=[IO.StreamWriter]::new($rawPath,$false,[Text.UTF8Encoding]::new($false)); $header='timestamp_local,elapsed_s,phase,role,duty_pct,on_ms,off_ms,telemetry_valid,mq8_status,mq8_v,mq135_v,mq3_v,mq5_v,mq4_v,mq7_v,mq6_v,mq2_v,status_json'; $writer.WriteLine($header)
  for ($i=0; $i -lt $phases.Count; $i++) {
    $phase=$phases[$i]; $pattern=Send-Duty $phase.Duty; $phaseStarted=Get-Date; $phasePath=Join-Path $OutputDirectory ("MQ8_RECOVERY_{0}_{1:D2}_{2}_{3}pct.csv" -f $stamp,($i+1),$phase.Name,$phase.Duty); $script:phasePath=$phasePath; $phaseWriter=[IO.StreamWriter]::new($phasePath,$false,[Text.UTF8Encoding]::new($false)); $phaseWriter.WriteLine($header)
    $points=[System.Collections.Generic.List[object]]::new(); $stableSince=$null; $loss=0; $phaseSamples=0; $startMv=$null; $lastMv=$null; $span=[double]::NaN; $spanLimit=[double]::NaN; $trend=[double]::NaN; $trendLimit=[double]::NaN; $gate='Mengumpulkan'; $finished=$false
    while (-not $finished) {
      $status=Get-Status; $now=Get-Date; $phaseSec=($now-$phaseStarted).TotalSeconds; $valid=$false; $mq8Status=255; $values=@(); $mq8=$null
      if ($null -ne $status -and $null -ne $status.telemetry) {
        $values=@($status.telemetry.sensorVoltage); $statuses=@($status.telemetry.sensorStatus); $mq8Index=[array]::IndexOf([string[]]$status.telemetry.featureOrder,'MQ8')
        if ($mq8Index -ge 0 -and $mq8Index -lt $values.Count) { $mq8=$values[$mq8Index] }; if ($mq8Index -ge 0 -and $mq8Index -lt $statuses.Count) { $mq8Status=[int]$statuses[$mq8Index] }
        $valid=[bool]$status.telemetry.valid -and $null -ne $mq8 -and -not [double]::IsNaN([double]$mq8) -and -not [double]::IsInfinity([double]$mq8) -and $mq8Status -eq 0
      }
      if ($valid) {
        $loss=0; $mv=1000.0*[double]$mq8; if ($null -eq $startMv) { $startMv=$mv }; $lastMv=$mv; $points.Add([pscustomobject]@{ Sec=$phaseSec; Mv=$mv })
        # Same visible window as the Operator Running table default: 60 seconds.
        while ($points.Count -and ($phaseSec-$points[0].Sec) -gt 60) { $points.RemoveAt(0) }
        $span=($points | Measure-Object Mv -Maximum).Maximum-($points | Measure-Object Mv -Minimum).Minimum; $spanLimit=[Math]::Max(0.20,[Math]::Abs($mv)*0.015)
        $trendPoints=@($points | Where-Object { $_.Sec -ge ($phaseSec-60) }); if ($trendPoints.Count -ge 2) { $mins=($trendPoints[-1].Sec-$trendPoints[0].Sec)/60; $trend=if($mins -gt 0){($trendPoints[-1].Mv-$trendPoints[0].Mv)/$mins}else{0} } else { $trend=[double]::NaN }; $trendLimit=[Math]::Max(0.10,[Math]::Abs($mv)*0.006)
        $operatorStable=$points.Count -ge 5 -and $span -le $spanLimit -and [Math]::Abs($trend) -le $trendLimit
        if ($operatorStable) { $stableSince=$now; $stableFor=0; $gate='Stabil'; $finished=$true }
        else { $stableSince=$null; $stableFor=0; if($points.Count -lt 5 -or [double]::IsNaN($trend) -or [double]::IsInfinity($trend)){$gate='Mengumpulkan'}elseif($span -le (3*$spanLimit) -and [Math]::Abs($trend) -le (3*$trendLimit)){$gate='Bergerak'}else{$gate='Fluktuatif'} }
      } else { $loss++; $stableSince=$null; $stableFor=0; $gate='Mengumpulkan'; if($loss -ge 10){throw "MQ8/telemetry gagal 10 kali pada $($phase.Name)"} }
      $elapsed=($now-$startedAt).TotalSeconds; $sensorText=0..7 | ForEach-Object { if($_ -lt $values.Count){Invariant $values[$_]}else{''} }; $json=if($null -ne $status){$status|ConvertTo-Json -Compress -Depth 12}else{''}; $fields=@($now.ToString('yyyy-MM-dd HH:mm:ss.fff zzz'),(Invariant $elapsed),$phase.Name,$phase.Role,$phase.Duty,$pattern.On,$pattern.Off,[int]$valid,$mq8Status)+$sensorText+@($json); $line=CsvLine $fields
      $writer.WriteLine($line); $phaseWriter.WriteLine($line); $writer.Flush(); $phaseWriter.Flush(); $samples++; $phaseSamples++; $live.Add(('"{0}","{1}","{2}","{3}","{4}"' -f $now.ToString('yyyy-MM-dd HH:mm:ss.fff zzz'),(Invariant $elapsed),$phase.Name,$phase.Duty,(Invariant $mq8)))
      Write-Progress 'RECORDING' $phase ($i+1) $phases.Count $gate $span $spanLimit $trend $trendLimit $stableFor $loss; if(($samples%10)-eq 0){Write-Live $live}; Start-Sleep -Milliseconds 350
    }
    $phaseWriter.Dispose(); $summary.Add([pscustomobject]@{Phase=$phase.Name;Role=$phase.Role;DutyPct=$phase.Duty;DurationMinutes=[Math]::Round(((Get-Date)-$phaseStarted).TotalMinutes,3);Samples=$phaseSamples;StartMq8Mv=$startMv;EndMq8Mv=$lastMv;Status=$gate;Range5mMv=$span;RangeLimitMv=$spanLimit;Trend1mMvPerMin=$trend;TrendLimitMvPerMin=$trendLimit;StableHoldSec=$stableFor;TelemetryLossStreak=$loss;PhaseCsv=$phasePath})
  }
  $summary|Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding utf8; $stopReason='recovery_sequence_complete_stable'; Write-Live $live; Write-Progress 'COMPLETE' $phases[-1] $phases.Count $phases.Count 'Stabil' $span $spanLimit $trend $trendLimit $stableFor 0
} catch { $stopReason="failed_$($_.Exception.Message)"; if($phase){Write-Progress 'FAILED' $phase 0 $phases.Count $gate $span $spanLimit $trend $trendLimit $stableFor $loss}; throw
} finally { if($writer){$writer.Dispose()}; if($uno.IsOpen){try{Send-Duty $FinalDutyPct|Out-Null}catch{};$uno.Close()}; if($gld.IsOpen){$gld.Close()};$uno.Dispose();$gld.Dispose() }
Write-Output "STOP_REASON=$stopReason"; Write-Output "CSV=$rawPath"; Write-Output "SUMMARY=$summaryPath"; Write-Output "LIVE_DATA=$livePath"; Write-Output "LIVE_SVG=$svgPath"
