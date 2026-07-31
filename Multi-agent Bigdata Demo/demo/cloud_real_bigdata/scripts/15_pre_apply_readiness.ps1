param(
    [string]$ObsBucketName = "",

    [string]$BucketPrefix = "sat-agentic",

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$PromptFile = "",

    [string]$Scenario = "sat_padron_base_anual",

    [switch]$UseMaaS,

    [switch]$EnableWebEcs,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$AllowOpenIngressForDemo,

    [switch]$AllowLongLivedDemo,

    [switch]$RunReadonlyCloudProbe,

    [switch]$RunTerraformPreflight,

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

function New-BucketName {
    param([string]$Prefix)
    $safePrefix = ($Prefix.ToLowerInvariant() -replace "[^a-z0-9-]", "-").Trim("-")
    if (-not $safePrefix) { $safePrefix = "sat-agentic" }
    if ($safePrefix.Length -gt 40) {
        $safePrefix = $safePrefix.Substring(0, 40).Trim("-")
    }
    $suffix = (Get-Date -Format "yyyyMMddHHmmss") + "-" + (Get-Random -Minimum 1000 -Maximum 9999)
    return "$safePrefix-$suffix"
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return [ordered]@{
            status = "invalid_json"
            path = $Path
            error = $_.Exception.Message
        }
    }
}

function Add-Gate {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail,
        [string]$EvidencePath = "",
        [bool]$Blocking = $false
    )
    $script:Gates += [ordered]@{
        name = $Name
        status = $Status
        blocking = $Blocking
        detail = $Detail
        evidence_path = $EvidencePath
    }
}

function Invoke-Captured {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    try {
        $output = & $Block 2>&1
        return [ordered]@{
            name = $Name
            exit_code = 0
            succeeded = $true
            output = (($output | Out-String).Trim())
        }
    }
    catch {
        return [ordered]@{
            name = $Name
            exit_code = 1
            succeeded = $false
            output = $_.Exception.Message
        }
    }
}

function Render-MarkdownTable {
    param([array]$Rows)
    $lines = @(
        "| status | blocking | gate | detail | evidence |",
        "| --- | --- | --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $detail = ([string]$row.detail).Replace("|", "\|").Replace("`r", " ").Replace("`n", "<br>")
        $evidence = ([string]$row.evidence_path).Replace("|", "\|")
        $name = ([string]$row.name).Replace("|", "\|")
        $lines += "| $($row.status) | $($row.blocking) | $name | $detail | $evidence |"
    }
    return $lines
}

