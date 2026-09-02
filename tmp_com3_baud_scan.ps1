$baudRates = @(115200,921600,74880)
$port='COM3'
foreach($baud in $baudRates){
  Write-Output "===== BAUD $baud ====="
  $sp = New-Object System.IO.Ports.SerialPort $port,$baud,'None',8,'One'
  try {
    $sp.ReadTimeout = 800
    $sp.WriteTimeout = 800
    $sp.Open()
    Start-Sleep -Milliseconds 700
    $sp.DiscardInBuffer(); $sp.DiscardOutBuffer()
    $sp.WriteLine('GET_INFO')
    Start-Sleep -Milliseconds 500
    for($i=0;$i -lt 20;$i++){
      try { $line = $sp.ReadLine(); if($line){ Write-Output $line } }
      catch { }
    }
  } catch {
    Write-Output "OPEN_FAIL $($_.Exception.Message)"
  } finally {
    if($sp -and $sp.IsOpen){ $sp.Close() }
  }
}
