[CmdletBinding()]
param(
    [ValidateSet("all", "firmware", "server", "hub", "gateway-server")]
    [string]$Scope = "all",

    [string]$RepoRoot = (Join-Path $PSScriptRoot "..\..\.."),

    [ValidateRange(1, 500)]
    [int]$OutputTailLines = 80
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Limit-Lines {
    param(
        [object[]]$Lines,
        [int]$Limit
    )

    $textLines = @($Lines | ForEach-Object { [string]$_ })
    if ($textLines.Count -gt $Limit) {
        $textLines = @($textLines | Select-Object -Last $Limit)
    }

    return ($textLines -join [Environment]::NewLine)
}

function New-SkippedCheck {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Reason
    )

    [pscustomobject]@{
        name       = $Name
        status     = "skipped"
        exitCode   = $null
        durationMs = 0
        command    = $null
        output     = $Reason
    }
}

function Invoke-ExternalCheck {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Tool,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [int]$TailLines
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $previousLocation = Get-Location
    $output = @()
    $exitCode = $null

    try {
        Set-Location -LiteralPath $WorkingDirectory
        $output = @(& $Tool @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    catch {
        $output = @($_.Exception.Message)
        $exitCode = 1
    }
    finally {
        Set-Location -LiteralPath $previousLocation
        $stopwatch.Stop()
    }

    [pscustomobject]@{
        name       = $Name
        status     = $(if ($exitCode -eq 0) { "passed" } else { "failed" })
        exitCode   = $exitCode
        durationMs = $stopwatch.ElapsedMilliseconds
        command    = "$Tool $($Arguments -join ' ')"
        output     = Limit-Lines -Lines $output -Limit $TailLines
    }
}

function Add-FileCheck {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Target,

        [Parameter(Mandatory)]
        [string]$Name,

        [AllowNull()]
        [string]$Tool,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [Parameter(Mandatory)]
        [string]$RequiredPath,

        [Parameter(Mandatory)]
        [string]$Root,

        [Parameter(Mandatory)]
        [int]$TailLines
    )

    if (-not $Tool) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "Required runtime is unavailable; dependency installation is outside audit scope."))
        return
    }

    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "Repository-owned check is absent: $RequiredPath"))
        return
    }

    $Target.Add((Invoke-ExternalCheck -Name $Name -Tool $Tool -Arguments $Arguments -WorkingDirectory $Root -TailLines $TailLines))
}

function Add-AllowlistedFileCheck {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Target,

        [Parameter(Mandatory)]
        [string]$Name,

        [AllowNull()]
        [string]$Tool,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [Parameter(Mandatory)]
        [string]$RelativePath,

        [Parameter(Mandatory)]
        [hashtable]$AllowedHashes,

        [Parameter(Mandatory)]
        [string]$Root,

        [Parameter(Mandatory)]
        [int]$TailLines
    )

    if (-not $Tool) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "Required runtime is unavailable; dependency installation is outside audit scope."))
        return
    }

    $file = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "Allowlisted check is absent: $RelativePath"))
        return
    }

    if (-not $AllowedHashes.ContainsKey($RelativePath)) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "Check is not present in the reviewed host-check manifest: $RelativePath"))
        return
    }

    $actualHash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    $expectedHash = [string]$AllowedHashes[$RelativePath]
    if ($actualHash -ne $expectedHash) {
        $Target.Add((New-SkippedCheck -Name $Name -Reason "SHA-256 drift for $RelativePath. Review side effects and dependencies before updating the manifest."))
        return
    }

    $Target.Add((Invoke-ExternalCheck -Name $Name -Tool $Tool -Arguments $Arguments -WorkingDirectory $Root -TailLines $TailLines))
}

$inputRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$gitRootOutput = @(& git -C $inputRoot rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve Git root: $($gitRootOutput -join [Environment]::NewLine)"
}

