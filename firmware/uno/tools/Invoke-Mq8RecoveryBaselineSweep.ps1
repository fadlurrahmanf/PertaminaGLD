[CmdletBinding()]
param(
  [string]$UnoPort = 'COM5',
  [string]$GldPort = 'COM3',
  [string]$GldBridgeUrl = '',
  [ValidateRange(0, 60)][int]$MinimumMinutes = 10,
  [ValidateRange(0, 30)][int]$StableHoldMinutes = 5,
  [ValidateRange(1, 120)][double]$DirectionConfirmSeconds = 10,
  [switch]$ManualOperator,
  [switch]$AutoMode,
  [string]$ControlFile = '',
  [string]$ConfigFile = '',
  [string]$OutputDirectory = '',
  [string]$SessionStamp = '',
  [double[]]$TestDuties = @(95,90,85,80,75,70,65,60,55,50),
  [switch]$SkipBaseline,
  [ValidateRange(0, 100)][double]$FinalDutyPct = 100
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
  $root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
  $OutputDirectory = Join-Path $root 'apps\operator-hub\output\mq8-duty-cycle\hot-sweep'
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
if (($ManualOperator -or $AutoMode) -and [string]::IsNullOrWhiteSpace($ControlFile)) { $ControlFile = Join-Path $OutputDirectory "MQ8_RECOVERY_BASELINE_${stamp}_CONTROL.txt" }
$script:manualMode = -not $AutoMode
if (-not [string]::IsNullOrWhiteSpace($ControlFile)) { [IO.File]::WriteAllText($ControlFile, $(if($script:manualMode){'HOLD'}else{'AUTO'}), [Text.UTF8Encoding]::new($false)) }
$testDuties = @($TestDuties | ForEach-Object { [double]$_ })
if ($testDuties.Count -eq 0 -or @($testDuties | Where-Object { $_ -lt 0 -or $_ -gt 100 }).Count) {
  throw 'TestDuties must contain one or more duty values from 0 through 100.'
}
$phases = [System.Collections.Generic.List[object]]::new()
if (-not $SkipBaseline) { $phases.Add([pscustomobject]@{ Name='BASELINE_100'; Duty=100; Role='BASELINE' }) }
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
function Invoke-GldBridge([string]$method, [string]$path, $body = $null) {
  $headers = @{ 'X-GLD-Bridge-Token' = $script:gldBridgeToken }
  $uri = $GldBridgeUrl.TrimEnd('/') + $path
  if ($null -eq $body) { return Invoke-RestMethod -Method $method -Uri $uri -Headers $headers -ErrorAction Stop }
  return Invoke-RestMethod -Method $method -Uri $uri -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json -Compress) -ErrorAction Stop
}
function Get-Status {
  if (-not [string]::IsNullOrWhiteSpace($GldBridgeUrl)) {
    try {
      $before = Invoke-GldBridge 'GET' '/api/serial/recent?slot=1&after=0'
      $after = [int]$before.sequence
      Invoke-GldBridge 'POST' '/api/serial/write' @{ slot = 1; line = 'GET_STATUS' } | Out-Null
      $until = (Get-Date).AddSeconds(2)
      while ((Get-Date) -lt $until) {
        $recent = Invoke-GldBridge 'GET' ("/api/serial/recent?slot=1&after={0}" -f $after)
        foreach ($item in @($recent.lines)) {
          $line = [string]$item.line
          if ($line.StartsWith('GLD_STATUS_JSON ')) { try { return $line.Substring(16) | ConvertFrom-Json } catch { return $null } }
        }
        Start-Sleep -Milliseconds 120
      }
    } catch { return $null }
    return $null
  }
  $gld.DiscardInBuffer(); $gld.WriteLine('GET_STATUS'); $until=(Get-Date).AddSeconds(2)
  while ((Get-Date) -lt $until) {
    try { $line=$gld.ReadLine().Trim() } catch [System.TimeoutException] { continue }
    if ($line.StartsWith('GLD_STATUS_JSON ')) { try { return $line.Substring(16) | ConvertFrom-Json } catch { return $null } }
  }
  return $null
}
function Write-Live([System.Collections.Generic.List[string]]$rows, [switch]$UpdateChart) {
  # A chart viewer may briefly lock its snapshot. That must skip only this
  # refresh, never abort the acquisition or its final IO8 safety command.
  try { [IO.File]::WriteAllText($livePath, "timestamp_local,elapsed_s,phase,duty_pct,mq8_v,mq8_gain`r`n" + ($rows -join "`r`n"), [Text.UTF8Encoding]::new($false)) } catch { return }
  # The web console reads live.csv directly. SVG generation is intentionally
  # slower because rendering it for every sample would delay acquisition.
  if ($UpdateChart -and (Test-Path -LiteralPath $chartUpdater)) { try { & $chartUpdater -LiveDataPath $livePath -ProgressPath $progressPath -OutputPath $svgPath } catch {} }
}
function Write-Progress([string]$state, $phase, [int]$index, [int]$count, [string]$gate, [double]$span, [double]$spanLimit, [double]$trend, [double]$trendLimit, [double]$stableSeconds, [double]$phaseSeconds, [int]$lost) {
  $details = "Fase $($phase.Name) ($($phase.Role)); status=$gate; rentang 60dtk=$([Math]::Round($span,3)) mV; tren 1m=$([Math]::Round($trend,3)) mV/menit. Status mengikuti arah data terhadap sampel >=5 detik sebelumnya; arah yang belum bertahan 10 detik dinyatakan Stabil."
  $text = @"
# MQ8 Recovery-to-Baseline Sweep

- Status: **$state**
- Mulai: $($startedAt.ToString('yyyy-MM-dd HH:mm:ss zzz'))
- Duty aktif: **$($phase.Duty)%**
- Fase: **$($phase.Name)** ($($phase.Role))
- Tahap: $index dari $count
  - Status MQ8: **$gate**
  - Mode fase: **$(if($script:manualMode){'Manual — menunggu keputusan operator'}else{'Auto — minimal 10 menit + stabil 3 menit'})**
  - Durasi fase: **$([Math]::Round($phaseSeconds/60,2)) menit** / minimum $MinimumMinutes menit
  - Stabil berturut-turut: **$([Math]::Round($stableSeconds/60,2)) menit** / syarat $StableHoldMinutes menit
  - Konfirmasi arah: **$DirectionConfirmSeconds detik**
- Sampel tersimpan: $script:samples
- Streak MQ8 tidak terdeteksi: $lost / 10
- CSV gabungan: $rawPath
- CSV fase: $script:phasePath
- Ringkasan: $summaryPath
- SVG live: $svgPath
- Keterangan: $details

 $(if($script:manualMode){"Pindah fase hanya saat operator menyatakan fase stabil. File kontrol: $ControlFile (NEXT untuk lanjut, HOLD untuk tetap merekam, AUTO untuk mode otomatis, STOP untuk mengakhiri aman)."}else{"Gate pindah fase: fase minimal $MinimumMinutes menit, lalu status arah MQ8 harus Stabil selama $StableHoldMinutes menit berturut-turut. Tulis MANUAL pada file kontrol untuk kembali menunggu operator."}) Aturan status: telemetry valid/MQ8 status=0; nilai sekarang dibandingkan dengan sampel valid paling baru yang berumur minimal 5 detik. Jika arah naik atau turun belum bertahan $DirectionConfirmSeconds detik, statusnya Stabil. Arah yang bertahan >=$DirectionConfirmSeconds detik menjadi Menaik atau Menurun.
"@
  # Progress is observational only; a viewer lock must never stop the bench run.
  try { [IO.File]::WriteAllText($progressPath, $text, [Text.UTF8Encoding]::new($false)) } catch {}
}

