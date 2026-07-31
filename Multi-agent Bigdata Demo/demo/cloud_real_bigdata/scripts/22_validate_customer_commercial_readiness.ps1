param(
    [string]$BaseUrl = "http://127.0.0.1:8788",

    [string]$DomainName = $env:TF_VAR_demo_domain,

    [switch]$HttpsEnabled,

    [switch]$IamLeastPrivilegeConfirmed,

    [switch]$MonitoringEnabled,

    [switch]$RemoteTerraformStateConfirmed,

    [int]$BackupRetentionDays = 0,

    [switch]$RetentionPolicyConfirmed,

    [string]$IncidentOwner = $env:TF_VAR_demo_owner,

    [switch]$ProductionSlaApproved,

    [switch]$RequireCommercial,

    [switch]$PublishToEvidence,

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

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

function Add-Check {
    param(
        [string]$Stage,
        [string]$Id,
        [string]$Name,
        [string]$Status,
        [string]$Detail,
        [bool]$Required = $true
    )
    $script:Checks += [ordered]@{
        stage = $Stage
        id = $Id
        name = $Name
        status = $Status
        required = $Required
        detail = $Detail
    }
}

function Bool-Status {
    param(
        [bool]$Value,
        [string]$PassedDetail,
        [string]$FailedDetail
    )
    if ($Value) {
        return @("passed", $PassedDetail)
    }
    return @("warning", $FailedDetail)
}

function Render-Table {
    param([array]$Rows)
    $lines = @(
        "| stage | status | required | id | name | detail |",
        "| --- | --- | --- | --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $detail = ([string]$row.detail).Replace("|", "\|").Replace("`r", " ").Replace("`n", "<br>")
        $name = ([string]$row.name).Replace("|", "\|")
        $lines += "| $($row.stage) | $($row.status) | $($row.required) | $($row.id) | $name | $detail |"
    }
    return $lines
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\customer_commercial_readiness"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$publicEvidenceDir = Join-Path $root "cloud_real_bigdata\public_evidence"
$evidencePath = Join-Path $publicEvidenceDir "latest_e2e_result.json"
$summaryPath = Join-Path $publicEvidenceDir "customer_demo_summary.json"
$handoffPath = Join-Path $root ".cloud_real_bigdata_work\customer_handoff\customer_handoff_latest.json"
$auditPath = Join-Path $root ".cloud_real_bigdata_work\acceptance_audit\final_acceptance_audit.json"
$webDiagPath = Join-Path $root ".cloud_real_bigdata_work\web_diagnostics\web_diagnostics_latest.json"
$webDeployPath = Join-Path $root ".cloud_real_bigdata_work\web_deploy\web_deploy_manifest.json"
$minimalPlanPath = Join-Path $root ".cloud_real_bigdata_work\minimal_cost_quota_plan\minimal_cost_quota_plan_latest.json"
$applySafetyPath = Join-Path $root ".cloud_real_bigdata_work\apply_safety\apply_safety_latest.json"
$lifecyclePath = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"

$evidence = Read-JsonFile $evidencePath
$summary = Read-JsonFile $summaryPath
$handoff = Read-JsonFile $handoffPath
$audit = Read-JsonFile $auditPath
$webDiag = Read-JsonFile $webDiagPath
$webDeploy = Read-JsonFile $webDeployPath
$minimalPlan = Read-JsonFile $minimalPlanPath
$applySafety = Read-JsonFile $applySafetyPath
$lifecycle = Read-JsonFile $lifecyclePath

$script:Checks = @()

$jobStatus = if ($evidence) { [string]$evidence.job.terminal_status } else { "not_run" }
$goldRows = if ($evidence -and $null -ne $evidence.gold_row_count) { [int]$evidence.gold_row_count } else { 0 }
$directRfcExposed = if ($evidence) { [bool]$evidence.direct_rfc_exposed } else { $true }
$duckdbUsed = if ($evidence) { [bool]$evidence.duckdb_used } else { $true }
$minimalPlanStatus = if ($minimalPlan) { [string]$minimalPlan.status } else { "not_run" }
$summaryStatus = if ($summary) { [string]$summary.status } else { "not_run" }
$handoffStatus = if ($handoff) { [string]$handoff.status } else { "not_run" }
$auditStatus = if ($audit) { [string]$audit.status } else { "not_run" }
$webDiagStatus = if ($webDiag) { [string]$webDiag.status } else { "not_run" }
$applySafetyStatus = if ($applySafety) { [string]$applySafety.status } else { "not_run" }
$applySafetyBlocking = if ($applySafety) { @($applySafety.checks | Where-Object { [bool]$_.blocking }).Count -gt 0 } else { $true }
$openAdminIngress = if ($applySafety) { [string]$applySafety.admin_cidr -in @("0.0.0.0/0", "::/0") } else { $true }
$applySafetyAccepted = $applySafetyStatus -eq "passed" -or (
    $applySafetyStatus -eq "warning" -and
    -not $applySafetyBlocking -and
    -not $openAdminIngress
)
$lifecycleStatus = if ($lifecycle) { [string]$lifecycle.status } else { "not_run" }
$enableDws = if ($minimalPlan -and $minimalPlan.options) { [bool]$minimalPlan.options.enable_dws } else { $false }
$enableDataArts = if ($evidence -and $evidence.dataarts -and $evidence.dataarts.instance_name) {
    $true
}
elseif ($minimalPlan -and $minimalPlan.options) {
    [bool]$minimalPlan.options.enable_dataarts
}
else {
    $false
}

Add-Check -Stage "customer_demo" -Id "PLAN-001" -Name "Minimal resource plan exists" -Status ($(if ($minimalPlanStatus -in @("ready_for_operator_review", "review_required")) { "passed" } else { "warning" })) -Detail "status=$minimalPlanStatus"
Add-Check -Stage "customer_demo" -Id "CLOUD-001" -Name "Real MRS job succeeded" -Status ($(if ($jobStatus -eq "success") { "passed" } else { "warning" })) -Detail "job_status=$jobStatus"
Add-Check -Stage "customer_demo" -Id "DATA-001" -Name "Gold output is non-empty" -Status ($(if ($goldRows -gt 0) { "passed" } else { "warning" })) -Detail "gold_row_count=$goldRows"
Add-Check -Stage "customer_demo" -Id "PRIVACY-001" -Name "Direct RFC is masked" -Status ($(if (-not $directRfcExposed) { "passed" } else { "warning" })) -Detail "direct_rfc_exposed=$directRfcExposed"
Add-Check -Stage "customer_demo" -Id "EXEC-001" -Name "Execution does not use DuckDB" -Status ($(if (-not $duckdbUsed) { "passed" } else { "warning" })) -Detail "duckdb_used=$duckdbUsed"
Add-Check -Stage "customer_demo" -Id "WEB-001" -Name "Cloud website diagnostics passed" -Status ($(if ($webDiagStatus -eq "ready_for_customer_demo") { "passed" } else { "warning" })) -Detail "status=$webDiagStatus"
Add-Check -Stage "customer_demo" -Id "SUMMARY-001" -Name "Customer summary is ready" -Status ($(if ($summaryStatus -eq "ready_for_customer_demo") { "passed" } else { "warning" })) -Detail "status=$summaryStatus"
Add-Check -Stage "customer_demo" -Id "AUDIT-001" -Name "Strict final audit passed" -Status ($(if ($auditStatus -eq "ready_for_customer_demo") { "passed" } else { "warning" })) -Detail "status=$auditStatus"
Add-Check -Stage "customer_demo" -Id "HANDOFF-001" -Name "Customer handoff is ready" -Status ($(if ($handoffStatus -eq "ready_for_customer_handoff") { "passed" } else { "warning" })) -Detail "status=$handoffStatus"
Add-Check -Stage "customer_demo" -Id "LIFECYCLE-001" -Name "Cleanup owner and expiration are present" -Status ($(if ($lifecycleStatus -eq "passed") { "passed" } else { "warning" })) -Detail "status=$lifecycleStatus"
Add-Check -Stage "customer_demo" -Id "INGRESS-001" -Name "Ingress safety passed" -Status ($(if ($applySafetyAccepted) { "passed" } else { "warning" })) -Detail "status=$applySafetyStatus; blocking=$applySafetyBlocking; admin_cidr=$($applySafety.admin_cidr); web_cidr=$($applySafety.web_cidr)"

$demoRequiredOpen = @($script:Checks | Where-Object { $_.stage -eq "customer_demo" -and $_.required -and $_.status -ne "passed" })
$demoReady = $demoRequiredOpen.Count -eq 0

Add-Check -Stage "commercial" -Id "COMM-BASE-001" -Name "Customer demo evidence is already ready" -Status ($(if ($demoReady) { "passed" } else { "warning" })) -Detail ($(if ($demoReady) { "strict customer demo gate passed" } else { "real cloud customer demo evidence is not ready yet" }))
Add-Check -Stage "commercial" -Id "TLS-001" -Name "Domain and HTTPS are configured" -Status ($(if ($DomainName -and $HttpsEnabled) { "passed" } else { "warning" })) -Detail ($(if ($DomainName -and $HttpsEnabled) { "domain=$DomainName; https=true" } else { "set -DomainName and -HttpsEnabled before external commercial access" }))
Add-Check -Stage "commercial" -Id "IAM-001" -Name "Least-privilege IAM is confirmed" -Status ($(if ($IamLeastPrivilegeConfirmed) { "passed" } else { "warning" })) -Detail "Do not use broad workstation AK/SK for commercial operations."
Add-Check -Stage "commercial" -Id "OBSERVE-001" -Name "Monitoring and alerting are enabled" -Status ($(if ($MonitoringEnabled) { "passed" } else { "warning" })) -Detail "Cloud Eye/AOM-style alerting must cover MRS job failure, ECS health, OBS growth, and error counts."
Add-Check -Stage "commercial" -Id "STATE-001" -Name "Terraform remote state is controlled" -Status ($(if ($RemoteTerraformStateConfirmed) { "passed" } else { "warning" })) -Detail "Commercial environments need controlled remote state and access review."
Add-Check -Stage "commercial" -Id "RETENTION-001" -Name "Backup and retention are defined" -Status ($(if ($BackupRetentionDays -gt 0 -and $RetentionPolicyConfirmed) { "passed" } else { "warning" })) -Detail "backup_retention_days=$BackupRetentionDays; retention_policy_confirmed=$([bool]$RetentionPolicyConfirmed)"
Add-Check -Stage "commercial" -Id "OPS-001" -Name "Incident owner is defined" -Status ($(if ($IncidentOwner) { "passed" } else { "warning" })) -Detail ($(if ($IncidentOwner) { "incident_owner=$IncidentOwner" } else { "set -IncidentOwner or TF_VAR_demo_owner" }))
Add-Check -Stage "commercial" -Id "SLA-001" -Name "Production SLA is approved" -Status ($(if ($ProductionSlaApproved) { "passed" } else { "warning" })) -Detail "Production SLA, RTO/RPO, support hours, and rollback owner must be approved."
Add-Check -Stage "commercial" -Id "DWS-001" -Name "DWS production sizing benchmark" -Status ($(if (-not $enableDws) { "not_required" } else { "warning" })) -Required $enableDws -Detail ($(if ($enableDws) { "DWS is enabled; benchmark serving workload before production." } else { "DWS is not enabled in the minimal plan." }))
Add-Check -Stage "commercial" -Id "DATAARTS-001" -Name "DataArts production orchestration review" -Status ($(if (-not $enableDataArts) { "not_required" } else { "warning" })) -Required $enableDataArts -Detail ($(if ($enableDataArts) { "DataArts is enabled; confirm workspace quota, permissions, and API/UI fallback runbook." } else { "DataArts is not enabled in the minimal plan." }))

$commercialRequiredOpen = @($script:Checks | Where-Object { $_.stage -eq "commercial" -and $_.required -and $_.status -ne "passed" })
$commercialReady = $commercialRequiredOpen.Count -eq 0

$finalStatus = if ($commercialReady) {
    "ready_for_commercial_pilot"
}
elseif ($demoReady) {
    "ready_for_customer_demo"
}
else {
    "pending_customer_demo_evidence"
}

if ($RequireCommercial -and -not $commercialReady) {
    $finalStatus = "failed"
}

$base = $BaseUrl.TrimEnd("/")
$report = [ordered]@{
    status = $finalStatus
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = $false
    uploads_obs_objects = $false
    submits_mrs_job = $false
    network_calls = 0
    write_calls = 0
    base_url = $base
    demo_ready = $demoReady
    commercial_ready = $commercialReady
    demo_open_required_count = $demoRequiredOpen.Count
    commercial_open_required_count = $commercialRequiredOpen.Count
    job_status = $jobStatus
    gold_row_count = $goldRows
    direct_rfc_exposed = $directRfcExposed
    duckdb_used = $duckdbUsed
    customer_report_url = "$base/cloud-evidence/customer_demo_report.html"
    customer_handoff_url = "$base/cloud-evidence/customer_handoff.html"
    checks = $script:Checks
    options = [ordered]@{
        domain_name = $DomainName
        https_enabled = [bool]$HttpsEnabled
        iam_least_privilege_confirmed = [bool]$IamLeastPrivilegeConfirmed
        monitoring_enabled = [bool]$MonitoringEnabled
        remote_terraform_state_confirmed = [bool]$RemoteTerraformStateConfirmed
        backup_retention_days = $BackupRetentionDays
        retention_policy_confirmed = [bool]$RetentionPolicyConfirmed
        incident_owner = $IncidentOwner
        production_sla_approved = [bool]$ProductionSlaApproved
        enable_dws = $enableDws
        enable_dataarts = $enableDataArts
    }
    paths = [ordered]@{
        cloud_evidence = $evidencePath
        customer_summary = $summaryPath
        customer_handoff = $handoffPath
        final_audit = $auditPath
        web_diagnostics = $webDiagPath
        web_deploy = $webDeployPath
        minimal_cost_quota_plan = $minimalPlanPath
        apply_safety = $applySafetyPath
        lifecycle_guard = $lifecyclePath
    }
    next_action = if ($commercialReady) {
        "Proceed with a controlled commercial pilot review using this report, the strict audit, and the customer handoff package."
    }
    elseif ($demoReady) {
        "Use the customer demo package for controlled demonstration; complete commercial hardening before production or external SLA claims."
    }
    else {
        ".\cloud_real_bigdata\scripts\19_run_customer_demo_once.ps1 -EnableWebEcs -SshKeyPath `"<path-to-private-key.pem>`" -Apply -ConfirmPaidResources"
    }
}

$jsonPath = Join-Path $OutputDir "customer_commercial_readiness_latest.json"
$mdPath = Join-Path $OutputDir "customer_commercial_readiness.md"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# SAT Agentic Customer And Commercial Readiness",
    "",
    "- status: $($report.status)",
    "- demo_ready: $($report.demo_ready)",
    "- commercial_ready: $($report.commercial_ready)",
    "- creates_resources: false",
    "- uploads_obs_objects: false",
    "- submits_mrs_job: false",
    "- network_calls: 0",
    "- write_calls: 0",
    "- customer_report_url: $($report.customer_report_url)",
    "- customer_handoff_url: $($report.customer_handoff_url)",
    "",
    "## Checks",
    ""
)
$md += Render-Table $script:Checks
$md += @(
    "",
    "## Next Action",
    "",
    '```powershell',
    $report.next_action,
    '```'
)
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

if ($PublishToEvidence) {
    New-Item -ItemType Directory -Force -Path $publicEvidenceDir | Out-Null
    Copy-Item -LiteralPath $jsonPath -Destination (Join-Path $publicEvidenceDir "customer_commercial_readiness.json") -Force
    Copy-Item -LiteralPath $mdPath -Destination (Join-Path $publicEvidenceDir "customer_commercial_readiness.md") -Force
}

Write-Host "Customer/commercial readiness status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "failed") { "Red" } elseif ($report.status -eq "ready_for_commercial_pilot") { "Green" } elseif ($report.status -eq "ready_for_customer_demo") { "Green" } else { "Yellow" }))
Write-Host "Readiness JSON: $jsonPath"
Write-Host "Readiness report: $mdPath"
Write-Host "No cloud APIs were called, no resources were created, no OBS objects were uploaded, and no MRS jobs were submitted."

if ($finalStatus -eq "failed") {
    throw "Customer/commercial readiness failed. $($report.next_action)"
}