$root = [System.IO.Path]::GetFullPath([string]$gitRootOutput[-1])
if (-not (Test-Path -LiteralPath (Join-Path $root "ActivityAI/rules/AGENTS.md"))) {
    throw "Not a PertaminaGLD repository root: $root"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
$python = if ($pythonCommand) { $pythonCommand.Source } else { $null }
$node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
$checks = [System.Collections.Generic.List[object]]::new()
$manifestPath = Join-Path $PSScriptRoot "..\references\host-check-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Host-check manifest is missing: $manifestPath"
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$allowedHashes = @{}
foreach ($entry in @($manifest.files)) {
    $allowedHashes[[string]$entry.path] = [string]$entry.sha256
}

$oldNoByteCode = [Environment]::GetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "Process")
[Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1", "Process")

try {
    if ($Scope -in @("all", "firmware", "gateway-server")) {
        $allowlistedRunner = Join-Path $PSScriptRoot "run-allowlisted-python-tests.py"
        $firmwareChecks = if ($Scope -eq "gateway-server") {
            @(
                @{ Name = "Gateway multi-gateway isolation"; Path = "firmware/tests/test_gateway_multi_gateway_isolation.py" }
            )
        }
        else {
            @(
                @{ Name = "Firmware shared protocol"; Path = "firmware/tests/test_shared_protocol.py" },
                @{ Name = "Gateway multi-gateway isolation"; Path = "firmware/tests/test_gateway_multi_gateway_isolation.py" },
                @{ Name = "CH parent policy"; Path = "firmware/tests/test_ch_parent_policy.py" }
            )
        }

        foreach ($definition in $firmwareChecks) {
            $file = Join-Path $root $definition.Path
            if (-not (Test-Path -LiteralPath $allowlistedRunner -PathType Leaf)) {
                $checks.Add((New-SkippedCheck -Name $definition.Name -Reason "Explicit Python test runner is missing: $allowlistedRunner"))
                continue
            }
            Add-AllowlistedFileCheck -Target $checks -Name $definition.Name -Tool $python -Arguments @("-B", $allowlistedRunner, $file) -RelativePath $definition.Path -AllowedHashes $allowedHashes -Root $root -TailLines $OutputTailLines
        }
    }

    if ($Scope -in @("all", "server", "gateway-server")) {
        $serverChecks = @(
            @{ Name = "Node-RED replay policy"; Path = "server/nodered/tests/replay-policy.test.js"; Extra = @() },
            @{ Name = "Node-RED multi-gateway topology"; Path = "server/nodered/tests/multi-gateway-topology.test.js"; Extra = @() },
            @{ Name = "Node-RED GLD request correlation"; Path = "server/nodered/tests/gld-request-correlation.test.js"; Extra = @() },
            @{ Name = "Node-RED generated-flow drift"; Path = "server/nodered/apply-pertamina-gld-flow.js"; Extra = @("--check") }
        )

        foreach ($definition in $serverChecks) {
            $file = Join-Path $root $definition.Path
            $arguments = @($file) + @($definition.Extra)
            Add-AllowlistedFileCheck -Target $checks -Name $definition.Name -Tool $node -Arguments $arguments -RelativePath $definition.Path -AllowedHashes $allowedHashes -Root $root -TailLines $OutputTailLines
        }
    }

    if ($Scope -in @("all", "hub")) {
        $javascriptChecks = @(
            "apps/operator-hub/public/js/hub.js",
            "apps/gld-operator/js/main.js",
            "apps/gld-operator/js/nulling.js",
            "apps/gld-operator/js/serial-protocol.js"
        )

        foreach ($relativePath in $javascriptChecks) {
            $file = Join-Path $root $relativePath
            Add-FileCheck -Target $checks -Name "JavaScript syntax: $relativePath" -Tool $node -Arguments @("--check", $file) -RequiredPath $file -Root $root -TailLines $OutputTailLines
        }

        $astCheck = "import ast,pathlib,sys; p=pathlib.Path(sys.argv[1]); ast.parse(p.read_text(encoding='utf-8'), filename=str(p))"
        $pythonChecks = @(
            "apps/operator-hub/bridge.py",
            "apps/operator-hub/preflight.py"
        )

        foreach ($relativePath in $pythonChecks) {
            $file = Join-Path $root $relativePath
            Add-FileCheck -Target $checks -Name "Python syntax: $relativePath" -Tool $python -Arguments @("-B", "-c", $astCheck, $file) -RequiredPath $file -Root $root -TailLines $OutputTailLines
        }
    }
}
finally {
    [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", $oldNoByteCode, "Process")
}

$passed = @($checks | Where-Object { $_.status -eq "passed" }).Count
$failed = @($checks | Where-Object { $_.status -eq "failed" }).Count
$skipped = @($checks | Where-Object { $_.status -eq "skipped" }).Count

$result = [pscustomobject]@{
    schemaVersion = 1
    checkedAtUtc  = [DateTime]::UtcNow.ToString("o")
    repoRoot      = $root
    scope         = $Scope
    safety        = "Host-only checks. Executable repository checks require an exact reviewed SHA-256; no dynamic test discovery, build, COM, upload, broker, deployment, dependency installation, or live service operation."
    manifestHead  = [string]$manifest.reviewedAtHead
    summary       = [pscustomobject]@{
        total   = $checks.Count
        passed  = $passed
        failed  = $failed
        skipped = $skipped
    }
    checks        = @($checks)
}

$result | ConvertTo-Json -Depth 6
if ($failed -gt 0) {
    exit 1
}
if ($skipped -gt 0) {
    exit 2
}
