param(
    [string]$NodeRedUrl    = "http://127.0.0.1:1880",
    [string]$MqttHost      = "CHANGE_ME_MQTT_HOST",
    [int]$MqttPort         = 1884,
    [string]$MqttUser      = $env:MQTT_USER,
    [string]$MqttPassword  = $env:MQTT_PASS,
    [string]$MySqlHost     = "localhost",
    [int]$MySqlPort        = 3306,
    [string]$MySqlDatabase = "pertamina_gld",
    [string]$MySqlUser     = "root",
    [string]$MySqlPassword = "",
    [string]$CsvPath       = "C:\Users\asus\gld-dataset.csv",
    [string]$DeviceId      = "F001",
    [switch]$GenerateOnly
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function New-Id($name) { return "pgld_ds_$name" }

$tab = New-Id "tab"
$broker = "pgl_mqtt_broker"
$mysqlCfg = New-Id "mysql_cfg"
$commandTopic = "gas-leak-detector/$DeviceId/dataset"
$ackTopic = "gas-leak-detector/+/cmd/ack"

# JS function bodies stay single-line for PowerShell 5.1 ConvertTo-Json stability.
$parseFn = "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload; if(!p||p.seq===undefined||!p.sensor_voltage||p.sensor_voltage.length!==8){node.warn('invalid record');return null;} var sv=p.sensor_voltage,gain=p.sensor_gain||[0,0,0,0,0,0,0,0]; msg.topic='INSERT INTO gld_dataset (device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'; msg.payload=[p.device_id||'',p.node_id||0,p.mode||'DATASET',p.seq,p.timestamp_ms||0,p.label||'',p.nulling_profile_id||0,sv[0],sv[1],sv[2],sv[3],sv[4],sv[5],sv[6],sv[7],gain[0],gain[1],gain[2],gain[3],gain[4],gain[5],gain[6],gain[7]]; return msg;"
$csvRowFn = "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload; if(!p||!p.sensor_voltage)return null; var sv=p.sensor_voltage,gain=p.sensor_gain||[0,0,0,0,0,0,0,0]; msg.payload=[p.device_id||'',p.node_id||0,p.mode||'DATASET',p.seq,p.timestamp_ms||0,p.label||'',p.nulling_profile_id||0].concat(sv).concat(gain).join(',')+String.fromCharCode(10); msg.filename=global.get('gld_csv_path')||'$CsvPath'; return msg;"
$csvHeaderFn = "msg.payload='device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7'+String.fromCharCode(10); msg.filename=global.get('gld_csv_path')||'$CsvPath'; return msg;"
$initFn = "global.set('gld_csv_path','$CsvPath'); return msg;"
$createTableFn = "msg.topic='CREATE TABLE IF NOT EXISTS gld_dataset (id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,device_id VARCHAR(16),node_id INT UNSIGNED,mode VARCHAR(16) DEFAULT \'DATASET\',seq INT UNSIGNED,timestamp_ms BIGINT UNSIGNED,label VARCHAR(32),nulling_profile_id TINYINT UNSIGNED DEFAULT 0,sv0 FLOAT,sv1 FLOAT,sv2 FLOAT,sv3 FLOAT,sv4 FLOAT,sv5 FLOAT,sv6 FLOAT,sv7 FLOAT,gain0 TINYINT,gain1 TINYINT,gain2 TINYINT,gain3 TINYINT,gain4 TINYINT,gain5 TINYINT,gain6 TINYINT,gain7 TINYINT)'; msg.payload=[]; return msg;"

$tabNode = @{
    id = $tab
    type = "tab"
    label = "GLD Dataset Server"
    disabled = $false
    info = "Dataset recording: current GLD unified JSON records via MQTT to MySQL + CSV."
}

$mysqlConfig = @{
    id = $mysqlCfg
    type = "MySQLdatabase"
    name = "GLD Dataset DB"
    host = $MySqlHost
    port = [string]$MySqlPort
    db = $MySqlDatabase
    tz = "Asia/Jakarta"
    charset = "UTF8"
    credentials = @{ user = $MySqlUser; password = $MySqlPassword }
}

$tabNodes = @(
    @{ id = New-Id "init_inject"; type = "inject"; z = $tab; name = "init on boot"
       props = @(@{ p = "payload" })
       repeat = ""; once = $true; onceDelay = "0.5"; payload = ""; payloadType = "date"
       x = 160; y = 80; wires = @(, @((New-Id "init_fn"))) },

    @{ id = New-Id "init_fn"; type = "function"; z = $tab; name = "set csv path"
       func = $initFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 380; y = 80; wires = @(, @((New-Id "create_table_fn"), (New-Id "csv_header_fn"))) },

    @{ id = New-Id "create_table_fn"; type = "function"; z = $tab; name = "CREATE TABLE SQL"
       func = $createTableFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 640; y = 60; wires = @(, @((New-Id "mysql_init"))) },

    @{ id = New-Id "mysql_init"; type = "mysql"; z = $tab; name = "CREATE TABLE"; mydb = $mysqlCfg
       x = 880; y = 60; wires = @(, @()) },

    @{ id = New-Id "csv_header_fn"; type = "function"; z = $tab; name = "CSV header"
       func = $csvHeaderFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 640; y = 120; wires = @(, @((New-Id "csv_header_file"))) },

    @{ id = New-Id "csv_header_file"; type = "file"; z = $tab; name = "write CSV header"
       filename = "filename"; filenameType = "msg"; appendNewline = $false; createDir = $true; overwriteFile = "true"
       x = 880; y = 120; wires = @(, @()) },

    @{ id = New-Id "start_dataset_inject"; type = "inject"; z = $tab; name = "START_DATASET clear_air_test"
       props = @(@{ p = "payload" })
       repeat = ""; once = $false; onceDelay = "0.1"
       payload = '{"cmd":"START_DATASET","label":"clear_air_test","target_samples":0,"sample_interval_ms":1000,"max_duration_ms":0,"use_fan_intake":false,"fan_on_ms":1000,"post_fan_settle_ms":0}'
       payloadType = "json"; x = 180; y = 180; wires = @(, @((New-Id "mqtt_dataset_cmd_out"))) },

    @{ id = New-Id "stop_dataset_inject"; type = "inject"; z = $tab; name = "STOP_DATASET"
       props = @(@{ p = "payload" })
       repeat = ""; once = $false; onceDelay = "0.1"
       payload = '{"cmd":"STOP_DATASET"}'
       payloadType = "json"; x = 180; y = 220; wires = @(, @((New-Id "mqtt_dataset_cmd_out"))) },

    @{ id = New-Id "mqtt_dataset_cmd_out"; type = "mqtt out"; z = $tab; name = "dataset command"
       topic = $commandTopic; qos = "0"; retain = ""; respTopic = ""; contentType = "application/json"
       userProps = ""; correl = ""; expiry = ""; broker = $broker
       x = 480; y = 200; wires = @() },

    @{ id = New-Id "mqtt_data_in"; type = "mqtt in"; z = $tab; name = "dataset/data"
       topic = "gas-leak-detector/+/dataset/data"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 260; wires = @(, @((New-Id "parse_record_fn"), (New-Id "csv_row_fn"), (New-Id "debug_record"))) },

    @{ id = New-Id "parse_record_fn"; type = "function"; z = $tab; name = "parse record"
       func = $parseFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 400; y = 260; wires = @(, @((New-Id "mysql_insert"))) },

    @{ id = New-Id "mysql_insert"; type = "mysql"; z = $tab; name = "INSERT record"; mydb = $mysqlCfg
       x = 660; y = 220; wires = @(, @()) },

    @{ id = New-Id "csv_row_fn"; type = "function"; z = $tab; name = "format CSV row"
       func = $csvRowFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 660; y = 280; wires = @(, @((New-Id "csv_append_file"))) },

    @{ id = New-Id "csv_append_file"; type = "file"; z = $tab; name = "append CSV"
       filename = "filename"; filenameType = "msg"; appendNewline = $false; createDir = $true; overwriteFile = "false"
       x = 880; y = 280; wires = @(, @()) },

    @{ id = New-Id "debug_record"; type = "debug"; z = $tab; name = "record"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.label"; statusType = "msg"
       x = 660; y = 340; wires = @() },

    @{ id = New-Id "mqtt_status_in"; type = "mqtt in"; z = $tab; name = "dataset/status"
       topic = "gas-leak-detector/+/dataset/status"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 440; wires = @(, @((New-Id "debug_status"))) },

    @{ id = New-Id "debug_status"; type = "debug"; z = $tab; name = "status"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.state"; statusType = "msg"
       x = 400; y = 440; wires = @() },

    @{ id = New-Id "mqtt_summary_in"; type = "mqtt in"; z = $tab; name = "dataset/summary"
       topic = "gas-leak-detector/+/dataset/summary"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 520; wires = @(, @((New-Id "debug_summary"))) },

    @{ id = New-Id "debug_summary"; type = "debug"; z = $tab; name = "summary"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.total_samples"; statusType = "msg"
       x = 400; y = 520; wires = @() },

    @{ id = New-Id "mqtt_ack_in"; type = "mqtt in"; z = $tab; name = "cmd/ack"
       topic = $ackTopic; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 600; wires = @(, @((New-Id "debug_ack"))) },

    @{ id = New-Id "debug_ack"; type = "debug"; z = $tab; name = "command ack"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.result"; statusType = "msg"
       x = 400; y = 600; wires = @() },

    @{ id = New-Id "mqtt_nulling_in"; type = "mqtt in"; z = $tab; name = "nulling/result"
       topic = "gas-leak-detector/+/nulling/result"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $true; rh = 0; inputs = 0
       x = 160; y = 680; wires = @(, @((New-Id "debug_nulling"))) },

    @{ id = New-Id "debug_nulling"; type = "debug"; z = $tab; name = "nulling profile"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.profileId"; statusType = "msg"
       x = 400; y = 680; wires = @() }
)

$generatedPath = Join-Path $scriptDir "pertamina-gld-dataset.flow.json"
$exportNodes = @($tabNode, $mysqlConfig) + $tabNodes
$exportNodes | ConvertTo-Json -Depth 30 | Set-Content -Path $generatedPath -Encoding UTF8

if ($GenerateOnly) {
    [pscustomobject]@{ Generated = $true; FlowFile = $generatedPath; Nodes = $exportNodes.Count } |
        ConvertTo-Json -Compress
    exit 0
}

$flowsEndpoint = "$NodeRedUrl/flows"
$apiHeaders = @{ "Node-RED-API-Version" = "v2" }
$deployHeaders = @{
    "Node-RED-API-Version" = "v2"
    "Node-RED-Deployment-Type" = "full"
}

$current = Invoke-RestMethod -Uri $flowsEndpoint -Method Get -Headers $apiHeaders -TimeoutSec 30
if (-not $current.flows -or -not $current.rev) {
    throw "Node-RED /flows did not return API v2 envelope with flows and rev"
}

$currentFlows = @($current.flows)

$deployNodes = @()
$credentials = @{}
foreach ($node in $exportNodes) {
    $copy = @{}
    foreach ($key in $node.Keys) {
        $copy[$key] = $node[$key]
    }
    if ($copy.ContainsKey("credentials")) {
        $credentials[[string]$copy["id"]] = $copy["credentials"]
        [void]$copy.Remove("credentials")
    }
    $deployNodes += $copy
}

$removedDatasetNodes = @($currentFlows | Where-Object {
    $id = [string]$_.id
    ($id.StartsWith("pgld_ds_")) -or
    ($_.type -eq "tab" -and ($_.id -eq $tab -or $_.label -eq "GLD Dataset Server"))
})

$kept = @($currentFlows | Where-Object {
    $id = [string]$_.id
    -not (
        $id.StartsWith("pgld_ds_") -or
        ($_.type -eq "tab" -and ($_.id -eq $tab -or $_.label -eq "GLD Dataset Server"))
    )
})
$merged = @($kept + $deployNodes)

$deployBody = @{
    rev = $current.rev
    flows = $merged
    credentials = $credentials
}
$jsonBody = $deployBody | ConvertTo-Json -Depth 60 -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$bodyBytes = $utf8NoBom.GetBytes($jsonBody)
$response = Invoke-RestMethod -Uri $flowsEndpoint -Method Post `
    -Headers $deployHeaders `
    -ContentType "application/json; charset=utf-8" `
    -Body $bodyBytes -TimeoutSec 60

[pscustomobject]@{
    Applied = $true
    NodeRedUrl = $NodeRedUrl
    TabId = $tab
    FlowFile = $generatedPath
    AddedNodes = $exportNodes.Count
    RemovedDatasetNodes = $removedDatasetNodes.Count
    TotalNodes = $merged.Count
    ApiUsesEnvelope = $true
    CredentialsApplied = $credentials.Count
    BrokerConfig = $broker
    CommandTopic = $commandTopic
    AckTopic = $ackTopic
    MqttHostHint = $MqttHost
    MqttPortHint = $MqttPort
} | ConvertTo-Json -Compress
