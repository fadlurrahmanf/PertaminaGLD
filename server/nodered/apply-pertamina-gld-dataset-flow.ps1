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
    [string]$CsvPath       = "C:\\Users\\asus\\gld-dataset.csv",
    [switch]$GenerateOnly
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function New-Id($name) { return "pgld_ds_$name" }

$tab      = New-Id "tab"
$broker   = "pgl_mqtt_broker"   # reuse existing broker config node
$mysqlCfg = New-Id "mysql_cfg"

# JS function bodies — single-line only (avoids PS 5.1 ConvertTo-Json multiline issues).
$parseFn       = "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload; if(!p||p.seq===undefined||!p.ch||p.ch.length!==8){node.warn('invalid record');return null;} var ch=p.ch,gain=p.gain||[0,0,0,0,0,0,0,0],ok=p.ok||[0,0,0,0,0,0,0,0]; msg.topic='INSERT INTO gld_dataset (node_id,seq,ts_ms,label,profile_id,ch0,ch1,ch2,ch3,ch4,ch5,ch6,ch7,gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7,ok0,ok1,ok2,ok3,ok4,ok5,ok6,ok7) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'; msg.payload=[p.nodeId||'',p.seq,p.ts_ms||0,p.label||'',p.profileId||0,ch[0],ch[1],ch[2],ch[3],ch[4],ch[5],ch[6],ch[7],gain[0],gain[1],gain[2],gain[3],gain[4],gain[5],gain[6],gain[7],ok[0],ok[1],ok[2],ok[3],ok[4],ok[5],ok[6],ok[7]]; return msg;"

$csvRowFn      = "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload; if(!p||!p.ch)return null; var ch=p.ch,gain=p.gain||[0,0,0,0,0,0,0,0],ok=p.ok||[0,0,0,0,0,0,0,0]; msg.payload=[p.nodeId||'',p.seq,p.ts_ms||0,p.label||'',p.profileId||0].concat(ch).concat(gain).concat(ok).join(',')+'\n'; msg.filename=global.get('gld_csv_path')||'$CsvPath'; return msg;"

$csvHeaderFn   = "msg.payload='node_id,seq,ts_ms,label,profile_id,ch0,ch1,ch2,ch3,ch4,ch5,ch6,ch7,gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7,ok0,ok1,ok2,ok3,ok4,ok5,ok6,ok7\n'; msg.filename=global.get('gld_csv_path')||'$CsvPath'; return msg;"

$initFn        = "global.set('gld_csv_path','$CsvPath'); return msg;"

$createTableFn = "msg.topic='CREATE TABLE IF NOT EXISTS gld_dataset (id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,node_id VARCHAR(16),seq INT UNSIGNED,ts_ms BIGINT UNSIGNED,label VARCHAR(32),profile_id TINYINT UNSIGNED DEFAULT 0,ch0 FLOAT,ch1 FLOAT,ch2 FLOAT,ch3 FLOAT,ch4 FLOAT,ch5 FLOAT,ch6 FLOAT,ch7 FLOAT,gain0 TINYINT,gain1 TINYINT,gain2 TINYINT,gain3 TINYINT,gain4 TINYINT,gain5 TINYINT,gain6 TINYINT,gain7 TINYINT,ok0 TINYINT,ok1 TINYINT,ok2 TINYINT,ok3 TINYINT,ok4 TINYINT,ok5 TINYINT,ok6 TINYINT,ok7 TINYINT)'; msg.payload=[]; return msg;"

