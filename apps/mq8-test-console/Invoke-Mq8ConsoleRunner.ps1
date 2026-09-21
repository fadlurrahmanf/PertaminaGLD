[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$SessionStamp,
  [Parameter(Mandatory = $true)][string]$OutputDirectory,
  [ValidateSet('manual','auto')][string]$StartMode = 'manual',
  [ValidateRange(1,120)][double]$DirectionConfirmSeconds = 10,
  [string]$ConfigFile = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$runner = Join-Path $repoRoot 'firmware\uno\tools\Invoke-Mq8RecoveryBaselineSweep.ps1'

# The GLD bridge owns COM3. Splatting guarantees that this value reaches the
# runner as a named parameter; the console must never open COM3 directly.
$runnerParameters = @{
  UnoPort = 'COM5'
  GldBridgeUrl = 'http://127.0.0.1:5174'
  ManualOperator = ($StartMode -eq 'manual')
  AutoMode = ($StartMode -eq 'auto')
  MinimumMinutes = 10
  StableHoldMinutes = 3
  DirectionConfirmSeconds = $DirectionConfirmSeconds
  ConfigFile = $ConfigFile
  OutputDirectory = $OutputDirectory
  SessionStamp = $SessionStamp
  TestDuties = @(15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95)
}
Write-Output "MQ8_CONSOLE_GLD_BRIDGE=$($runnerParameters.GldBridgeUrl)"
& $runner @runnerParameters

exit $LASTEXITCODE
