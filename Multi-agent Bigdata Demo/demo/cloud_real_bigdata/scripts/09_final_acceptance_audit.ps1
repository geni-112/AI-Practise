param(
    [string]$BaseUrl = "http://127.0.0.1:8788",

    [string]$OutputDir = "",

    [switch]$RequireCloudSuccess
)

$ErrorActionPreference = "Stop"

function Add-Check {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )
    $script:Checks += [ordered]@{
        id = $Id
        name = $Name
        status = $Status
        detail = $Detail
    }
}

function Test-Configured {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "User") }
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine") }
    return [bool]$value
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
        Add-Check "JSON-001" "Readable JSON: $Path" "failed" $_.Exception.Message
        return $null
    }
}

function Invoke-JsonGet {
    param([string]$Url)
    try {
        return Invoke-RestMethod -Method Get -Uri $Url -Headers @{ "Cache-Control" = "no-cache" } -TimeoutSec 8
    }
    catch {
        Add-Check "WEB-000" "Website API reachable: $Url" "warning" $_.Exception.Message
        return $null
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\acceptance_audit"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

$script:Checks = @()
$startedAt = (Get-Date).ToUniversalTime().ToString("o")
$publicEvidenceDir = Join-Path $root "cloud_real_bigdata\public_evidence"
$latestEvidencePath = Join-Path $publicEvidenceDir "latest_e2e_result.json"
$customerSummaryPath = Join-Path $publicEvidenceDir "customer_demo_summary.json"
$customerHtmlPath = Join-Path $publicEvidenceDir "customer_demo_report.html"
$customerMarkdownPath = Join-Path $publicEvidenceDir "customer_demo_report.md"
$preflightPath = Join-Path $root ".cloud_real_bigdata_work\real_cloud_preflight\real_cloud_preflight_latest.json"
$latestTracePath = Join-Path $root ".cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json"
$operatorHandoffPath = Join-Path $root ".cloud_real_bigdata_work\operator_handoff\operator_handoff_summary.json"
$credentialStatusPath = Join-Path $root ".cloud_real_bigdata_work\credential_status\credential_status_latest.json"
$applySafetyPath = Join-Path $root ".cloud_real_bigdata_work\apply_safety\apply_safety_latest.json"
$lifecycleGuardPath = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"
$minimalPlanPath = Join-Path $root ".cloud_real_bigdata_work\minimal_cost_quota_plan\minimal_cost_quota_plan_latest.json"
$readonlyProbePath = Join-Path $root ".cloud_real_bigdata_work\readonly_probe\readonly_probe_latest.json"
$preApplyReadinessPath = Join-Path $root ".cloud_real_bigdata_work\pre_apply_readiness\pre_apply_readiness_latest.json"
$operatorBootstrapPath = Join-Path $root ".cloud_real_bigdata_work\operator_bootstrap\operator_bootstrap_latest.json"
$customerDemoOncePath = Join-Path $root ".cloud_real_bigdata_work\customer_demo_once\customer_demo_once_latest.json"
$customerHandoffPath = Join-Path $root ".cloud_real_bigdata_work\customer_handoff\customer_handoff_latest.json"
$customerCommercialPath = Join-Path $root ".cloud_real_bigdata_work\customer_commercial_readiness\customer_commercial_readiness_latest.json"
$webDeployManifestPath = Join-Path $root ".cloud_real_bigdata_work\web_deploy\web_deploy_manifest.json"
$webDiagnosticsPath = Join-Path $root ".cloud_real_bigdata_work\web_diagnostics\web_diagnostics_latest.json"

Write-Host "SAT Agentic final acceptance audit" -ForegroundColor Cyan
Write-Host "  mode: $($(if ($RequireCloudSuccess) { 'require cloud success' } else { 'preflight allowed' }))"
Write-Host "  base url: $BaseUrl"
Write-Host ""

$requiredFiles = @(
    "cloud_real_bigdata\scripts\05_run_real_e2e.ps1",
    "cloud_real_bigdata\scripts\04_destroy.ps1",
    "cloud_real_bigdata\scripts\07_verify_customer_demo.ps1",
    "cloud_real_bigdata\scripts\08_prepare_minimal_run.ps1",
    "cloud_real_bigdata\scripts\export_customer_demo_package.py",
    "cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1",
    "cloud_real_bigdata\scripts\13_diagnose_web_ecs.ps1",
    "cloud_real_bigdata\scripts\14_validate_apply_safety.ps1",
    "cloud_real_bigdata\scripts\15_pre_apply_readiness.ps1",
    "cloud_real_bigdata\scripts\16_validate_lifecycle_guard.ps1",
    "cloud_real_bigdata\scripts\17_run_readonly_cloud_probe.ps1",
    "cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1",
    "cloud_real_bigdata\scripts\19_run_customer_demo_once.ps1",
    "cloud_real_bigdata\scripts\20_export_customer_handoff.ps1",
    "cloud_real_bigdata\scripts\21_export_minimal_cost_quota_plan.ps1",
    "cloud_real_bigdata\scripts\22_validate_customer_commercial_readiness.ps1",
    "cloud_real_bigdata\scripts\readonly_cloud_probe.py",
    "cloud_real_bigdata\terraform\main.tf",
    "cloud_real_bigdata\terraform\variables.tf",
    "cloud_real_bigdata\terraform\outputs.tf",
    "cloud_real_bigdata\examples\sat_prompt.txt",
    "app\main.py",
    "static\app.js"
)
foreach ($relative in $requiredFiles) {
    $path = Join-Path $root $relative
    if (Test-Path -LiteralPath $path) {
        Add-Check "FILE" "Required file exists: $relative" "passed" "present"
    }
    else {
        Add-Check "FILE" "Required file exists: $relative" "failed" "missing"
    }
}

$parseErrors = @()
Get-ChildItem (Join-Path $root "cloud_real_bigdata\scripts\*.ps1") | ForEach-Object {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) {
        $parseErrors += "$($_.Name): $($errors[0].Message)"
    }
}
if ($parseErrors.Count -eq 0) {
    Add-Check "STATIC-PS" "PowerShell scripts parse" "passed" "all cloud scripts parse"
}
else {
    Add-Check "STATIC-PS" "PowerShell scripts parse" "failed" ($parseErrors -join "; ")
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
$compileOutput = & $python -m compileall (Join-Path $root "app") (Join-Path $root "cloud_real_bigdata\scripts") (Join-Path $root "cloud_real_bigdata\spark") 2>&1
if ($LASTEXITCODE -eq 0) {
    Add-Check "STATIC-PY" "Python modules compile" "passed" "app and cloud scripts compile"
}
else {
    Add-Check "STATIC-PY" "Python modules compile" "failed" (($compileOutput | Out-String).Trim())
}

$terraform = Get-Command terraform -ErrorAction SilentlyContinue
if ($terraform) {
    Push-Location (Join-Path $root "cloud_real_bigdata\terraform")
    try {
        $tfOutput = terraform validate 2>&1
        if ($LASTEXITCODE -eq 0) {
            Add-Check "STATIC-TF" "Terraform validates" "passed" "configuration is valid"
        }
        else {
            Add-Check "STATIC-TF" "Terraform validates" "failed" (($tfOutput | Out-String).Trim())
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Add-Check "STATIC-TF" "Terraform validates" "failed" "terraform command not found"
}

$missingEnv = @()
foreach ($name in @(
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "TF_VAR_mrs_manager_admin_password",
    "TF_VAR_node_key_pair_name"
)) {
    if (-not (Test-Configured $name)) {
        $missingEnv += $name
    }
}
if ($missingEnv.Count -eq 0) {
    Add-Check "ENV" "Real cloud environment variables" "passed" "required variables are present"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "ENV" "Real cloud environment variables" $status ("missing: " + ($missingEnv -join ", "))
}

$credentialStatus = Read-JsonFile $credentialStatusPath
if ($credentialStatus) {
    $credentialCheckStatus = if ([string]$credentialStatus.status -eq "ready") { "passed" } else { "warning" }
    Add-Check "CREDENTIALS" "Non-secret credential status report" $credentialCheckStatus "status=$($credentialStatus.status); missing=$($credentialStatus.missing_required -join ', '); report=$credentialStatusPath"
}
else {
    Add-Check "CREDENTIALS" "Non-secret credential status report" "warning" "not run: .\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1"
}

$applySafetyStatusForDecision = "not_run"
$applySafety = Read-JsonFile $applySafetyPath
if ($applySafety) {
    $applySafetyRawStatus = [string]$applySafety.status
    $applySafetyBlocking = @($applySafety.checks | Where-Object { [bool]$_.blocking }).Count -gt 0
    $openAdminIngress = [string]$applySafety.admin_cidr -in @("0.0.0.0/0", "::/0")
    $applySafetyStatusForDecision = if (
        $applySafetyRawStatus -eq "warning" -and
        -not $applySafetyBlocking -and
        -not $openAdminIngress
    ) {
        "passed"
    }
    else {
        $applySafetyRawStatus
    }
    $applySafetyCheckStatus = if ($applySafetyStatusForDecision -eq "passed") {
        "passed"
    }
    elseif ($RequireCloudSuccess) {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "APPLY-SAFETY" "Apply safety gate" $applySafetyCheckStatus "status=$applySafetyStatusForDecision; raw_status=$applySafetyRawStatus; admin_cidr=$($applySafety.admin_cidr); web_cidr=$($applySafety.web_cidr); blocking=$applySafetyBlocking; report=$applySafetyPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "APPLY-SAFETY" "Apply safety gate" $status "not run: .\cloud_real_bigdata\scripts\14_validate_apply_safety.ps1 -EnableWebEcs -Apply"
}

$lifecycleStatusForDecision = "not_run"
$lifecycleGuard = Read-JsonFile $lifecycleGuardPath
if ($lifecycleGuard) {
    $lifecycleStatusForDecision = [string]$lifecycleGuard.status
    $lifecycleCheckStatus = if ($lifecycleStatusForDecision -eq "passed") {
        "passed"
    }
    elseif ($RequireCloudSuccess) {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "LIFECYCLE" "Lifecycle cleanup gate" $lifecycleCheckStatus "status=$lifecycleStatusForDecision; owner=$($lifecycleGuard.demo_owner); expires_at=$($lifecycleGuard.demo_expires_at); report=$lifecycleGuardPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "LIFECYCLE" "Lifecycle cleanup gate" $status "not run: .\cloud_real_bigdata\scripts\16_validate_lifecycle_guard.ps1 -Apply"
}

$minimalPlanStatusForDecision = "not_run"
$minimalPlan = Read-JsonFile $minimalPlanPath
if ($minimalPlan) {
    $minimalPlanStatusForDecision = [string]$minimalPlan.status
    $minimalPlanCheckStatus = if ($minimalPlanStatusForDecision -in @("ready_for_operator_review", "review_required")) {
        "passed"
    }
    elseif ($RequireCloudSuccess -or $minimalPlanStatusForDecision -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "RESOURCE-PLAN" "Minimal cost and quota plan" $minimalPlanCheckStatus "status=$minimalPlanStatusForDecision; minimum_mode=$($minimalPlan.minimum_mode); report=$minimalPlanPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "RESOURCE-PLAN" "Minimal cost and quota plan" $status "not run: .\cloud_real_bigdata\scripts\21_export_minimal_cost_quota_plan.ps1 -EnableWebEcs"
}

$readonlyProbe = Read-JsonFile $readonlyProbePath
if ($readonlyProbe) {
    $probeStatus = [string]$readonlyProbe.status
    $checkStatus = if ($probeStatus -eq "passed") {
        "passed"
    }
    elseif ($RequireCloudSuccess -or $probeStatus -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "READONLY-PROBE" "Huawei Cloud read-only API probe" $checkStatus "status=$probeStatus; network_calls=$($readonlyProbe.network_calls); report=$readonlyProbePath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "READONLY-PROBE" "Huawei Cloud read-only API probe" $status "not run: .\cloud_real_bigdata\scripts\17_run_readonly_cloud_probe.ps1"
}

$preflight = Read-JsonFile $preflightPath
$preflightStatusForDecision = "not_run"
if ($preflight) {
    $preflightStatus = [string]$preflight.status
    $preflightStatusForDecision = $preflightStatus
    Add-Check "PREFLIGHT" "Real-cloud plan preflight" ($(if ($preflightStatus -eq "passed") { "passed" } else { "warning" })) "status=$preflightStatus; creates_resources=$($preflight.creates_resources); report=$preflightPath"
}
else {
    Add-Check "PREFLIGHT" "Real-cloud plan preflight" "warning" "not run: $preflightPath"
}

$readinessStatusForDecision = "not_run"
$readiness = Read-JsonFile $preApplyReadinessPath
if ($readiness) {
    $readinessStatusForDecision = [string]$readiness.status
    $readinessCheckStatus = if ($readinessStatusForDecision -in @("ready_for_apply", "ready_for_real_cloud_preflight")) {
        "passed"
    }
    elseif ($RequireCloudSuccess -or $readinessStatusForDecision -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "READINESS" "Pre-apply readiness gate" $readinessCheckStatus "status=$readinessStatusForDecision; report=$preApplyReadinessPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "READINESS" "Pre-apply readiness gate" $status "not run: .\cloud_real_bigdata\scripts\15_pre_apply_readiness.ps1 -EnableWebEcs"
}

$operatorBootstrap = Read-JsonFile $operatorBootstrapPath
if ($operatorBootstrap) {
    $bootstrapStatus = [string]$operatorBootstrap.status
    $bootstrapCheckStatus = if ($bootstrapStatus -in @("ready_for_apply", "ready_for_real_cloud_preflight")) {
        "passed"
    }
    elseif ($RequireCloudSuccess -or $bootstrapStatus -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "BOOTSTRAP" "Operator bootstrap wrapper" $bootstrapCheckStatus "status=$bootstrapStatus; creates_resources=$($operatorBootstrap.creates_resources); report=$operatorBootstrapPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "BOOTSTRAP" "Operator bootstrap wrapper" $status "not run: .\cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1"
}

$customerDemoOnce = Read-JsonFile $customerDemoOncePath
if ($customerDemoOnce) {
    $demoOnceStatus = [string]$customerDemoOnce.status
    $demoOnceCheckStatus = if ($demoOnceStatus -eq "ready_for_customer_demo") {
        "passed"
    }
    else {
        "warning"
    }
    Add-Check "DEMO-ONCE" "Customer demo once wrapper" $demoOnceCheckStatus "status=$demoOnceStatus; creates_resources=$($customerDemoOnce.creates_resources); report=$customerDemoOncePath"
}
else {
    Add-Check "DEMO-ONCE" "Customer demo once wrapper" "warning" "not run: .\cloud_real_bigdata\scripts\19_run_customer_demo_once.ps1"
}

$customerHandoff = Read-JsonFile $customerHandoffPath
if ($customerHandoff) {
    $handoffStatus = [string]$customerHandoff.status
    $handoffCheckStatus = if ($handoffStatus -eq "ready_for_customer_handoff") {
        "passed"
    }
    else {
        "warning"
    }
    Add-Check "HANDOFF" "Customer handoff package" $handoffCheckStatus "status=$handoffStatus; report=$customerHandoffPath"
}
else {
    Add-Check "HANDOFF" "Customer handoff package" "warning" "not run: .\cloud_real_bigdata\scripts\20_export_customer_handoff.ps1"
}

$customerCommercial = Read-JsonFile $customerCommercialPath
if ($customerCommercial) {
    $commercialStatus = [string]$customerCommercial.status
    $commercialCheckStatus = if ($commercialStatus -in @("ready_for_customer_demo", "ready_for_commercial_pilot")) {
        "passed"
    }
    elseif ($RequireCloudSuccess -and $commercialStatus -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "CUSTOMER-COMMERCIAL" "Customer/commercial readiness" $commercialCheckStatus "status=$commercialStatus; demo_ready=$($customerCommercial.demo_ready); commercial_ready=$($customerCommercial.commercial_ready); report=$customerCommercialPath"
}
else {
    $status = if ($RequireCloudSuccess) { "warning" } else { "warning" }
    Add-Check "CUSTOMER-COMMERCIAL" "Customer/commercial readiness" $status "not run: .\cloud_real_bigdata\scripts\22_validate_customer_commercial_readiness.ps1 -BaseUrl `"$BaseUrl`""
}

$latestTrace = Read-JsonFile $latestTracePath
if ($latestTrace) {
    $traceStatus = [string]$latestTrace.status
    $traceMode = [string]$latestTrace.mode
    $traceRunId = [string]$latestTrace.outputs.run_id
    $traceCheckStatus = if ($traceStatus -in @("completed", "planned")) { "passed" } else { "warning" }
    Add-Check "TRACE" "Latest E2E operator trace" $traceCheckStatus "status=$traceStatus; mode=$traceMode; run_id=$traceRunId; path=$latestTracePath"
}
else {
    Add-Check "TRACE" "Latest E2E operator trace" "warning" "not found: $latestTracePath"
}

$operatorHandoff = Read-JsonFile $operatorHandoffPath
if ($operatorHandoff) {
    Add-Check "HANDOFF" "Operator handoff package" "passed" "status=$($operatorHandoff.status); path=$operatorHandoffPath"
}
else {
    Add-Check "HANDOFF" "Operator handoff package" "warning" "not found: $operatorHandoffPath"
}

$webDeployManifest = Read-JsonFile $webDeployManifestPath
if ($webDeployManifest) {
    $deployStatus = [string]$webDeployManifest.status
    Add-Check "WEB-DEPLOY" "Web ECS deploy manifest" ($(if ($deployStatus -eq "deployed") { "passed" } else { "failed" })) "status=$deployStatus; target=$($webDeployManifest.target_url); path=$webDeployManifestPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "WEB-DEPLOY" "Web ECS deploy manifest" $status "not found: $webDeployManifestPath"
}

$webDiagnostics = Read-JsonFile $webDiagnosticsPath
if ($webDiagnostics) {
    $diagStatus = [string]$webDiagnostics.status
    $checkStatus = if ($diagStatus -eq "ready_for_customer_demo") {
        "passed"
    }
    elseif ($RequireCloudSuccess -or $diagStatus -eq "failed") {
        "failed"
    }
    else {
        "warning"
    }
    Add-Check "WEB-DIAG" "Web ECS diagnostics" $checkStatus "status=$diagStatus; failed_critical=$($webDiagnostics.failed_critical_count); path=$webDiagnosticsPath"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "WEB-DIAG" "Web ECS diagnostics" $status "not found: $webDiagnosticsPath"
}

$evidence = Read-JsonFile $latestEvidencePath
if ($evidence) {
    $jobStatus = [string]$evidence.job.terminal_status
    Add-Check "EVIDENCE-001" "Latest cloud evidence exists" "passed" $latestEvidencePath
    Add-Check "EVIDENCE-002" "MRS job succeeded" ($(if ($jobStatus -eq "success") { "passed" } else { "failed" })) "status=$jobStatus"
    Add-Check "EVIDENCE-003" "Gold output is non-empty" ($(if ([int]$evidence.gold_row_count -gt 0) { "passed" } else { "failed" })) "gold_row_count=$($evidence.gold_row_count)"
    Add-Check "EVIDENCE-004" "Direct RFC is not exposed" ($(if (-not [bool]$evidence.direct_rfc_exposed) { "passed" } else { "failed" })) "direct_rfc_exposed=$($evidence.direct_rfc_exposed)"
    Add-Check "EVIDENCE-005" "DuckDB is not used" ($(if (-not [bool]$evidence.duckdb_used) { "passed" } else { "failed" })) "duckdb_used=$($evidence.duckdb_used)"
    Add-Check "EVIDENCE-006" "Prompt-to-artifact link exists" ($(if ($evidence.agent_run_id) { "passed" } else { "warning" })) "agent_run_id=$($evidence.agent_run_id)"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "EVIDENCE-001" "Latest cloud evidence exists" $status "not found: $latestEvidencePath"
}

$summary = Read-JsonFile $customerSummaryPath
if ($summary) {
    Add-Check "REPORT-001" "Customer demo summary exists" "passed" $customerSummaryPath
    Add-Check "REPORT-002" "Customer demo summary is ready" ($(if ($summary.status -eq "ready_for_customer_demo") { "passed" } else { "failed" })) "status=$($summary.status)"
    Add-Check "REPORT-003" "Customer summary has gold rows" ($(if ([int]$summary.gold_row_count -gt 0) { "passed" } else { "failed" })) "gold_row_count=$($summary.gold_row_count)"
}
else {
    $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
    Add-Check "REPORT-001" "Customer demo summary exists" $status "not found: $customerSummaryPath"
}
foreach ($path in @($customerHtmlPath, $customerMarkdownPath)) {
    $name = Split-Path -Leaf $path
    if (Test-Path -LiteralPath $path) {
        Add-Check "REPORT-FILE" "Customer report file exists: $name" "passed" $path
    }
    else {
        $status = if ($RequireCloudSuccess) { "failed" } else { "warning" }
        Add-Check "REPORT-FILE" "Customer report file exists: $name" $status "not found"
    }
}

$base = $BaseUrl.TrimEnd("/")
$health = Invoke-JsonGet "$base/api/health"
if ($health) {
    Add-Check "WEB-001" "Website health endpoint" ($(if ([bool]$health.ok) { "passed" } else { "failed" })) "ok=$($health.ok); bigdata_deployed=$($health.bigdata_deployed)"
}
$apiEvidence = Invoke-JsonGet "$base/api/cloud/e2e-evidence"
if ($apiEvidence) {
    if ($RequireCloudSuccess) {
        Add-Check "WEB-002" "Website exposes successful cloud evidence" ($(if ($apiEvidence.available -and $apiEvidence.status -eq "success") { "passed" } else { "failed" })) "available=$($apiEvidence.available); status=$($apiEvidence.status)"
    }
    else {
        Add-Check "WEB-002" "Website cloud evidence endpoint responds" "passed" "available=$($apiEvidence.available); status=$($apiEvidence.status)"
    }
}
$goldQueryApi = Invoke-JsonGet "$base/api/cloud/gold-query"
if ($goldQueryApi) {
    if ($RequireCloudSuccess) {
        Add-Check "WEB-003" "Website exposes queryable gold result" ($(if ($goldQueryApi.available -and [int]$goldQueryApi.filtered_count -gt 0) { "passed" } else { "failed" })) "available=$($goldQueryApi.available); filtered_count=$($goldQueryApi.filtered_count)"
    }
    else {
        Add-Check "WEB-003" "Website gold query endpoint responds" "passed" "available=$($goldQueryApi.available); filtered_count=$($goldQueryApi.filtered_count)"
    }
}

$failed = @($script:Checks | Where-Object { $_.status -eq "failed" })
$warnings = @($script:Checks | Where-Object { $_.status -eq "warning" })
$finalStatus = if ($failed.Count -gt 0) {
    "failed"
}
elseif ($RequireCloudSuccess) {
    "ready_for_customer_demo"
}
elseif ($missingEnv.Count -gt 0 -or $preflightStatusForDecision -ne "passed" -or $applySafetyStatusForDecision -ne "passed" -or $lifecycleStatusForDecision -ne "passed" -or $minimalPlanStatusForDecision -notin @("ready_for_operator_review", "review_required")) {
    "pending_cloud_preflight"
}
else {
    "ready_for_real_apply"
}

$report = [ordered]@{
    status = $finalStatus
    mode = if ($RequireCloudSuccess) { "require_cloud_success" } else { "preflight_allowed" }
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    started_at = $startedAt
    base_url = $base
    failed_count = $failed.Count
    warning_count = $warnings.Count
    checks = $script:Checks
    next_action = if ($finalStatus -eq "ready_for_customer_demo") {
        "Use the website and customer_demo_report.html for customer demonstration."
    }
    elseif ($finalStatus -eq "ready_for_real_apply") {
        "Run 05_run_real_e2e.ps1 -Apply, then rerun this audit with -RequireCloudSuccess."
    }
    elseif ($finalStatus -eq "pending_cloud_preflight") {
        "Run 18_bootstrap_operator_session.ps1 -ConfigureCredentials -PersistUserEnv -SetGuardDefaults -DetectAdminCidr -EnableWebEcs -RunTerraformPreflight."
    }
    else {
        "Fix failed checks before customer demonstration."
    }
}

$jsonPath = Join-Path $OutputDir "final_acceptance_audit.json"
$mdPath = Join-Path $OutputDir "final_acceptance_audit.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = @(
    "# SAT Agentic Final Acceptance Audit",
    "",
    "- status: $($report.status)",
    "- mode: $($report.mode)",
    "- base_url: $($report.base_url)",
    "- failed_count: $($report.failed_count)",
    "- warning_count: $($report.warning_count)",
    "",
    "## Checks",
    "",
    "| status | id | name | detail |",
    "| --- | --- | --- | --- |"
)
foreach ($check in $script:Checks) {
    $detail = ([string]$check.detail).Replace("|", "\|")
    $name = ([string]$check.name).Replace("|", "\|")
    $lines += "| $($check.status) | $($check.id) | $name | $detail |"
}
$lines += ""
$lines += "## Next Action"
$lines += ""
$lines += $report.next_action
$lines | Set-Content -LiteralPath $mdPath -Encoding UTF8

foreach ($check in $script:Checks) {
    $color = switch ($check.status) {
        "passed" { "Green" }
        "warning" { "Yellow" }
        default { "Red" }
    }
    Write-Host "[$($check.status)] $($check.name) - $($check.detail)" -ForegroundColor $color
}
Write-Host ""
Write-Host "Audit JSON: $jsonPath"
Write-Host "Audit report: $mdPath"
Write-Host "Final status: $finalStatus" -ForegroundColor ($(if ($finalStatus -eq "failed") { "Red" } else { "Green" }))

if ($failed.Count -gt 0) {
    exit 1
}
