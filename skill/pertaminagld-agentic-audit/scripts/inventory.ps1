[CmdletBinding()]
param(
    [string]$RepoRoot = (Join-Path $PSScriptRoot "..\..\..")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-GitLines {
    param(
        [Parameter(Mandatory)]
        [string]$Root,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $lines = @(& git -C $Root @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($lines -join [Environment]::NewLine)"
    }

    return @($lines | ForEach-Object { [string]$_ })
}

function Get-PathRecord {
    param(
        [Parameter(Mandatory)]
        [string]$Root,

        [Parameter(Mandatory)]
        [string]$RelativePath
    )

    $absolutePath = Join-Path $Root $RelativePath
    $exists = Test-Path -LiteralPath $absolutePath
    $lastWriteUtc = $null
    if ($exists) {
        $lastWriteUtc = (Get-Item -LiteralPath $absolutePath).LastWriteTimeUtc.ToString("o")
    }

    [pscustomobject]@{
        path         = $RelativePath.Replace("\", "/")
        exists       = $exists
        lastWriteUtc = $lastWriteUtc
    }
}

$inputRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$gitRootLines = @(Invoke-GitLines -Root $inputRoot -Arguments @("rev-parse", "--show-toplevel"))
$root = [System.IO.Path]::GetFullPath($gitRootLines[-1])

$requiredMarkers = @(
    "AGENTS.md",
    "ActivityAI/rules/AGENTS.md",
    "firmware/platformio.ini",
    "apps/operator-hub",
    "server/nodered"
)

$missingMarkers = @($requiredMarkers | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root $_)) })
if ($missingMarkers.Count -gt 0) {
    throw "Not a PertaminaGLD repository root. Missing: $($missingMarkers -join ', ')"
}

$statusWithBranch = @(Invoke-GitLines -Root $root -Arguments @("status", "--short", "--branch"))
$porcelain = @(Invoke-GitLines -Root $root -Arguments @("status", "--short"))
$headLines = @(Invoke-GitLines -Root $root -Arguments @("rev-parse", "HEAD"))
$branchLines = @(Invoke-GitLines -Root $root -Arguments @("branch", "--show-current"))
$lastCommitLines = @(Invoke-GitLines -Root $root -Arguments @("log", "-1", "--format=%h %cI %s"))
$head = $headLines[-1]
$branch = if ($branchLines.Count -gt 0) { $branchLines[-1] } else { "(detached)" }
$lastCommit = $lastCommitLines[-1]

$instructionPaths = @(
    "AGENTS.md",
    "ActivityAI/rules/AGENTS.md",
    "ActivityAI/rules/AI_WORKFLOW_RULES.md",
    "docs/resume.md"
)

$activityPaths = @(
    "ActivityAI/codexactivity.md",
    "ActivityAI/claudeactivity.md"
)

$checkPaths = @(
    "skill/pertaminagld-agentic-audit/references/host-check-manifest.json",
    "skill/pertaminagld-agentic-audit/scripts/run-allowlisted-python-tests.py",
    "firmware/tests/test_shared_protocol.py",
    "firmware/tests/test_gateway_multi_gateway_isolation.py",
    "firmware/tests/test_ch_parent_policy.py",
    "server/nodered/tests/replay-policy.test.js",
    "server/nodered/tests/multi-gateway-topology.test.js",
    "server/nodered/tests/gld-request-correlation.test.js",
    "server/nodered/apply-pertamina-gld-flow.js",
    "apps/operator-hub/public/js/hub.js",
    "apps/operator-hub/bridge.py",
    "apps/operator-hub/preflight.py",
    "apps/gld-operator/js/main.js",
    "apps/gld-operator/js/nulling.js",
    "apps/gld-operator/js/serial-protocol.js"
)

$result = [pscustomobject]@{
    schemaVersion = 1
    checkedAtUtc  = [DateTime]::UtcNow.ToString("o")
    repoRoot      = $root
    branch        = $branch
    head          = $head
    lastCommit    = $lastCommit
    dirty         = ($porcelain.Count -gt 0)
    gitStatus     = @($statusWithBranch)
    instructions  = @($instructionPaths | ForEach-Object { Get-PathRecord -Root $root -RelativePath $_ })
    activityLogs  = @($activityPaths | ForEach-Object { Get-PathRecord -Root $root -RelativePath $_ })
    knownChecks   = @($checkPaths | ForEach-Object { Get-PathRecord -Root $root -RelativePath $_ })
}

$result | ConvertTo-Json -Depth 5
