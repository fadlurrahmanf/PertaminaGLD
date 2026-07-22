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
    [string]$NodeRedToken  = $env:NODE_RED_ADMIN_TOKEN,
    [switch]$GenerateOnly,
    [switch]$Check
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
$csvHeader = "device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,sv_MQ8,sv_MQ135,sv_MQ3,sv_MQ5,sv_MQ4,sv_MQ7,sv_MQ6,sv_MQ2,gain_MQ8,gain_MQ135,gain_MQ3,gain_MQ5,gain_MQ4,gain_MQ7,gain_MQ6,gain_MQ2,status_MQ8,status_MQ135,status_MQ3,status_MQ5,status_MQ4,status_MQ7,status_MQ6,status_MQ2,feature_1,feature_2,feature_3,feature_4,feature_5,feature_6,feature_7,feature_8"
$parseFn = "function reject(reason){node.warn('dataset record rejected: '+reason);return null;} function finite8(v){return Array.isArray(v)&&v.length===8&&v.every(function(x){return typeof x==='number'&&Number.isFinite(x);});} function csv(v){var s=String(v===undefined?'':v);return /[\x22,\r\n]/.test(s)?String.fromCharCode(34)+s.replace(/\x22/g,String.fromCharCode(34)+String.fromCharCode(34))+String.fromCharCode(34):s;} var p;try{p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload;}catch(e){return reject('invalid JSON');} var expected=['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2']; var gains=[1,2,4,8,16,32,64]; if(!p||typeof p!=='object'||Array.isArray(p))return reject('object required'); var device=String(p.device_id||'').toUpperCase(); if(!/^[0-9A-F]{4}`$/.test(device))return reject('invalid device_id'); var topic=String(msg.topic||'').split('/'); if(topic.length!==4||topic[0]!=='gas-leak-detector'||String(topic[1]).toUpperCase()!==device||topic[2]!=='dataset'||topic[3]!=='data')return reject('topic/device mismatch'); if(!Number.isInteger(p.node_id)||p.node_id!==parseInt(device,16))return reject('node_id mismatch'); if(String(p.mode||'').toUpperCase()!=='DATASET')return reject('mode'); if(!Number.isInteger(p.seq)||p.seq<0||p.seq>4294967295)return reject('seq'); if(!Number.isInteger(p.timestamp_ms)||p.timestamp_ms<0||p.timestamp_ms>4294967295)return reject('timestamp_ms'); if(!Number.isInteger(p.nulling_profile_id)||p.nulling_profile_id<1||p.nulling_profile_id>255)return reject('nulling profile'); var label=String(p.label||''); if(!label||label.length>31||/[\x00-\x1F]/.test(label)||/^[=+\-@]/.test(label))return reject('unsafe label'); if(!finite8(p.sensor_voltage))return reject('sensor_voltage'); if(!Array.isArray(p.sensor_gain)||p.sensor_gain.length!==8||!p.sensor_gain.every(function(x){return Number.isInteger(x)&&gains.includes(x);}))return reject('sensor_gain'); if(!Array.isArray(p.sensor_status)||p.sensor_status.length!==8||!p.sensor_status.every(function(x){return x===0;}))return reject('sensor_status'); if(!Array.isArray(p.feature_order)||p.feature_order.length!==8||!p.feature_order.every(function(x,i){return x===expected[i];}))return reject('feature_order'); var row=[device,p.node_id,'DATASET',p.seq,p.timestamp_ms,label,p.nulling_profile_id].concat(p.sensor_voltage,p.sensor_gain); msg.csvLine=row.concat(p.sensor_status,p.feature_order).map(csv).join(',')+String.fromCharCode(10); msg.filename=global.get('gld_csv_path')||'$CsvPath'; msg.topic='INSERT INTO gld_dataset (device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7) SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM gld_dataset WHERE device_id=? AND seq=? AND timestamp_ms=? AND label=? LIMIT 1)'; msg.payload=row.concat([device,p.seq,p.timestamp_ms,label]); return msg;"
$persistGateFn = "var result=msg.payload||{}; if(Number(result.affectedRows)!==1){node.status({fill:'yellow',shape:'ring',text:'duplicate/rejected'});return null;} var count=Number(flow.get('gld_dataset_persisted_count')||0)+1; flow.set('gld_dataset_persisted_count',count); msg.payload=msg.csvLine; delete msg.csvLine; node.status({fill:'green',shape:'dot',text:count+' rows persisted'}); return msg;"
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
}

