param(
    [int]$MqttPort = 1884,
    [int]$NodeRedPort = 1880,
    [int]$StartupTimeoutSec = 45
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot "apps\runtime\local-mqtt"
$BrokerScript = Join-Path $RepoRoot "tools\local_mqtt_broker.py"
$CredentialsPath = Join-Path $RuntimeDir "credentials.local.json"
$StatusPath = Join-Path $RuntimeDir "status.local.json"
$FlowApplyScript = Join-Path $RepoRoot "server\nodered\apply-pertamina-gld-flow.js"
$NodeRedUserDir = Join-Path $env:USERPROFILE ".node-red"

function Wait-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName $HostName -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-LocalBrokerStatus() {
    if (-not (Test-Path -LiteralPath $StatusPath)) { return $null }
    try {
        $status = Get-Content -Raw -LiteralPath $StatusPath | ConvertFrom-Json
        if (-not $status.running -or -not $status.pid) { return $null }
        $process = Get-Process -Id ([int]$status.pid) -ErrorAction SilentlyContinue
        $listener = Get-NetTCPConnection -State Listen -LocalPort $MqttPort -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq [int]$status.pid } | Select-Object -First 1
        if ($process -and $listener) { return $status }
    } catch {
    }
    return $null
}

function Get-PythonExe() {
    $embedded = Join-Path $RepoRoot "apps\gld-operator\python-embed\python.exe"
    if (Test-Path -LiteralPath $embedded) { return $embedded }
    return (Get-Command python -ErrorAction Stop).Source
}

if (-not (Get-LocalBrokerStatus)) {
    $conflict = Get-NetTCPConnection -State Listen -LocalPort $MqttPort -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conflict) {
        throw "Port $MqttPort already belongs to PID $($conflict.OwningProcess), not to the portable local broker. Stop that process or choose another port."
    }
    $pythonExe = Get-PythonExe
    Start-Process -FilePath $pythonExe -ArgumentList @($BrokerScript, "--host", "127.0.0.1", "--port", "$MqttPort", "--credentials-file", $CredentialsPath, "--status-file", $StatusPath) -WorkingDirectory $RepoRoot -WindowStyle Hidden
    if (-not (Wait-TcpPort "127.0.0.1" $MqttPort $StartupTimeoutSec)) {
        throw "Local MQTT broker did not listen on 127.0.0.1:$MqttPort."
    }
}

$broker = Get-LocalBrokerStatus
if (-not $broker) { throw "Local MQTT broker status could not be verified." }
if (-not (Test-Path -LiteralPath $CredentialsPath)) { throw "Local MQTT credentials were not created." }
$credentials = Get-Content -Raw -LiteralPath $CredentialsPath | ConvertFrom-Json
if (-not $credentials.username -or -not $credentials.password) { throw "Local MQTT credentials are incomplete." }

$nodeRedListener = Get-NetTCPConnection -State Listen -LocalPort $NodeRedPort -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nodeRedListener) {
    $nodeRedCommand = (Get-Command "node-red.cmd" -ErrorAction Stop).Source
    Start-Process -FilePath $nodeRedCommand -WorkingDirectory (Join-Path $RepoRoot "server\nodered") -WindowStyle Hidden
    if (-not (Wait-TcpPort "127.0.0.1" $NodeRedPort $StartupTimeoutSec)) {
        throw "Node-RED did not listen on 127.0.0.1:$NodeRedPort."
    }
}

$nodeExe = (Get-Command node -ErrorAction Stop).Source
$previousMqttUser = $env:MQTT_USER
$previousMqttPass = $env:MQTT_PASS
try {
    $env:MQTT_USER = [string]$credentials.username
    $env:MQTT_PASS = [string]$credentials.password
    & $nodeExe $FlowApplyScript "--no-write-flow" "--node-red-url" "http://127.0.0.1:$NodeRedPort" "--node-red-user-dir" $NodeRedUserDir "--mqtt-host" "127.0.0.1" "--mqtt-port" "$MqttPort"
    if ($LASTEXITCODE -ne 0) { throw "Node-RED flow apply failed with exit code $LASTEXITCODE." }
} finally {
    $env:MQTT_USER = $previousMqttUser
    $env:MQTT_PASS = $previousMqttPass
}

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    $status = Get-LocalBrokerStatus
    if ($status -and @($status.clients) -contains "node-red-pertamina-gld") {
        Write-Host "READY MQTT=127.0.0.1:$MqttPort NodeRED=http://127.0.0.1:$NodeRedPort client=node-red-pertamina-gld"
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
throw "Node-RED is running, but the local broker did not record MQTT CONNECT from node-red-pertamina-gld."