function Write-LightweightStatusReport {
    param(
        [string]$Path,
        [string]$Status,
        [string]$Message,
        [string]$NextAction = ""
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [ordered]@{
        status = $Status
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        values_printed = $false
        creates_resources = $false
        uploads_obs_objects = $false
        submits_mrs_job = $false
        network_calls = 0
        write_calls = 0
        obs_bucket_name = $ObsBucketName
        reason = $Message
        message = $Message
        next_action = $NextAction
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$tfDir = Resolve-Path (Join-Path $scriptDir "..\terraform")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\pre_apply_readiness"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not $ObsBucketName) {
    $ObsBucketName = if ($env:TF_VAR_obs_bucket_name) { $env:TF_VAR_obs_bucket_name } else { New-BucketName -Prefix $BucketPrefix }
}
if (-not $NodeKeyPairName -and $env:TF_VAR_node_key_pair_name) {
    $NodeKeyPairName = $env:TF_VAR_node_key_pair_name
}
if (-not $PromptFile) {
    $PromptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"
}

$credentialStatusPath = Join-Path $root ".cloud_real_bigdata_work\credential_status\credential_status_latest.json"
$applySafetyPath = Join-Path $root ".cloud_real_bigdata_work\apply_safety\apply_safety_latest.json"
$lifecycleGuardPath = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"
$minimalPlanPath = Join-Path $root ".cloud_real_bigdata_work\minimal_cost_quota_plan\minimal_cost_quota_plan_latest.json"
$readonlyProbePath = Join-Path $root ".cloud_real_bigdata_work\readonly_probe\readonly_probe_latest.json"
$preflightPath = Join-Path $root ".cloud_real_bigdata_work\real_cloud_preflight\real_cloud_preflight_latest.json"
$latestTracePath = Join-Path $root ".cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json"
$nodeKeyForCommand = if ($NodeKeyPairName) { $NodeKeyPairName } else { "<existing-key-pair>" }

$script:Gates = @()
$commands = [ordered]@{
    credential_status = ".\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1"
    minimal_cost_quota_plan = ".\cloud_real_bigdata\scripts\21_export_minimal_cost_quota_plan.ps1 -ObsBucketName `"$ObsBucketName`"$(if ($EnableWebEcs) { ' -EnableWebEcs' })$(if ($EnableDws) { ' -EnableDws' })$(if ($EnableDataArts) { ' -EnableDataArts' })"
    apply_safety = ".\cloud_real_bigdata\scripts\14_validate_apply_safety.ps1 -EnableWebEcs:$($EnableWebEcs.IsPresent) -Apply"
    lifecycle_guard = ".\cloud_real_bigdata\scripts\16_validate_lifecycle_guard.ps1 -Apply$(if ($AllowLongLivedDemo) { ' -AllowLongLivedDemo' })"
    readonly_probe = ".\cloud_real_bigdata\scripts\17_run_readonly_cloud_probe.ps1 -ObsBucketName `"$ObsBucketName`""
    validate_env = ".\cloud_real_bigdata\scripts\02_validate_env.ps1"
    preflight = ".\cloud_real_bigdata\scripts\10_real_cloud_preflight_plan.ps1 -ObsBucketName `"$ObsBucketName`" -NodeKeyPairName `"$nodeKeyForCommand`" -PromptFile `"$PromptFile`" -Scenario `"$Scenario`"$(if ($UseMaaS) { ' -UseMaaS' })$(if ($EnableWebEcs) { ' -EnableWebEcs' })$(if ($EnableDws) { ' -EnableDws' })$(if ($EnableDataArts) { ' -EnableDataArts' })$(if ($AllowOpenIngressForDemo) { ' -AllowOpenIngressForDemo' })$(if ($AllowLongLivedDemo) { ' -AllowLongLivedDemo' })"
    apply = ".\cloud_real_bigdata\scripts\05_run_real_e2e.ps1 -ObsBucketName `"$ObsBucketName`" -NodeKeyPairName `"$nodeKeyForCommand`" -PromptFile `"$PromptFile`" -Scenario `"$Scenario`"$(if ($UseMaaS) { ' -UseMaaS' })$(if ($EnableWebEcs) { ' -EnableWebEcs -SshKeyPath `"<path-to-private-key.pem>`"' })$(if ($EnableDws) { ' -EnableDws' })$(if ($EnableDataArts) { ' -EnableDataArts' })$(if ($AllowOpenIngressForDemo) { ' -AllowOpenIngressForDemo' })$(if ($AllowLongLivedDemo) { ' -AllowLongLivedDemo' }) -Apply"
}

Write-Host "SAT Agentic pre-apply readiness" -ForegroundColor Cyan
Write-Host "  bucket: $ObsBucketName"
Write-Host "  web ecs: $($EnableWebEcs.IsPresent)"
Write-Host "  dws: $($EnableDws.IsPresent)"
Write-Host "  dataarts: $($EnableDataArts.IsPresent)"
Write-Host "  long-lived demo override: $($AllowLongLivedDemo.IsPresent)"
Write-Host "  read-only cloud probe: $($RunReadonlyCloudProbe.IsPresent)"
Write-Host "  terraform preflight: $($RunTerraformPreflight.IsPresent)"
Write-Host ""

$minimalPlanRun = Invoke-Captured -Name "minimal_cost_quota_plan" -Block {
    $params = @{
        ObsBucketName = $ObsBucketName
    }
    if ($EnableWebEcs) { $params.EnableWebEcs = $true }
    if ($EnableDws) { $params.EnableDws = $true }
    if ($EnableDataArts) { $params.EnableDataArts = $true }
    & (Join-Path $scriptDir "21_export_minimal_cost_quota_plan.ps1") @params
}
$minimalPlan = Read-JsonFile $minimalPlanPath
if ($minimalPlanRun.succeeded -and $minimalPlan -and ([string]$minimalPlan.status -in @("ready_for_operator_review", "review_required"))) {
    $planStatus = [string]$minimalPlan.status
    $gateStatus = if ($planStatus -eq "review_required") { "warning" } else { "passed" }
    Add-Gate -Name "minimal_cost_quota_plan" -Status $gateStatus -Blocking $false -Detail "status=$planStatus; minimum_mode=$($minimalPlan.minimum_mode)" -EvidencePath $minimalPlanPath
}
else {
    $detail = if ($minimalPlan) { [string]$minimalPlan.next_action } else { $minimalPlanRun.output }
    Add-Gate -Name "minimal_cost_quota_plan" -Status "failed" -Blocking $true -Detail $detail -EvidencePath $minimalPlanPath
}

Invoke-Captured -Name "credential_status" -Block {
    & (Join-Path $scriptDir "12_configure_cloud_credentials.ps1")
} | Out-Null
$credentialStatus = Read-JsonFile $credentialStatusPath
if ($credentialStatus -and [string]$credentialStatus.status -eq "ready") {
    Add-Gate -Name "credentials" -Status "passed" -Detail "minimal cloud variables are configured" -EvidencePath $credentialStatusPath
}
else {
    $missing = if ($credentialStatus) { $credentialStatus.missing_required -join ", " } else { "credential status report missing" }
    Add-Gate -Name "credentials" -Status "warning" -Blocking $true -Detail "missing: $missing" -EvidencePath $credentialStatusPath
}

Invoke-Captured -Name "apply_safety" -Block {
    & (Join-Path $scriptDir "14_validate_apply_safety.ps1") `
        -EnableWebEcs:$EnableWebEcs `
        -Apply `
        -AllowOpenIngressForDemo:$AllowOpenIngressForDemo `
        -EmitReportOnly
} | Out-Null
$applySafety = Read-JsonFile $applySafetyPath
if ($applySafety -and [string]$applySafety.status -eq "passed") {
    Add-Gate -Name "apply_safety" -Status "passed" -Detail "admin_cidr=$($applySafety.admin_cidr)" -EvidencePath $applySafetyPath
}
elseif ($applySafety -and [string]$applySafety.status -eq "warning") {
    Add-Gate -Name "apply_safety" -Status "warning" -Blocking $false -Detail "admin_cidr=$($applySafety.admin_cidr); open ingress explicitly allowed for disposable demo" -EvidencePath $applySafetyPath
}
else {
    $detail = if ($applySafety) { "admin_cidr=$($applySafety.admin_cidr); $($applySafety.next_action)" } else { "apply safety report missing" }
    Add-Gate -Name "apply_safety" -Status "warning" -Blocking $true -Detail $detail -EvidencePath $applySafetyPath
}

Invoke-Captured -Name "lifecycle_guard" -Block {
    & (Join-Path $scriptDir "16_validate_lifecycle_guard.ps1") `
        -Apply `
        -AllowLongLivedDemo:$AllowLongLivedDemo `
        -EmitReportOnly
} | Out-Null
$lifecycleGuard = Read-JsonFile $lifecycleGuardPath
if ($lifecycleGuard -and [string]$lifecycleGuard.status -eq "passed") {
    Add-Gate -Name "lifecycle_guard" -Status "passed" -Detail "owner=$($lifecycleGuard.demo_owner); expires_at=$($lifecycleGuard.demo_expires_at)" -EvidencePath $lifecycleGuardPath
}
elseif ($lifecycleGuard -and [string]$lifecycleGuard.status -eq "warning") {
    Add-Gate -Name "lifecycle_guard" -Status "warning" -Blocking $false -Detail "owner=$($lifecycleGuard.demo_owner); expires_at=$($lifecycleGuard.demo_expires_at); long-lived explicitly allowed" -EvidencePath $lifecycleGuardPath
}
else {
    $detail = if ($lifecycleGuard) { $lifecycleGuard.next_action } else { "lifecycle guard report missing" }
    Add-Gate -Name "lifecycle_guard" -Status "warning" -Blocking $true -Detail $detail -EvidencePath $lifecycleGuardPath
}

$tfValidate = Invoke-Captured -Name "terraform_validate" -Block {
    Push-Location $tfDir
    try {
        terraform validate
        if ($LASTEXITCODE -ne 0) { throw "terraform validate failed" }
    }
    finally {
        Pop-Location
    }
}
if ($tfValidate.succeeded) {
    Add-Gate -Name "terraform_validate" -Status "passed" -Detail "Terraform configuration validates"
}
else {
    Add-Gate -Name "terraform_validate" -Status "failed" -Blocking $true -Detail $tfValidate.output
}

$envValidate = Invoke-Captured -Name "environment_validate" -Block {
    & (Join-Path $scriptDir "02_validate_env.ps1") -RequireDws:$EnableDws
}
if ($envValidate.succeeded) {
    Add-Gate -Name "environment_validate" -Status "passed" -Detail "tools, SDKs, and required env vars passed"
}
else {
    Add-Gate -Name "environment_validate" -Status "warning" -Blocking $true -Detail $envValidate.output
}

$canRunCloudProbe = @($script:Gates | Where-Object { $_.blocking -and $_.status -ne "passed" }).Count -eq 0
if ($RunReadonlyCloudProbe) {
    if ($canRunCloudProbe) {
        $probeRun = Invoke-Captured -Name "readonly_cloud_probe" -Block {
            & (Join-Path $scriptDir "17_run_readonly_cloud_probe.ps1") -ObsBucketName $ObsBucketName
        }
        $probe = Read-JsonFile $readonlyProbePath
        if ($probeRun.succeeded -and $probe -and [string]$probe.status -eq "passed") {
            Add-Gate -Name "readonly_cloud_probe" -Status "passed" -Detail "read-only cloud API checks passed" -EvidencePath $readonlyProbePath
        }
        else {
            $detail = if ($probe) { [string]$probe.reason } else { $probeRun.output }
            Add-Gate -Name "readonly_cloud_probe" -Status "failed" -Blocking $true -Detail $detail -EvidencePath $readonlyProbePath
        }
    }
    else {
        $detail = "Skipped until blocking local readiness gates pass"
        Write-LightweightStatusReport -Path $readonlyProbePath -Status "skipped" -Message $detail -NextAction "Fix blocking readiness gates, then rerun with -RunReadonlyCloudProbe."
        Add-Gate -Name "readonly_cloud_probe" -Status "skipped" -Blocking $false -Detail $detail -EvidencePath $readonlyProbePath
    }
}
else {
    $probe = Read-JsonFile $readonlyProbePath
    if ($probe -and [string]$probe.status -eq "passed") {
        Add-Gate -Name "readonly_cloud_probe" -Status "passed" -Detail "existing read-only probe report has passed" -EvidencePath $readonlyProbePath
    }
    else {
        $detail = "Pass -RunReadonlyCloudProbe after credentials and safety are ready"
        Write-LightweightStatusReport -Path $readonlyProbePath -Status "not_run" -Message $detail -NextAction $commands.readonly_probe
        Add-Gate -Name "readonly_cloud_probe" -Status "not_run" -Blocking $false -Detail $detail -EvidencePath $readonlyProbePath
    }
}

$canRunPreflight = @($script:Gates | Where-Object { $_.blocking -and $_.status -ne "passed" }).Count -eq 0
if ($RunTerraformPreflight) {
    if ($canRunPreflight) {
        $preflightRun = Invoke-Captured -Name "terraform_preflight" -Block {
            $params = @{
                ObsBucketName = $ObsBucketName
                NodeKeyPairName = $NodeKeyPairName
                PromptFile = $PromptFile
                Scenario = $Scenario
            }
            if ($UseMaaS) { $params.UseMaaS = $true }
            if ($EnableWebEcs) { $params.EnableWebEcs = $true }
            if ($EnableDws) { $params.EnableDws = $true }
            if ($EnableDataArts) { $params.EnableDataArts = $true }
            if ($AllowOpenIngressForDemo) { $params.AllowOpenIngressForDemo = $true }
            if ($AllowLongLivedDemo) { $params.AllowLongLivedDemo = $true }
            & (Join-Path $scriptDir "10_real_cloud_preflight_plan.ps1") @params
        }
        $preflight = Read-JsonFile $preflightPath
        if ($preflightRun.succeeded -and $preflight -and [string]$preflight.status -eq "passed") {
            Add-Gate -Name "terraform_preflight" -Status "passed" -Detail "real cloud Terraform plan completed without apply" -EvidencePath $preflightPath
        }
        else {
            $detail = if ($preflight) { [string]$preflight.message } else { $preflightRun.output }
            Add-Gate -Name "terraform_preflight" -Status "failed" -Blocking $true -Detail $detail -EvidencePath $preflightPath
        }
    }
    else {
        $detail = "Skipped until blocking readiness gates pass"
        Write-LightweightStatusReport -Path $preflightPath -Status "skipped" -Message $detail -NextAction "Fix blocking readiness gates, then rerun with -RunTerraformPreflight."
        Add-Gate -Name "terraform_preflight" -Status "skipped" -Blocking $false -Detail $detail -EvidencePath $preflightPath
    }
}
else {
    $preflight = Read-JsonFile $preflightPath
    if ($preflight -and [string]$preflight.status -eq "passed") {
        Add-Gate -Name "terraform_preflight" -Status "passed" -Detail "existing preflight report has passed" -EvidencePath $preflightPath
    }
    else {
        $detail = "Pass -RunTerraformPreflight after credentials and safety are ready"
        Write-LightweightStatusReport -Path $preflightPath -Status "not_run" -Message $detail -NextAction $commands.preflight
        Add-Gate -Name "terraform_preflight" -Status "not_run" -Blocking $false -Detail $detail -EvidencePath $preflightPath
    }
}

$failed = @($script:Gates | Where-Object { $_.status -eq "failed" })
$blockingOpen = @($script:Gates | Where-Object { $_.blocking -and $_.status -ne "passed" })
$preflightGate = $script:Gates | Where-Object { $_.name -eq "terraform_preflight" } | Select-Object -First 1
$finalStatus = if ($failed.Count -gt 0) {
    "failed"
}
elseif ($blockingOpen.Count -gt 0) {
    "pending_readiness"
}
elseif ($preflightGate -and $preflightGate.status -eq "passed") {
    "ready_for_apply"
}
else {
    "ready_for_real_cloud_preflight"
}

$report = [ordered]@{
    status = $finalStatus
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = $false
    uploads_obs_objects = $false
    submits_mrs_job = $false
    options = [ordered]@{
        obs_bucket_name = $ObsBucketName
        prompt_file = $PromptFile
        scenario = $Scenario
        use_maas = [bool]$UseMaaS
        enable_web_ecs = [bool]$EnableWebEcs
        enable_dws = [bool]$EnableDws
        enable_dataarts = [bool]$EnableDataArts
        allow_open_ingress_for_demo = [bool]$AllowOpenIngressForDemo
        allow_long_lived_demo = [bool]$AllowLongLivedDemo
        run_readonly_cloud_probe = [bool]$RunReadonlyCloudProbe
        run_terraform_preflight = [bool]$RunTerraformPreflight
    }
    gates = $script:Gates
    paths = [ordered]@{
        credential_status = $credentialStatusPath
        minimal_cost_quota_plan = $minimalPlanPath
        apply_safety = $applySafetyPath
        lifecycle_guard = $lifecycleGuardPath
        readonly_probe = $readonlyProbePath
        preflight = $preflightPath
        latest_trace = $latestTracePath
    }
    commands = $commands
    next_action = if ($finalStatus -eq "ready_for_apply") {
        $commands.apply
    }
    elseif ($finalStatus -eq "ready_for_real_cloud_preflight") {
        $commands.preflight
    }
    elseif ($finalStatus -eq "pending_readiness") {
        "Fix blocking readiness gates, then rerun 15_pre_apply_readiness.ps1 -EnableWebEcs -RunReadonlyCloudProbe -RunTerraformPreflight."
    }
    else {
        "Fix failed readiness gates before running real cloud preflight or apply."
    }
}

$jsonPath = Join-Path $OutputDir "pre_apply_readiness_latest.json"
$mdPath = Join-Path $OutputDir "pre_apply_readiness.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# SAT Agentic Pre-Apply Readiness",
    "",
    "- status: $($report.status)",
    "- generated_at: $($report.generated_at)",
    "- creates_resources: false",
    "- uploads_obs_objects: false",
    "- submits_mrs_job: false",
    "- obs_bucket_name: $($report.options.obs_bucket_name)",
    "- values_printed: false",
    "",
    "## Gates",
    ""
)
$md += Render-MarkdownTable $script:Gates
$md += @(
    "",
    "## Next Action",
    "",
    '```powershell',
    $report.next_action,
    '```'
)
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

foreach ($gate in $script:Gates) {
    $color = switch ($gate.status) {
        "passed" { "Green" }
        "warning" { "Yellow" }
        "skipped" { "Yellow" }
        "not_run" { "Yellow" }
        default { "Red" }
    }
    Write-Host "[$($gate.status)] $($gate.name) - $($gate.detail)" -ForegroundColor $color
}
Write-Host ""
Write-Host "Readiness JSON: $jsonPath"
Write-Host "Readiness report: $mdPath"
Write-Host "Final status: $finalStatus" -ForegroundColor ($(if ($finalStatus -eq "failed") { "Red" } elseif ($finalStatus -like "pending*") { "Yellow" } else { "Green" }))

if ($finalStatus -eq "failed") {
    exit 1
}
