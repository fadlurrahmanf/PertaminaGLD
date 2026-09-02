$ports = @(921600,115200,74880)
$cmds = @('GET_STATUS','VERSION','HELP','RUN_BOOT_CHECK')
foreach($port in  @("COM3")){
  foreach($baud in $ports){
    try {
      $sp = New-Object System.IO.Ports.SerialPort($port,$baud,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
      $sp.ReadTimeout = 1500
      $sp.WriteTimeout = 1500
      $sp.DtrEnable = $false
      $sp.RtsEnable = $false
      $sp.Open()
      Start-Sleep -Milliseconds 400
      $sp.DiscardInBuffer()
      Write-Output "=== PORT $port BAUD $baud OPEN" 
      $i=0
      foreach($cmd in $cmds){
        $sp.WriteLine($cmd)
        Start-Sleep -Milliseconds 300
        $lines = @()
        for($k=0;$k -lt 20;$k++){
          try{ $line = $sp.ReadLine(); if($line){$lines += $line} } catch { }
        }
        Write-Output "CMD=$cmd"
        Write-Output (($lines | Select-Object -First 12) -join "`n")
        Start-Sleep -Milliseconds 200
      }
      $sp.Close()
      break
    } catch {
      Write-Output "=== PORT $port BAUD $baud FAIL $($_.Exception.Message)"
    }
  }
}
