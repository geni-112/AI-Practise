param(
    [Parameter(Mandatory = $false)]
    [string]$RunId = "front-11ed357b8f",

    [Parameter(Mandatory = $false)]
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required file: $Path"
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

function Read-RawFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path
}

$runDir = Join-Path $ProjectRoot (Join-Path "generated" $RunId)
$releaseDir = Join-Path $runDir "release"
$preExecutionDir = Join-Path $runDir "pre_execution"
$blueprintOutDir = Join-Path $ProjectRoot (Join-Path "cloud_execution_blueprint" (Join-Path "out" $RunId))
New-Item -ItemType Directory -Force -Path $blueprintOutDir | Out-Null

$paths = [ordered]@{
    preExecutionReadiness = Join-Path $preExecutionDir "pre_execution_readiness.json"
    releaseManifest       = Join-Path $releaseDir "release_manifest.json"
    cloudParameterMap     = Join-Path $releaseDir "cloud_parameter_map.json"
    deploymentPreflight   = Join-Path $releaseDir "deployment_preflight.json"
    finalImportManifest   = Join-Path $releaseDir "final_import_manifest.json"
    resolvedDataArts      = Join-Path $releaseDir "resolved_dataarts_import_package.json"
}

$preExecution = Read-JsonFile $paths.preExecutionReadiness
$releaseManifest = Read-JsonFile $paths.releaseManifest
$cloudParameterMap = Read-JsonFile $paths.cloudParameterMap
$deploymentPreflight = Read-JsonFile $paths.deploymentPreflight

$script:Checks = @()
function Add-Check {
    param(
        [string]$Id,
        [string]$Name,
        [bool]$Passed,
        [string]$Detail,
        [ValidateSet("error", "warning")]
        [string]$Severity = "error"
    )
    $status = if ($Passed) { "passed" } elseif ($Severity -eq "warning") { "warning" } else { "failed" }
    $script:Checks += [pscustomobject]@{
        id     = $Id
        name   = $Name
        status = $status
        detail = $Detail
    }
}

$preExecutionGates = @($preExecution.gates)
$failedPreExecutionGates = @($preExecutionGates | Where-Object { $_.ready -ne $true })
Add-Check `
    -Id "CEB-001" `
    -Name "Four pre-execution gates are ready" `
    -Passed (($preExecution.ready_for_execution_layer -eq $true) -and ($failedPreExecutionGates.Count -eq 0)) `
    -Detail ("ready_for_execution_layer={0}; failed_gates={1}" -f $preExecution.ready_for_execution_layer, $failedPreExecutionGates.Count)

Add-Check `
    -Id "CEB-002" `
    -Name "Cloud execution is still blocked" `
    -Passed (($preExecution.cloud_execution -eq "blocked") -and ($releaseManifest.cloud_execution -eq "blocked")) `
    -Detail ("pre_execution={0}; release={1}" -f $preExecution.cloud_execution, $releaseManifest.cloud_execution)

$requiredReleaseFiles = @(
    "approval_summary.json",
    "dataarts_import_package.json",
    "resolved_dataarts_import_package.json",
    "deployment_preflight.json",
    "cloud_parameter_map.json",
    "cloud_import_review.json",
    "final_import_manifest.json",
    "operator_handoff.md",
    "rollback_plan.md"
)
$missingReleaseFiles = @($requiredReleaseFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $releaseDir $_)) })
Add-Check `
    -Id "CEB-003" `
    -Name "Release handoff files exist" `
    -Passed ($missingReleaseFiles.Count -eq 0) `
    -Detail ("missing=[{0}]" -f ($missingReleaseFiles -join ", "))

$approvedArtifacts = @($releaseManifest.approved_artifacts)
$expectedArtifacts = @("mrs_transform.py", "dws_serving.sql", "dataarts_dag.yaml")
$missingApprovals = @($expectedArtifacts | Where-Object { $approvedArtifacts -notcontains $_ })
Add-Check `
    -Id "CEB-004" `
    -Name "Executable artifacts are approved" `
    -Passed ($missingApprovals.Count -eq 0) `
    -Detail ("missing_approvals=[{0}]" -f ($missingApprovals -join ", "))

