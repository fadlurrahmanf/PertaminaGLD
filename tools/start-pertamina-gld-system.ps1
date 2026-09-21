param(
    [string]$NodeRedUrl = "http://127.0.0.1:1880",
    [string]$NodeRedUserDir = "$env:USERPROFILE\.node-red",
    [string]$NodeRedCommandPath = "",
    [int]$StartupTimeoutSec = 120,
    [int]$NodeRedStartupWaitSec = 15,
    [int]$NetworkStartupWaitSec = 120,
    [int]$DashboardStartupWaitSec = 180,
    [string]$RequiredNetworkName = "Bn",
    [string]$RequiredServerIPv4 = "192.168.8.19",
    [switch]$DashboardOnly,
    [switch]$ForceDeployFlow,
    [switch]$ConnectGatewayOperatorMonitor,
    [switch]$WaitForTopology,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$NodeRedDir = Join-Path $RepoRoot "server\nodered"
$OperatorHubDir = Join-Path $RepoRoot "apps\operator-hub"
$RuntimeDir = Join-Path $RepoRoot "apps\runtime\operator-hub"
$LogDir = Join-Path $RuntimeDir "logs"
$CredentialsPath = Join-Path $RepoRoot "apps\runtime\operator-hub\credentials.local.json"
$StartupStatePath = Join-Path $RuntimeDir "startup-flow-state.json"
$StartupProfilePath = Join-Path $RepoRoot "apps\runtime\operator-hub\startup.local.json"
$NodeRedEnvPath = Join-Path $NodeRedDir ".env"
$NodeRedTopologyBootstrapPath = Join-Path $NodeRedUserDir "pertamina-gld-topology-bootstrap.json"
$NodeRedTopologyContextPath = Join-Path $NodeRedUserDir "pgl-context\pgl_tab\flow.json"
$BrokerExePath = Join-Path $RepoRoot "apps\gld-operator\python-embed\python.exe"
$BrokerFirewallRuleName = "Pertamina GLD MQTT Broker 1884 (Bn Private)"

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

function Test-Listening([int]$Port) {
    try {
        return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Test-ListeningAt([string]$Address, [int]$Port) {
    try {
        return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object {
            $_.LocalAddress -eq $Address
        })
    } catch {
        return $false
    }
}

function Restore-NodeRedTopologyContext {
    if (Test-Listening 1880) {
        return
    }
    if (-not (Test-Path -LiteralPath $NodeRedTopologyBootstrapPath)) {
        return
    }
    try {
        $bootstrap = Get-Content -Raw -LiteralPath $NodeRedTopologyBootstrapPath | ConvertFrom-Json
        if (-not $bootstrap.pglTopology) {
            throw "bootstrap does not contain pglTopology"
        }
        $contextExists = Test-Path -LiteralPath $NodeRedTopologyContextPath
        $bootstrapTime = (Get-Item -LiteralPath $NodeRedTopologyBootstrapPath).LastWriteTimeUtc
        $contextTime = if ($contextExists) { (Get-Item -LiteralPath $NodeRedTopologyContextPath).LastWriteTimeUtc } else { [DateTime]::MinValue }
        if (-not $contextExists -or $bootstrapTime -gt $contextTime) {
            $contextDir = Split-Path -Parent $NodeRedTopologyContextPath
            New-Item -ItemType Directory -Path $contextDir -Force | Out-Null
            Copy-Item -LiteralPath $NodeRedTopologyBootstrapPath -Destination $NodeRedTopologyContextPath -Force
            Write-Step "Restored persisted CH topology context before Node-RED startup"
        }
    } catch {
        Write-Warning "Skipped invalid CH topology bootstrap: $($_.Exception.Message)"
    }
}

function Test-IsAdministrator() {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Test-RequiredServerNetwork() {
    try {
        $profiles = @(Get-NetConnectionProfile -ErrorAction Stop | Where-Object {
            $_.Name -eq $RequiredNetworkName -and $_.IPv4Connectivity -ne "Disconnected"
        })
        foreach ($profile in $profiles) {
            $addresses = @(Get-NetIPAddress -InterfaceIndex $profile.InterfaceIndex -AddressFamily IPv4 -ErrorAction Stop)
            if ($addresses.IPAddress -contains $RequiredServerIPv4) {
                if ($profile.NetworkCategory -eq "Private") {
                    return $true
                }
                if (Test-IsAdministrator) {
                    Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
                    Write-Step "Changed network $RequiredNetworkName to Private for broker firewall policy"
                }
                return $false
            }
        }
    } catch {
    }
    return $false
}

function Wait-RequiredServerNetwork() {
    $deadline = (Get-Date).AddSeconds($NetworkStartupWaitSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-RequiredServerNetwork) {
            Write-Step "Network $RequiredNetworkName ready at $RequiredServerIPv4"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Required network $RequiredNetworkName with local IPv4 $RequiredServerIPv4 was not ready within $NetworkStartupWaitSec seconds. Broker startup was stopped to prevent binding to the wrong interface."
}

function Get-BrokerProgramFirewallRules() {
    if (-not (Test-Path $BrokerExePath)) {
        return @()
    }
    $rules = @()
    try {
        $filters = @(Get-NetFirewallApplicationFilter -Program $BrokerExePath -ErrorAction Stop)
        foreach ($filter in $filters) {
            foreach ($rule in @(Get-NetFirewallRule -AssociatedNetFirewallApplicationFilter $filter -ErrorAction Stop)) {
                $rules += $rule
            }
        }
    } catch {
        return @()
    }
    return $rules
}

function Ensure-BrokerFirewall([string]$Phase) {
    if (-not (Test-Path $BrokerExePath)) {
        Write-Warning "Embedded broker executable was not found at $BrokerExePath"
        return
    }

    $programRules = @(Get-BrokerProgramFirewallRules)
    $conflictingBlocks = @($programRules | Where-Object {
        $_.Enabled -eq "True" -and $_.Direction -eq "Inbound" -and $_.Action -eq "Block"
    })
    $dedicatedRules = @(Get-NetFirewallRule -DisplayName $BrokerFirewallRuleName -ErrorAction SilentlyContinue)

    if (-not (Test-IsAdministrator)) {
        if ($conflictingBlocks.Count -gt 0 -or $dedicatedRules.Count -eq 0) {
            Write-Warning "Broker firewall repair is required during $Phase, but this launcher is not elevated. Run the scheduled startup task or launch once as Administrator."
        }
        return
    }

    foreach ($rule in $programRules) {
        if ($rule.DisplayName -eq "Python" -and $rule.Enabled -eq "True") {
            Set-NetFirewallRule -Name $rule.Name -Enabled False | Out-Null
            Write-Step "Disabled broad autogenerated Python firewall rule $($rule.Name)"
        }
    }

    if ($dedicatedRules.Count -eq 0) {
        $dedicatedRule = New-NetFirewallRule `
            -DisplayName $BrokerFirewallRuleName `
            -Direction Inbound `
            -Action Allow `
            -Enabled True `
            -Profile Private `
            -Program $BrokerExePath `
            -Protocol TCP `
            -LocalPort 1884 `
            -LocalAddress $RequiredServerIPv4 `
            -RemoteAddress LocalSubnet
    } else {
        $dedicatedRule = $dedicatedRules[0]
        Set-NetFirewallRule -Name $dedicatedRule.Name -Enabled True -Profile Private -Direction Inbound -Action Allow | Out-Null
        $dedicatedRule | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter -Program $BrokerExePath | Out-Null
        $dedicatedRule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 1884 -RemotePort Any | Out-Null
        $dedicatedRule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -LocalAddress $RequiredServerIPv4 -RemoteAddress LocalSubnet | Out-Null
        if ($dedicatedRules.Count -gt 1) {
            $dedicatedRules | Select-Object -Skip 1 | Set-NetFirewallRule -Enabled False | Out-Null
        }
    }
    Write-Step "Broker firewall verified for $RequiredServerIPv4`:1884 during $Phase"
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

function Start-LoggedCmd([string]$Command, [string]$WorkingDirectory, [string]$LogName) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $logPath = Join-Path $LogDir $LogName
    $quotedCommand = $Command.Replace('"', '""')
    $quotedLogPath = $logPath.Replace('"', '""')
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "`"$quotedCommand`" > `"$quotedLogPath`" 2>&1" `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden | Out-Null
    Write-Step "Logging $LogName at $logPath"
}

function Start-LoggedProcess([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$LogName) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $logPath = Join-Path $LogDir $LogName
    $errPath = Join-Path $LogDir ($LogName + ".err")
    $startArgs = @{
        FilePath = $FilePath
        WorkingDirectory = $WorkingDirectory
        WindowStyle = "Hidden"
        RedirectStandardOutput = $logPath
        RedirectStandardError = $errPath
    }
    if ($Arguments.Count -gt 0) {
        $startArgs.ArgumentList = $Arguments
    }
    Start-Process @startArgs | Out-Null
    Write-Step "Logging $LogName at $logPath"
    Write-Step "Logging $LogName stderr at $errPath"
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

function Get-FlowStartupState($Broker) {
    $envState = @{}
    foreach ($key in @("GLD_KEY_ID", "GLD_AES128_KEY_HEX", "PGL_GLD_TARGET_CH_MAP_JSON", "PGL_COMMAND_AUTH_TOKEN")) {
        $value = [Environment]::GetEnvironmentVariable($key, "Process")
        if ($null -eq $value) {
            $value = ""
        }
        $envState[$key] = [string]$value
    }
    return @{
        mqttHost = [string]$Broker.host
        mqttPort = [int]$Broker.port
        mqttUser = [string]$Broker.username
        mqttPassword = [string]$Broker.password
        mqttTopicRoot = [string]$Broker.topicRoot
        env = $envState
    }
}

function Test-FlowDeployNeeded($Broker) {
    if ($ForceDeployFlow) {
        Write-Step "Node-RED flow deploy forced"
        return $true
    }
    Write-Step "Node-RED flow deploy skipped for launch-only startup"
    return $false
}

function Save-FlowStartupState($Broker) {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    $stateJson = Get-FlowStartupState $Broker | ConvertTo-Json -Depth 6 -Compress
    @{
        savedAt = (Get-Date).ToUniversalTime().ToString("o")
        stateJson = $stateJson
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $StartupStatePath
}

function Start-OperatorHub() {
    if (Test-OperatorHubReady) {
        Write-Step "Operator Hub already running"
        return
    }
    $pyExe = Join-Path $RepoRoot "apps\gld-operator\python-embed\python.exe"
    if (-not (Test-Path $pyExe)) {
        $pyExe = "python"
    }
    Write-Step "Starting Operator Hub"
    Start-LoggedProcess $pyExe @("-u", "bridge.py", "--host", "127.0.0.1", "--port", "5173", "--mqtt-broker-host", $RequiredServerIPv4) $OperatorHubDir "operator-hub.log"
    if (-not (Wait-Port 5173 "Operator Hub" $StartupTimeoutSec)) {
        throw "Operator Hub did not start listening on port 5173 within $StartupTimeoutSec seconds."
    }
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
    $nodeRedCmd = $NodeRedCommandPath
    if ($nodeRedCmd -and -not (Test-Path $nodeRedCmd)) {
        throw "Configured Node-RED command was not found at $nodeRedCmd"
    }
    if (-not $nodeRedCmd) {
        $nodeRedCmd = Join-Path $env:APPDATA "npm\node-red.cmd"
    }
    if (Test-Path $nodeRedCmd) {
        Start-LoggedProcess $nodeRedCmd @("--userDir", $NodeRedUserDir) $NodeRedDir "node-red.log"
    } else {
        Start-LoggedCmd "node-red --userDir `"$NodeRedUserDir`"" $NodeRedDir "node-red.log"
    }
    if (-not (Wait-Port 1880 "Node-RED" $NodeRedStartupWaitSec)) {
        Write-Step "Node-RED launched in background; it may need more time before the UI opens"
    }
}

function Wait-BrokerCredentials() {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $CredentialsPath) {
            $broker = Get-Content -Raw $CredentialsPath | ConvertFrom-Json
            if ([string]$broker.host -ne $RequiredServerIPv4) {
                throw "MQTT broker credentials report $($broker.host), expected $RequiredServerIPv4. Stop the stale Operator Hub process and rerun the launcher."
            }
            if (-not (Test-ListeningAt $RequiredServerIPv4 1884)) {
                throw "MQTT port 1884 is listening on the wrong interface; expected $RequiredServerIPv4`:1884."
            }
            if ($broker.port -eq 1884 -and $broker.username -and $broker.password -and $broker.topicRoot -and
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
    Save-FlowStartupState $Broker
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
    $deadline = (Get-Date).AddSeconds(90)
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

function Open-SystemDashboards() {
    $dashboardUrl = "$NodeRedUrl/pertamina-gld/topology/view"
    $deadline = (Get-Date).AddSeconds($DashboardStartupWaitSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $dashboardUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Start-Process "http://127.0.0.1:5173/"
                Start-Process $dashboardUrl
                Write-Step "Operator Hub and topology dashboard opened"
                return
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }
    throw "Dashboard was not ready at $dashboardUrl within $DashboardStartupWaitSec seconds."
}

if ($DashboardOnly) {
    Write-Step "Waiting to open dashboards"
    Wait-RequiredServerNetwork
    Open-SystemDashboards
    Write-Step "Done"
    exit 0
}

Write-Step "Starting system from $RepoRoot"
Wait-RequiredServerNetwork
Ensure-BrokerFirewall "pre-start"
Start-OperatorHub
$broker = Wait-BrokerCredentials
Ensure-BrokerFirewall "post-start"
Load-DotEnv $NodeRedEnvPath
$nodeRedSettingsChanged = Ensure-NodeRedFunctionGlobalContext $NodeRedUserDir
if ($nodeRedSettingsChanged) {
    Stop-NodeRedForSettingsReload
}
Restore-NodeRedTopologyContext
Start-NodeRed
if (Test-FlowDeployNeeded $broker) {
    Apply-NodeRedFlow $broker
}
$gatewayPort = $null
if ($ConnectGatewayOperatorMonitor) {
    Connect-GatewayOperatorMonitor $broker | Out-Null
    $gatewayPort = Connect-GatewaySerial $broker
} else {
    Write-Step "Gateway Operator MQTT monitor connect skipped for fast startup"
}
if ($WaitForTopology) {
    Wait-Topology | Out-Null
}

Write-Step "Ready summary: Hub=5173 Node-RED=1880 MQTT=$($broker.host):$($broker.port) GatewayOperator=5373 COM=$(if ($gatewayPort) { $gatewayPort } else { 'manual' })"

if (-not $NoBrowser) {
    Open-SystemDashboards
}

Write-Step "Done"
