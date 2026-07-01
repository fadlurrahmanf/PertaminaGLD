param(
    [string]$NodeRedUrl = "http://127.0.0.1:1880",
    [string]$NodeRedUserDir = "C:\Users\asus\.node-red",
    [string]$GatewayStatusUrl = "http://192.168.4.1/api/status",
    [string]$GatewayBaseUrl = "http://192.168.4.1",
    [string]$MqttHost = "127.0.0.1",
    [int]$MqttPort = 1884,
    [string]$MqttUser = $env:MQTT_USER,
    [string]$MqttPassword = $env:MQTT_PASS,
    [switch]$GenerateOnly,
    [switch]$EnableGatewayPoll
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jsPath = Join-Path $scriptDir "apply-pertamina-gld-flow.js"
$nodeExe = (Get-Command node -ErrorAction Stop).Source

$nodeArgs = @(
    $jsPath,
    "--node-red-url", $NodeRedUrl,
    "--node-red-user-dir", $NodeRedUserDir,
    "--gateway-status-url", $GatewayStatusUrl,
    "--gateway-base-url", $GatewayBaseUrl,
    "--mqtt-host", $MqttHost,
    "--mqtt-port", [string]$MqttPort
)

if ($MqttUser) {
    $nodeArgs += @("--mqtt-user", $MqttUser)
}
if ($MqttPassword) {
    $nodeArgs += @("--mqtt-password", $MqttPassword)
}
if ($GenerateOnly) {
    $nodeArgs += "--generate-only"
}
if ($EnableGatewayPoll) {
    $nodeArgs += "--enable-gateway-poll"
}

& $nodeExe @nodeArgs
exit $LASTEXITCODE