$resolvedDataArtsText = Read-RawFile $paths.resolvedDataArts
$unresolvedPlaceholders = @([regex]::Matches($resolvedDataArtsText, '\$\{[A-Z0-9_]+\}') | ForEach-Object { $_.Value } | Select-Object -Unique)
Add-Check `
    -Id "CEB-005" `
    -Name "Resolved DataArts package has no unresolved placeholders" `
    -Passed ($unresolvedPlaceholders.Count -eq 0) `
    -Detail ("unresolved=[{0}]" -f ($unresolvedPlaceholders -join ", "))

$preflightFailed = 0
if ($null -ne $deploymentPreflight.failed) {
    $preflightFailed = [int]$deploymentPreflight.failed
}
Add-Check `
    -Id "CEB-006" `
    -Name "Deployment preflight has no failed checks" `
    -Passed ($preflightFailed -eq 0) `
    -Detail ("preflight_status={0}; failed={1}" -f $deploymentPreflight.status, $preflightFailed)

Add-Check `
    -Id "CEB-007" `
    -Name "Cloud parameter map remains placeholder-only" `
    -Passed (($cloudParameterMap.status -eq "placeholder_only") -and ($cloudParameterMap.approval_required_before_binding -eq $true)) `
    -Detail ("status={0}; approval_required_before_binding={1}" -f $cloudParameterMap.status, $cloudParameterMap.approval_required_before_binding)

$secretScanFiles = @(
    $paths.preExecutionReadiness,
    $paths.releaseManifest,
    $paths.cloudParameterMap,
    $paths.deploymentPreflight,
    $paths.finalImportManifest,
    $paths.resolvedDataArts
)
$secretPatterns = @(
    '-----BEGIN [A-Z ]*PRIVATE KEY-----',
    '(?i)(access_key|secret_key|password)\s*[:=]\s*["'']?[A-Za-z0-9+/=]{8,}',
    '(?i)AKIA[0-9A-Z]{16}'
)
$secretHits = @()
foreach ($filePath in $secretScanFiles) {
    $fileText = Read-RawFile $filePath
    foreach ($pattern in $secretPatterns) {
        if ($fileText -match $pattern) {
            $secretHits += ("{0}:{1}" -f (Split-Path -Leaf $filePath), $pattern)
        }
    }
}
Add-Check `
    -Id "CEB-008" `
    -Name "No obvious secrets in handoff metadata" `
    -Passed ($secretHits.Count -eq 0) `
    -Detail ("hits=[{0}]" -f ($secretHits -join ", "))

$failedChecks = @($script:Checks | Where-Object { $_.status -eq "failed" })
$warningChecks = @($script:Checks | Where-Object { $_.status -eq "warning" })
$passedChecks = @($script:Checks | Where-Object { $_.status -eq "passed" })
$status = if ($failedChecks.Count -eq 0) { "passed" } else { "failed" }

$summary = [ordered]@{
    run_id                        = $RunId
    generated_at                  = (Get-Date).ToUniversalTime().ToString("o")
    status                        = $status
    cloud_execution               = "blocked"
    ready_for_operator_blueprint  = ($status -eq "passed")
    project_root                  = $ProjectRoot
    release_dir                   = $releaseDir
    pre_execution_dir             = $preExecutionDir
    checks                        = $script:Checks
    passed                        = $passedChecks.Count
    warnings                      = $warningChecks.Count
    failed                        = $failedChecks.Count
    next_action                   = "Render operator handoff, then bind real Huawei Cloud resources only after explicit approval."
}

$summaryPath = Join-Path $blueprintOutDir "validation_summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Host ("Validation status: {0}" -f $status)
Write-Host ("Passed: {0}; Warnings: {1}; Failed: {2}" -f $passedChecks.Count, $warningChecks.Count, $failedChecks.Count)
Write-Host ("Summary: {0}" -f $summaryPath)

if ($failedChecks.Count -gt 0) {
    exit 2
}