# Build the tab node list.
# Note: nodes use z=$tab to belong to this tab. Config nodes (mysql cfg) have no z.
$tabNodes = @(
    @{ id = New-Id "init_inject"; type = "inject"; z = $tab; name = "init on boot"
       props = @(@{ p = "payload" })
       repeat = ""; once = $true; onceDelay = "0.5"; payload = ""; payloadType = "date"
       x = 160; y = 80; wires = @(@((New-Id "init_fn"))) },

    @{ id = New-Id "init_fn"; type = "function"; z = $tab; name = "set csv path"
       func = $initFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 380; y = 80; wires = @(@((New-Id "create_table_fn"), (New-Id "csv_header_fn"))) },

    @{ id = New-Id "create_table_fn"; type = "function"; z = $tab; name = "CREATE TABLE SQL"
       func = $createTableFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 620; y = 60; wires = @(@((New-Id "mysql_init"))) },

    @{ id = New-Id "mysql_init"; type = "mysql"; z = $tab; name = "CREATE TABLE"; mydb = $mysqlCfg
       x = 860; y = 60; wires = @(@()) },

    @{ id = New-Id "csv_header_fn"; type = "function"; z = $tab; name = "CSV header"
       func = $csvHeaderFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 620; y = 120; wires = @(@((New-Id "csv_header_file"))) },

    @{ id = New-Id "csv_header_file"; type = "file"; z = $tab; name = "write CSV header"
       filename = ""; filenameType = "msg"; appendNewline = $false; createDir = $true; overwriteFile = "true"
       x = 860; y = 120; wires = @(@()) },

    # Dataset record path
    @{ id = New-Id "mqtt_data_in"; type = "mqtt in"; z = $tab; name = "dataset/data"
       topic = "gas-leak-detector/+/dataset/data"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 260; wires = @(@((New-Id "parse_record_fn"))) },

    @{ id = New-Id "parse_record_fn"; type = "function"; z = $tab; name = "parse record"
       func = $parseFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 400; y = 260; wires = @(@((New-Id "mysql_insert"), (New-Id "csv_row_fn"), (New-Id "debug_record"))) },

    @{ id = New-Id "mysql_insert"; type = "mysql"; z = $tab; name = "INSERT record"; mydb = $mysqlCfg
       x = 660; y = 220; wires = @(@()) },

    @{ id = New-Id "csv_row_fn"; type = "function"; z = $tab; name = "format CSV row"
       func = $csvRowFn; outputs = 1; timeout = 0; noerr = 0; initialize = ""; finalize = ""; libs = @()
       x = 660; y = 280; wires = @(@((New-Id "csv_append_file"))) },

    @{ id = New-Id "csv_append_file"; type = "file"; z = $tab; name = "append CSV"
       filename = ""; filenameType = "msg"; appendNewline = $false; createDir = $true; overwriteFile = "false"
       x = 880; y = 280; wires = @(@()) },

    @{ id = New-Id "debug_record"; type = "debug"; z = $tab; name = "record"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.label"; statusType = "msg"
       x = 660; y = 340; wires = @() },

    # Status monitoring
    @{ id = New-Id "mqtt_status_in"; type = "mqtt in"; z = $tab; name = "dataset/status"
       topic = "gas-leak-detector/+/dataset/status"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $false; rh = 0; inputs = 0
       x = 160; y = 440; wires = @(@((New-Id "debug_status"))) },

    @{ id = New-Id "debug_status"; type = "debug"; z = $tab; name = "status"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.state"; statusType = "msg"
       x = 400; y = 440; wires = @() },

    # Nulling profile viewer
    @{ id = New-Id "mqtt_nulling_in"; type = "mqtt in"; z = $tab; name = "nulling/result"
       topic = "gas-leak-detector/+/nulling/result"; qos = "0"; datatype = "auto"; broker = $broker
       nl = $false; rap = $true; rh = 0; inputs = 0
       x = 160; y = 520; wires = @(@((New-Id "debug_nulling"))) },

    @{ id = New-Id "debug_nulling"; type = "debug"; z = $tab; name = "nulling profile"; active = $true
       tosidebar = $true; console = $false; tostatus = $true; complete = "payload"
       targetType = "msg"; statusVal = "payload.profileId"; statusType = "msg"
       x = 400; y = 520; wires = @() }
)

# Save generated flow file
$generatedPath = Join-Path $scriptDir "pertamina-gld-dataset.flow.json"
$tabNodes | ConvertTo-Json -Depth 30 | Set-Content -Path $generatedPath -Encoding UTF8

if ($GenerateOnly) {
    [pscustomobject]@{ Generated = $true; FlowFile = $generatedPath; Nodes = $tabNodes.Count } |
        ConvertTo-Json -Compress
    exit 0
}

# Use POST /flow (singular) to add/replace a single tab without touching other tabs.
# This avoids the round-trip ConvertTo-Json corruption of existing function node content.
$flowsEndpoint = "$NodeRedUrl/flows"
$flowEndpoint  = "$NodeRedUrl/flow"

# Step 1: find and delete any existing dataset tab (by our prefix id)
try {
    $existingTab = Invoke-RestMethod -Uri "$flowEndpoint/$tab" -Method Get -TimeoutSec 10 -ErrorAction Stop
    Write-Host "Found existing dataset tab id=$tab — deleting..."
    Invoke-RestMethod -Uri "$flowEndpoint/$tab" -Method Delete -TimeoutSec 10 | Out-Null
    Write-Host "Deleted."
} catch {
    Write-Host "No existing dataset tab found (will create new)."
}

# Step 2: build the flow body for POST /flow
# The tab node must be first; configs (mysql) included in configs array.
$flowBody = @{
    id      = $tab
    label   = "GLD Dataset Server"
    disabled = $false
    info    = "Dataset recording: GLD sensor records via MQTT to MySQL + CSV."
    nodes   = @($tabNodes)
    configs = @(
        @{ id = $mysqlCfg; type = "MySQLdatabase"; name = "GLD Dataset DB"
           host = $MySqlHost; port = [string]$MySqlPort; db = $MySqlDatabase
           tz = "Asia/Jakarta"; charset = "UTF8" }
    )
}

$json = $flowBody | ConvertTo-Json -Depth 30
$response = Invoke-RestMethod -Uri $flowEndpoint -Method Post `
    -Headers @{ "Content-Type" = "application/json" } `
    -Body $json -TimeoutSec 30

[pscustomobject]@{
    Applied      = $true
    NodeRedUrl   = $NodeRedUrl
    TabId        = $response.id
    FlowFile     = $generatedPath
    AddedNodes   = $tabNodes.Count
} | ConvertTo-Json -Compress
