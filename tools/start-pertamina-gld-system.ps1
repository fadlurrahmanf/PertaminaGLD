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
$StartupProfilePath = Join-Path $RepoRoot "apps\runtime\operator-hub\startup.local.json"
$NodeRedEnvPath = Join-Path $NodeRedDir ".env"

function Write-Step([string]$Message) {
    Write-Host "[Pertamina GLD] $Message"
}

function Test-TcpEndpoint([string]$HostName, [int]$Port, [int]$TimeoutMs = 1500) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait($TimeoutMs)) {
            return $false
        }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-TcpEndpoint([string]$HostName, [int]$Port, [string]$Name, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpEndpoint $HostName $Port) {
            Write-Step "$Name is reachable at ${HostName}:$Port"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Warning "$Name did not become reachable at ${HostName}:$Port within $TimeoutSec seconds"
    return $false
}

function Get-OperatorHubStatus() {
    try {
        return Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/status" -TimeoutSec 4
    } catch {
        return $null
    }
}

function Test-OperatorHubReady() {
    $status = Get-OperatorHubStatus
    return [bool]($status -and $status.apps.gw.identityOk -and $status.apps.ch.identityOk -and $status.apps.gld.identityOk)
}

function Test-NodeRedReady() {
    try {
        $topology = Invoke-RestMethod -Uri "$NodeRedUrl/pertamina-gld/topology" -TimeoutSec 4
        return [bool]($topology -and $topology.kind -eq "pgl-topology")
    } catch {
        return $false
    }
}

function Ensure-NodeRedFunctionGlobalContext([string]$UserDir) {
    $settingsPath = Join-Path $UserDir "settings.js"
    if (-not (Test-Path $settingsPath)) {
        throw "Node-RED settings.js was not found at $settingsPath. Run Node-RED once to initialize the user directory, then rerun this launcher."
    }

    $content = [System.IO.File]::ReadAllText($settingsPath)
    $required = @(
        @{ Name = "crypto"; Line = "        crypto: require('crypto')," },
        @{ Name = "fs"; Line = "        fs: require('fs')," },
        @{ Name = "path"; Line = "        path: require('path')," }
    )
    $missingLines = @()
    foreach ($item in $required) {
        $pattern = '(?m)^\s*' + [regex]::Escape($item.Name) + '\s*:\s*require\([''"]' + [regex]::Escape($item.Name) + '[''"]\)\s*,?'
        if ($content -notmatch $pattern) {
            $missingLines += $item.Line
        }
    }
    if ($missingLines.Count -eq 0) {
        Write-Step "Node-RED functionGlobalContext already exposes crypto, fs, and path"
        return $false
    }

    $openingPattern = "(?m)^(\s*functionGlobalContext\s*:\s*\{\s*)$"
    $opening = [regex]::Match($content, $openingPattern)
    if (-not $opening.Success) {
        throw "Could not locate functionGlobalContext in $settingsPath; update it manually before starting Node-RED"
    }
    $backupPath = "$settingsPath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    [System.IO.File]::Copy($settingsPath, $backupPath, $false)
    $newline = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
    $replacement = $opening.Groups[1].Value + $newline + ($missingLines -join $newline)
    $updated = $content.Substring(0, $opening.Index) + $replacement + $content.Substring($opening.Index + $opening.Length)
    [System.IO.File]::WriteAllText($settingsPath, $updated, [System.Text.UTF8Encoding]::new($false))
    & node --check $settingsPath
    if ($LASTEXITCODE -ne 0) {
        [System.IO.File]::Copy($backupPath, $settingsPath, $true)
        throw "Node-RED settings update failed syntax validation; restored $backupPath"
    }
    Write-Step "Node-RED functionGlobalContext updated (backup: $backupPath)"
    return $true
}

