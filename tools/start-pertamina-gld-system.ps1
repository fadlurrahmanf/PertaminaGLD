param(
    [string]$NodeRedUrl = "http://127.0.0.1:1880",
    [string]$NodeRedUserDir = "$env:USERPROFILE\.node-red",
    [int]$StartupTimeoutSec = 60,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$NodeRedDir = Join-Path $RepoRoot "server\nodered"
$OperatorHubDir = Join-Path $RepoRoot "apps\operator-hub"
$CredentialsPath = Join-Path $RepoRoot "apps\runtime\operator-hub\credentials.local.json"
$NodeRedEnvPath = Join-Path $NodeRedDir ".env"

function Write-Step([string]$Message) {
    Write-Host "[Pertamina GLD] $Message"
}

function Test-Listening([int]$Port) {
    try {
        return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Wait-Port([int]$Port, [string]$Name, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Listening $Port) {
            Write-Step "$Name is listening on port $Port"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Warning "$Name did not start listening on port $Port within $TimeoutSec seconds"
    return $false
}

function Load-DotEnv([string]$Path) {
    if (-not (Test-Path $Path)) {
        Write-Step "server\nodered\.env not found; continuing without extra Node-RED env secrets"
        return
    }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $idx = $trimmed.IndexOf("=")
        if ($idx -le 0) {
            continue
        }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
        if ($key) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Step "Loaded server\nodered\.env into this startup session"
}

function Start-OperatorHub() {
    if (Test-Listening 5173) {
        Write-Step "Operator Hub already running"
        return
    }
    $bat = Join-Path $OperatorHubDir "run-operator-hub.bat"
    Write-Step "Starting Operator Hub"
    Start-Process -FilePath $bat -WorkingDirectory $OperatorHubDir -WindowStyle Hidden
    Wait-Port 5173 "Operator Hub" $StartupTimeoutSec | Out-Null
}

function Start-NodeRed() {
    if (Test-Listening 1880) {
        Write-Step "Node-RED already running"
        return
    }
    Write-Step "Starting Node-RED"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "node-red" -WorkingDirectory $NodeRedDir -WindowStyle Hidden
    Wait-Port 1880 "Node-RED" $StartupTimeoutSec | Out-Null
}

function Wait-BrokerCredentials() {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Test-Path $CredentialsPath) -and (Test-Listening 1884)) {
            $broker = Get-Content -Raw $CredentialsPath | ConvertFrom-Json
            if ($broker.host -and $broker.port -and $broker.username -and $broker.password) {
                Write-Step "MQTT broker ready at $($broker.host):$($broker.port)"
                return $broker
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "MQTT broker credentials/listener were not ready. Start Operator Hub and check apps\runtime\operator-hub\credentials.local.json."
}

function Apply-NodeRedFlow($Broker) {
    Write-Step "Applying Node-RED flow with current Operator Hub MQTT credentials"
    $args = @(
        (Join-Path $NodeRedDir "apply-pertamina-gld-flow.js"),
        "--node-red-url", $NodeRedUrl,
        "--node-red-user-dir", $NodeRedUserDir,
        "--gateway-status-url", "http://0.0.0.0/disabled-until-gateway-ip-known",
        "--gateway-base-url", "http://0.0.0.0",
        "--mqtt-host", [string]$Broker.host,
        "--mqtt-port", [string]$Broker.port,
        "--mqtt-user", [string]$Broker.username,
        "--mqtt-password", [string]$Broker.password,
        "--allow-insecure-mqtt"
    )
    if ($env:GLD_KEY_ID) {
        $args += @("--gld-key-id", [string]$env:GLD_KEY_ID)
    }
    if ($env:GLD_AES128_KEY_HEX) {
        $args += @("--gld-aes128-key-hex", [string]$env:GLD_AES128_KEY_HEX)
    }
    if ($env:PGL_GLD_TARGET_CH_MAP_JSON) {
        $args += @("--gld-target-ch-map-json", [string]$env:PGL_GLD_TARGET_CH_MAP_JSON)
    }
    if ($env:PGL_COMMAND_AUTH_TOKEN) {
        $args += @("--command-auth-token", [string]$env:PGL_COMMAND_AUTH_TOKEN)
    }
    & node @args
    if ($LASTEXITCODE -ne 0) {
        throw "Node-RED flow apply failed with exit code $LASTEXITCODE"
    }
}

function Connect-GatewayOperatorMonitor($Broker) {
    if (-not (Wait-Port 5373 "Gateway Operator" 15)) {
        Write-Warning "Gateway Operator is not available; MQTT monitor was not connected"
        return
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:5373/api/health" -TimeoutSec 5
        $headers = @{ "X-GW-Bridge-Token" = $health.csrfToken }
        try {
            Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5373/api/mqtt/disconnect" -Headers $headers -ContentType "application/json" -Body "{}" -TimeoutSec 3 | Out-Null
        } catch {
        }
        $body = @{
            host = [string]$Broker.host
            port = [int]$Broker.port
            username = [string]$Broker.username
            password = [string]$Broker.password
            topicRoot = [string]$Broker.topicRoot
        } | ConvertTo-Json -Depth 5
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5373/api/mqtt/connect" -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec 8 | Out-Null
        Write-Step "Gateway Operator MQTT monitor connected"
    } catch {
        Write-Warning "Gateway Operator MQTT monitor connect failed: $($_.Exception.Message)"
    }
}

function Wait-Topology() {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        try {
            $topology = Invoke-RestMethod -Uri "$NodeRedUrl/pertamina-gld/topology" -TimeoutSec 5
            if ($topology.gatewayIds -and $topology.gatewayIds.Count -gt 0) {
                Write-Step "Topology ready: $($topology.gatewayIds.Count) GW, $($topology.nodeCount) node"
                return $true
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }
    Write-Warning "Topology endpoint is reachable but has no GW yet. Check GW Wi-Fi/MQTT or wait for the next gateway status/topology publish."
    return $false
}

Write-Step "Starting system from $RepoRoot"
Start-OperatorHub
$broker = Wait-BrokerCredentials
Load-DotEnv $NodeRedEnvPath
Start-NodeRed
Apply-NodeRedFlow $broker
Connect-GatewayOperatorMonitor $broker
Wait-Topology | Out-Null

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:5173/"
    Start-Process "$NodeRedUrl/pertamina-gld/topology/view"
}

Write-Step "Done"
