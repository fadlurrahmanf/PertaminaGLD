$port = 'COM3'
$baud = 921600
$cmds = @('GET_STATUS','VERSION','RUN_BOOT_CHECK','RUN_CURRENT_STATE_CHECK','RUN_TCA_CHANNEL_SCAN','RUN_I2C_SCAN')
$results = @{}
for($iter=1;$iter -le 5;$iter++){
  Write-Output "ITER=$iter"
  $sp = New-Object System.IO.Ports.SerialPort $port,$baud,'None',8,'One'
  try {
    $sp.ReadTimeout = 2500
    $sp.WriteTimeout = 2500
    $sp.DtrEnable = $false
    $sp.RtsEnable = $false
    $sp.Open()
    Start-Sleep -Milliseconds 400
    $sp.DiscardInBuffer()
    foreach($cmd in $cmds){
      $sp.WriteLine($cmd)
      Start-Sleep -Milliseconds 250
      $lines = @()
      $end = (Get-Date).AddSeconds(4)
      while((Get-Date) -lt $end){
        try {
          $line = $sp.ReadLine()
          if($line -ne $null -and $line -ne ''){ $lines += $line }
          if($line -like '*DONE*' -or $line -like 'BOOT_RECOVERY_ARM*' -or $line -like 'RUN_'+$cmd.replace(' ','')+'*'){ }
        } catch { }
      }
      Write-Output "  CMD=$cmd"
      if($lines.Count -eq 0){ Write-Output '    <no lines>'; }
      else {
        $lines | Select-Object -First 25 | ForEach-Object { Write-Output ("    $_") }
      }
    }
  } catch {
    Write-Output "FAILED OPEN $($_.Exception.Message)"
  } finally {
    if($sp -and $sp.IsOpen){ $sp.Close() }
  }
}