function Stop-NodeRedForSettingsReload() {
    $listenerLines = netstat -ano -p tcp | Select-String -Pattern '^\s*TCP\s+\S+:1880\s+\S+\s+LISTENING\s+(\d+)\s*$'
    foreach ($line in $listenerLines) {
        if ($line.Line -notmatch 'LISTENING\s+(\d+)\s*$') {
            continue
        }
        $processId = [int]$Matches[1]
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -eq "node") {
            Write-Step "Restarting Node-RED PID $processId to load updated settings.js"
            Stop-Process -Id $processId -Force
        }
    }
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline -and (Test-TcpEndpoint "127.0.0.1" 1880 300)) {
        Start-Sleep -Milliseconds 250
    }
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
    if (Test-OperatorHubReady) {
        Write-Step "Operator Hub already running"
        return
    }
    $bat = Join-Path $OperatorHubDir "run-operator-hub.bat"
    Write-Step "Starting Operator Hub"
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = "cmd.exe"
    $info.Arguments = "/d /c call `"$bat`""
    $info.WorkingDirectory = $OperatorHubDir
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $info.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($info) | Out-Null
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-OperatorHubReady) {
            Write-Step "Operator Hub and child apps are healthy"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Operator Hub did not become healthy within $StartupTimeoutSec seconds. Check port 5173 and apps\operator-hub."
}

function Start-NodeRed() {
    if (Test-NodeRedReady) {
        Write-Step "Node-RED already running"
        return
    }
    Write-Step "Starting Node-RED"
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = "cmd.exe"
    $info.Arguments = "/d /c node-red"
    $info.WorkingDirectory = $NodeRedDir
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $info.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($info) | Out-Null
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-NodeRedReady) {
            Write-Step "Node-RED topology endpoint is healthy"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Node-RED did not become healthy within $StartupTimeoutSec seconds. Check port 1880."
}

function Wait-BrokerCredentials() {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $CredentialsPath) {
            $broker = Get-Content -Raw $CredentialsPath | ConvertFrom-Json
            if ($broker.host -and $broker.port -and $broker.username -and $broker.password -and $broker.topicRoot -and
                (Test-TcpEndpoint ([string]$broker.host) ([int]$broker.port))) {
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
    if (-not (Wait-TcpEndpoint "127.0.0.1" 5373 "Gateway Operator" 15)) {
        Write-Step "Gateway Operator is not available; skipping MQTT monitor (broker/Node-RED remain active)"
        return $null
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
        $deadline = (Get-Date).AddSeconds(12)
        while ((Get-Date) -lt $deadline) {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:5373/api/health" -TimeoutSec 5
            if ($health.mqtt.connected -and $health.mqtt.host -eq [string]$Broker.host -and
                [int]$health.mqtt.port -eq [int]$Broker.port -and $health.mqtt.topicRoot -eq [string]$Broker.topicRoot) {
                Write-Step "Gateway Operator MQTT monitor connected"
                return $health
            }
            Start-Sleep -Milliseconds 500
        }
        throw "Gateway Operator MQTT monitor did not confirm connection"
    } catch {
        Write-Step "Gateway Operator MQTT monitor unavailable: $($_.Exception.Message). Continuing; broker/Node-RED remain active"
        return $null
    }
}

function Connect-GatewaySerial($Broker) {
    if (-not (Test-Path $StartupProfilePath)) {
        Write-Step "No startup.local.json profile; skipping automatic Gateway COM connection"
        return $null
    }
    $profile = Get-Content -Raw $StartupProfilePath | ConvertFrom-Json
    if ($profile.PSObject.Properties.Name -contains "gatewaySerialEnabled" -and -not [bool]$profile.gatewaySerialEnabled) {
        Write-Step "Gateway serial auto-connect disabled (battery/MQTT mode)"
        return $null
    }
    $preferredPort = [string]$profile.gatewayComPort
    $slot = if ($profile.gatewayComSlot) { [int]$profile.gatewayComSlot } else { 1 }
    $baud = if ($profile.gatewayBaud) { [int]$profile.gatewayBaud } else { 115200 }
    if (-not $preferredPort) {
        Write-Step "Gateway COM is not configured in startup.local.json; skipping serial connection"
        return $null
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:5373/api/health" -TimeoutSec 5
    $headers = @{ "X-GW-Bridge-Token" = $health.csrfToken }
    $ports = Invoke-RestMethod -Uri "http://127.0.0.1:5373/api/ports" -Headers $headers -TimeoutSec 5
    $device = $ports.ports | Where-Object { $_.path -eq $preferredPort } | Select-Object -First 1
    if (-not $device) {
        Write-Warning "Configured Gateway port $preferredPort is not present; connect the Gateway USB and rerun startup"
        return $null
    }

    $slotState = $health.slots.PSObject.Properties[[string]$slot].Value
    if (-not ($slotState -and $slotState.connected -and $slotState.port -eq $preferredPort)) {
        $connectBody = @{ slot = $slot; port = $preferredPort; baud = $baud } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5373/api/serial/connect" -Headers $headers -ContentType "application/json" -Body $connectBody -TimeoutSec 8 | Out-Null
    }

    $deviceMqtt = @{
        host = [string]$Broker.host
        port = [int]$Broker.port
        username = [string]$Broker.username
        password = [string]$Broker.password
    } | ConvertTo-Json -Compress
    $writeBody = @{ slot = $slot; line = "SET_MQTT_CONFIG_JSON $deviceMqtt" } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5373/api/serial/write" -Headers $headers -ContentType "application/json" -Body $writeBody -TimeoutSec 8 | Out-Null
    Write-Step "Gateway serial connected on $preferredPort (slot $slot); current MQTT settings sent to device NVS"
    return $preferredPort
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
$nodeRedSettingsChanged = Ensure-NodeRedFunctionGlobalContext $NodeRedUserDir
if ($nodeRedSettingsChanged) {
    Stop-NodeRedForSettingsReload
}
Start-NodeRed
Apply-NodeRedFlow $broker
Connect-GatewayOperatorMonitor $broker | Out-Null
$gatewayPort = Connect-GatewaySerial $broker
Wait-Topology | Out-Null

Write-Step "Ready summary: Hub=5173 Node-RED=1880 MQTT=$($broker.host):$($broker.port) GatewayOperator=5373 COM=$(if ($gatewayPort) { $gatewayPort } else { 'manual' })"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:5173/"
    Start-Process "$NodeRedUrl/pertamina-gld/topology/view"
}

Write-Step "Done"