$tabNodes = @(
    @{ id = New-Id "init_inject"; type = "inject"; z = $tab; name = "init on boot"
       props = @(@{ p = "payload" })
       repeat = ""; once = $true; onceDelay = "0.5"; payload = ""; payloadType = "date"
       x = 160; y = 80; wires = @(, @((New-Id "init_fn"))) },

    @{ id = New-Id "init_fn"; type = "function"; z = $tab; name = "set csv path"
       func = $initFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 380; y = 80; wires = @(, @((New-Id "create_table_fn"))) },

    @{ id = New-Id "create_table_fn"; type = "function"; z = $tab; name = "CREATE TABLE SQL"
       func = $createTableFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 640; y = 60; wires = @(, @((New-Id "mysql_init"))) },

    @{ id = New-Id "mysql_init"; type = "mysql"; z = $tab; name = "CREATE TABLE"; mydb = $mysqlCfg
       x = 880; y = 60; wires = @(, @()) },

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
       x = 160; y = 260; wires = @(, @((New-Id "parse_record_fn"), (New-Id "debug_record"))) },

    @{ id = New-Id "parse_record_fn"; type = "function"; z = $tab; name = "parse record"
       func = $parseFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 400; y = 260; wires = @(, @((New-Id "mysql_insert"))) },

    @{ id = New-Id "mysql_insert"; type = "mysql"; z = $tab; name = "INSERT record"; mydb = $mysqlCfg
       x = 660; y = 220; wires = @(, @((New-Id "persist_gate_fn"))) },

    @{ id = New-Id "persist_gate_fn"; type = "function"; z = $tab; name = "persist only inserted row"
       func = $persistGateFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 690; y = 280; wires = @(, @((New-Id "csv_append_file"))) },

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
$generatedJson = $exportNodes | ConvertTo-Json -Depth 30
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
if ($Check) {
    if (-not (Test-Path -LiteralPath $generatedPath)) {
        throw "Generated dataset flow is missing: $generatedPath"
    }
    $existingJson = [IO.File]::ReadAllText($generatedPath)
    if ($existingJson -ne $generatedJson) {
        throw "Generated dataset flow drift detected; run with -GenerateOnly and review the result"
    }
    [pscustomobject]@{ Generated = $false; Drift = $false; FlowFile = $generatedPath; Nodes = $exportNodes.Count } |
        ConvertTo-Json -Compress
    exit 0
}
[IO.File]::WriteAllText($generatedPath, $generatedJson, $utf8NoBom)

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
if ($NodeRedToken) {
    $apiHeaders["Authorization"] = "Bearer $NodeRedToken"
    $deployHeaders["Authorization"] = "Bearer $NodeRedToken"
}

$current = Invoke-RestMethod -Uri $flowsEndpoint -Method Get -Headers $apiHeaders -TimeoutSec 30
if (-not $current.flows -or -not $current.rev) {
    throw "Node-RED /flows did not return API v2 envelope with flows and rev"
}

$currentFlows = @($current.flows)

$deployNodes = @()
foreach ($node in $exportNodes) {
    $copy = @{}
    foreach ($key in $node.Keys) {
        $copy[$key] = $node[$key]
    }
    if ([string]$copy["id"] -eq $mysqlCfg) {
        $copy["credentials"] = @{ user = $MySqlUser; password = $MySqlPassword }
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
}
$jsonBody = $deployBody | ConvertTo-Json -Depth 60 -Compress
$bodyBytes = $utf8NoBom.GetBytes($jsonBody)

$csvParent = Split-Path -Parent $CsvPath
if ($csvParent -and -not (Test-Path -LiteralPath $csvParent)) {
    [IO.Directory]::CreateDirectory($csvParent) | Out-Null
}
if (-not (Test-Path -LiteralPath $CsvPath) -or (Get-Item -LiteralPath $CsvPath).Length -eq 0) {
    [IO.File]::WriteAllText($CsvPath, $csvHeader + [Environment]::NewLine, $utf8NoBom)
} else {
    $existingHeader = [IO.File]::ReadLines($CsvPath) | Select-Object -First 1
    if ($existingHeader -ne $csvHeader) {
        throw "Existing CSV schema does not match the validated dataset schema; choose a new -CsvPath"
    }
}
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
    CredentialsApplied = 1
    BrokerConfig = $broker
    CommandTopic = $commandTopic
    AckTopic = $ackTopic
    MqttHostHint = $MqttHost
    MqttPortHint = $MqttPort
} | ConvertTo-Json -Compress