$uno=[System.IO.Ports.SerialPort]::new($UnoPort,115200,'None',8,'One'); $gld=$null
if ([string]::IsNullOrWhiteSpace($GldBridgeUrl)) { $gld=[System.IO.Ports.SerialPort]::new($GldPort,115200,'None',8,'One'); $gld.ReadTimeout=250 }
$uno.ReadTimeout=500; $writer=$null; $samples=0; $live=[System.Collections.Generic.List[string]]::new(); $summary=[System.Collections.Generic.List[object]]::new(); $stopReason='not_started'
try {
  if (-not [string]::IsNullOrWhiteSpace($GldBridgeUrl)) { $health=Invoke-RestMethod -Method GET -Uri ($GldBridgeUrl.TrimEnd('/') + '/api/health') -ErrorAction Stop; $script:gldBridgeToken=[string]$health.csrfToken; if($script:gldBridgeToken.Length -lt 16){throw 'GLD bridge tidak memberi token API yang valid'} }
  $uno.Open(); Start-Sleep -Milliseconds 1200; $uno.DiscardInBuffer(); if($null -ne $gld){$gld.Open()}
  $writer=[IO.StreamWriter]::new($rawPath,$false,[Text.UTF8Encoding]::new($false)); $header='timestamp_local,elapsed_s,phase,role,duty_pct,on_ms,off_ms,telemetry_valid,mq8_status,mq8_v,mq135_v,mq3_v,mq5_v,mq4_v,mq7_v,mq6_v,mq2_v,status_json'; $writer.WriteLine($header)
  for ($i=0; $i -lt $phases.Count; $i++) {
    $phase=$phases[$i]; $pattern=Send-Duty $phase.Duty; $phaseStarted=Get-Date; $phasePath=Join-Path $OutputDirectory ("MQ8_RECOVERY_{0}_{1:D2}_{2}_{3}pct.csv" -f $stamp,($i+1),$phase.Name,$phase.Duty); $script:phasePath=$phasePath; $phaseWriter=[IO.StreamWriter]::new($phasePath,$false,[Text.UTF8Encoding]::new($false)); $phaseWriter.WriteLine($header)
    $points=[System.Collections.Generic.List[object]]::new(); $stableSince=$null; $directionSince=$null; $lastDirection=$null; $loss=0; $phaseSamples=0; $startMv=$null; $lastMv=$null; $span=[double]::NaN; $spanLimit=[double]::NaN; $trend=[double]::NaN; $trendLimit=[double]::NaN; $gate='Mengumpulkan'; $stableFor=0; $finished=$false
    while (-not $finished) {
      if(-not [string]::IsNullOrWhiteSpace($ConfigFile) -and (Test-Path -LiteralPath $ConfigFile)){
        try{$config=Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json;$candidate=[double]$config.directionConfirmSeconds;if($candidate -ge 1 -and $candidate -le 120){$DirectionConfirmSeconds=$candidate}}catch{}
      }
      $status=Get-Status; $now=Get-Date; $phaseSec=($now-$phaseStarted).TotalSeconds; $valid=$false; $mq8Status=255; $values=@(); $mq8=$null
      if ($null -ne $status -and $null -ne $status.telemetry) {
        $values=@($status.telemetry.sensorVoltage); $statuses=@($status.telemetry.sensorStatus); $gains=@($status.telemetry.sensorGain); $mq8Index=[array]::IndexOf([string[]]$status.telemetry.featureOrder,'MQ8')
        if ($mq8Index -ge 0 -and $mq8Index -lt $values.Count) { $mq8=$values[$mq8Index] }; if ($mq8Index -ge 0 -and $mq8Index -lt $statuses.Count) { $mq8Status=[int]$statuses[$mq8Index] }
        $valid=[bool]$status.telemetry.valid -and $null -ne $mq8 -and -not [double]::IsNaN([double]$mq8) -and -not [double]::IsInfinity([double]$mq8) -and $mq8Status -eq 0
      }
      if ($valid) {
        $loss=0; $mv=1000.0*[double]$mq8; if ($null -eq $startMv) { $startMv=$mv }; $lastMv=$mv; $points.Add([pscustomobject]@{ Sec=$phaseSec; Mv=$mv })
        # Same visible window as the Operator Running table default: 60 seconds.
        while ($points.Count -and ($phaseSec-$points[0].Sec) -gt 60) { $points.RemoveAt(0) }
        $span=($points | Measure-Object Mv -Maximum).Maximum-($points | Measure-Object Mv -Minimum).Minimum; $spanLimit=[double]::NaN
        $trendPoints=@($points | Where-Object { $_.Sec -ge ($phaseSec-60) }); if ($trendPoints.Count -ge 2) { $mins=($trendPoints[-1].Sec-$trendPoints[0].Sec)/60; $trend=if($mins -gt 0){($trendPoints[-1].Mv-$trendPoints[0].Mv)/$mins}else{0} } else { $trend=[double]::NaN }; $trendLimit=[double]::NaN
        $reference=$null; for($pointIndex=$points.Count-1;$pointIndex -ge 0;$pointIndex--){if($points[$pointIndex].Sec -le ($phaseSec-5)){$reference=$points[$pointIndex];break}}
        if($null -eq $reference){$gate='Mengumpulkan';$stableSince=$null;$stableFor=0}else{
          $direction=if($mv -gt $reference.Mv){'+'}elseif($mv -lt $reference.Mv){'-'}else{'='}
          if($null -eq $lastDirection -or $lastDirection -ne $direction){$lastDirection=$direction;$directionSince=$now}
          $directionSeconds=if($null -ne $directionSince){($now-$directionSince).TotalSeconds}else{0}
          $operatorStable=($direction -eq '=') -or $directionSeconds -lt $DirectionConfirmSeconds
          if($operatorStable){$gate='Stabil'}elseif($direction -eq '+'){$gate='Menaik'}else{$gate='Menurun'}
          if($script:manualMode){$stableSince=$null;$stableFor=0}elseif($operatorStable){
            # Stable hold begins on the first confirmed Stabil state; the ten-minute
            # duration requirement delays only phase advancement.
            if($null -eq $stableSince){$stableSince=$now};$stableFor=($now-$stableSince).TotalSeconds
            if($phaseSec -ge (60*$MinimumMinutes) -and $stableFor -ge (60*$StableHoldMinutes)){$finished=$true}
          }else{$stableSince=$null;$stableFor=0}
        }
      } else { $loss++; $stableSince=$null; $stableFor=0; $gate='Mengumpulkan'; if($loss -ge 10){throw "MQ8/telemetry gagal 10 kali pada $($phase.Name)"} }
      if ((-not [string]::IsNullOrWhiteSpace($ControlFile)) -and (Test-Path -LiteralPath $ControlFile)) {
        $manualCommand = (Get-Content -LiteralPath $ControlFile -Raw).Trim().ToUpperInvariant()
        if ($manualCommand -eq 'STOP') { throw 'Operator menghentikan sesi manual' }
        if ($manualCommand -eq 'AUTO') { $script:manualMode=$false }
        if ($manualCommand -eq 'MANUAL') { $script:manualMode=$true; [IO.File]::WriteAllText($ControlFile, 'HOLD', [Text.UTF8Encoding]::new($false)) }
        if ($manualCommand -eq 'NEXT' -and $script:manualMode) { $finished=$true; [IO.File]::WriteAllText($ControlFile, 'HOLD', [Text.UTF8Encoding]::new($false)) }
      }
      $elapsed=($now-$startedAt).TotalSeconds; $sensorText=0..7 | ForEach-Object { if($_ -lt $values.Count){Invariant $values[$_]}else{''} }; $json=if($null -ne $status){$status|ConvertTo-Json -Compress -Depth 12}else{''}; $fields=@($now.ToString('yyyy-MM-dd HH:mm:ss.fff zzz'),(Invariant $elapsed),$phase.Name,$phase.Role,$phase.Duty,$pattern.On,$pattern.Off,[int]$valid,$mq8Status)+$sensorText+@($json); $line=CsvLine $fields
      # Invalid startup/telemetry rows are excluded completely: not raw CSV, phase CSV, or live chart.
      if ($valid) {
        $writer.WriteLine($line); $phaseWriter.WriteLine($line); $writer.Flush(); $phaseWriter.Flush(); $samples++; $phaseSamples++
        $mq8Gain = if($mq8Index -ge 0 -and $mq8Index -lt $gains.Count){$gains[$mq8Index]}else{''}
        $live.Add(('"{0}","{1}","{2}","{3}","{4}","{5}"' -f $now.ToString('yyyy-MM-dd HH:mm:ss.fff zzz'),(Invariant $elapsed),$phase.Name,$phase.Duty,(Invariant $mq8),(Invariant $mq8Gain)))
      }
      Write-Progress 'RECORDING' $phase ($i+1) $phases.Count $gate $span $spanLimit $trend $trendLimit $stableFor $phaseSec $loss
      if ($valid) { Write-Live $live -UpdateChart:(($samples % 10) -eq 0) }
      Start-Sleep -Milliseconds 350
    }
    $phaseWriter.Dispose(); $summary.Add([pscustomobject]@{Phase=$phase.Name;Role=$phase.Role;DutyPct=$phase.Duty;DurationMinutes=[Math]::Round(((Get-Date)-$phaseStarted).TotalMinutes,3);Samples=$phaseSamples;OperatorDecision=$(if($script:manualMode){'OPERATOR_CONFIRMED'}else{'AUTO_GATE'});StartMq8Mv=$startMv;EndMq8Mv=$lastMv;Status=$gate;Range60sMv=$span;RangeLimitMv=$spanLimit;Trend1mMvPerMin=$trend;TrendLimitMvPerMin=$trendLimit;StableHoldSec=$stableFor;TelemetryLossStreak=$loss;PhaseCsv=$phasePath})
  }
  $summary|Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding utf8; $stopReason='recovery_sequence_complete_stable'; Write-Live $live -UpdateChart; Write-Progress 'COMPLETE' $phases[-1] $phases.Count $phases.Count 'Stabil' $span $spanLimit $trend $trendLimit $stableFor (($now-$phaseStarted).TotalSeconds) 0
} catch { $stopReason="failed_$($_.Exception.Message)"; if($phase){Write-Progress 'FAILED' $phase 0 $phases.Count $gate $span $spanLimit $trend $trendLimit $stableFor $phaseSec $loss}; throw
} finally { if($writer){$writer.Dispose()}; if($uno.IsOpen){try{$finalAck=Send-Duty $FinalDutyPct;Write-Output ("FINAL_IO8=" + $finalAck.Reply)}catch{Write-Output ("FINAL_IO8_UNCONFIRMED=" + $_.Exception.Message)};$uno.Close()}; if($null -ne $gld -and $gld.IsOpen){$gld.Close()};$uno.Dispose();if($null -ne $gld){$gld.Dispose()} }
Write-Output "STOP_REASON=$stopReason"; Write-Output "CSV=$rawPath"; Write-Output "SUMMARY=$summaryPath"; Write-Output "LIVE_DATA=$livePath"; Write-Output "LIVE_SVG=$svgPath"
