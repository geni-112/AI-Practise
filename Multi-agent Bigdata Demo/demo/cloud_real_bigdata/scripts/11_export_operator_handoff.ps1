param(
    [string]$BaseUrl = "http://127.0.0.1:8788",

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

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
        return [ordered]@{
            status = "invalid_json"
            path = $Path
            error = $_.Exception.Message
        }
    }
}

function Get-SafeEnvSummary {
    $names = @(
        "HUAWEICLOUD_ACCESS_KEY",
        "HUAWEICLOUD_SECRET_KEY",
        "HUAWEICLOUD_REGION",
        "HUAWEICLOUD_PROJECT_ID",
        "TF_VAR_mrs_manager_admin_password",
        "TF_VAR_node_key_pair_name",
        "TF_VAR_dws_admin_password"
    )
    $items = @()
    foreach ($name in $names) {
        $items += [ordered]@{
            name = $name
            configured = Test-Configured $name
            required_for_minimal = $name -ne "TF_VAR_dws_admin_password"
        }
    }
    return $items
}

function Get-JsonEndpoint {
    param([string]$Url)
    try {
        return Invoke-RestMethod -Method Get -Uri $Url -Headers @{ "Cache-Control" = "no-cache" } -TimeoutSec 8
    }
    catch {
        return [ordered]@{
            status = "unreachable"
            url = $Url
            error = $_.Exception.Message
        }
    }
}

function Render-StatusTable {
    param([array]$Rows)
    $lines = @(
        "| item | status | detail |",
        "| --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $item = ([string]$row.item).Replace("|", "\|")
        $status = ([string]$row.status).Replace("|", "\|")
        $detail = ([string]$row.detail).Replace("|", "\|")
        $lines += "| $item | $status | $detail |"
    }
    return $lines
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\operator_handoff"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$preflightPath = Join-Path $root ".cloud_real_bigdata_work\real_cloud_preflight\real_cloud_preflight_latest.json"
$tracePath = Join-Path $root ".cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json"
$acceptancePath = Join-Path $root ".cloud_real_bigdata_work\acceptance_audit\final_acceptance_audit.json"
$credentialStatusPath = Join-Path $root ".cloud_real_bigdata_work\credential_status\credential_status_latest.json"
$applySafetyPath = Join-Path $root ".cloud_real_bigdata_work\apply_safety\apply_safety_latest.json"
$lifecycleGuardPath = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"
$readonlyProbePath = Join-Path $root ".cloud_real_bigdata_work\readonly_probe\readonly_probe_latest.json"
$preApplyReadinessPath = Join-Path $root ".cloud_real_bigdata_work\pre_apply_readiness\pre_apply_readiness_latest.json"
$webDeployManifestPath = Join-Path $root ".cloud_real_bigdata_work\web_deploy\web_deploy_manifest.json"
$webDiagnosticsPath = Join-Path $root ".cloud_real_bigdata_work\web_diagnostics\web_diagnostics_latest.json"
$evidencePath = Join-Path $root "cloud_real_bigdata\public_evidence\latest_e2e_result.json"
$customerSummaryPath = Join-Path $root "cloud_real_bigdata\public_evidence\customer_demo_summary.json"

$credentialStatus = Read-JsonFile $credentialStatusPath
$applySafety = Read-JsonFile $applySafetyPath
$lifecycleGuard = Read-JsonFile $lifecycleGuardPath
$readonlyProbe = Read-JsonFile $readonlyProbePath
$preApplyReadiness = Read-JsonFile $preApplyReadinessPath
$webDeployManifest = Read-JsonFile $webDeployManifestPath
$webDiagnostics = Read-JsonFile $webDiagnosticsPath
$preflight = Read-JsonFile $preflightPath
$trace = Read-JsonFile $tracePath
$acceptance = Read-JsonFile $acceptancePath
$evidence = Read-JsonFile $evidencePath
$customerSummary = Read-JsonFile $customerSummaryPath
$health = Get-JsonEndpoint ($BaseUrl.TrimEnd("/") + "/api/health")
$cloudEvidenceApi = Get-JsonEndpoint ($BaseUrl.TrimEnd("/") + "/api/cloud/e2e-evidence")

$envSummary = Get-SafeEnvSummary
$missingMinimal = @($envSummary | Where-Object { $_.required_for_minimal -and -not $_.configured })

$statusRows = @(
    [ordered]@{ item = "cloud_credentials"; status = if ($missingMinimal.Count -eq 0) { "ready" } else { "missing" }; detail = if ($missingMinimal.Count -eq 0) { "minimal required env vars are configured" } else { ($missingMinimal.name -join ", ") } },
    [ordered]@{ item = "credential_status_report"; status = if ($credentialStatus) { [string]$credentialStatus.status } else { "not_run" }; detail = if ($credentialStatus) { "missing=$($credentialStatus.missing_required -join ', ')" } else { $credentialStatusPath } },
    [ordered]@{ item = "apply_safety"; status = if ($applySafety) { [string]$applySafety.status } else { "not_run" }; detail = if ($applySafety) { "admin_cidr=$($applySafety.admin_cidr); allow_open_ingress=$($applySafety.allow_open_ingress_for_demo)" } else { $applySafetyPath } },
    [ordered]@{ item = "lifecycle_guard"; status = if ($lifecycleGuard) { [string]$lifecycleGuard.status } else { "not_run" }; detail = if ($lifecycleGuard) { "owner=$($lifecycleGuard.demo_owner); expires_at=$($lifecycleGuard.demo_expires_at)" } else { $lifecycleGuardPath } },
    [ordered]@{ item = "readonly_cloud_probe"; status = if ($readonlyProbe) { [string]$readonlyProbe.status } else { "not_run" }; detail = if ($readonlyProbe) { "network_calls=$($readonlyProbe.network_calls); writes=$($readonlyProbe.write_calls)" } else { $readonlyProbePath } },
    [ordered]@{ item = "pre_apply_readiness"; status = if ($preApplyReadiness) { [string]$preApplyReadiness.status } else { "not_run" }; detail = if ($preApplyReadiness) { "creates_resources=$($preApplyReadiness.creates_resources)" } else { $preApplyReadinessPath } },
    [ordered]@{ item = "real_cloud_preflight"; status = if ($preflight) { [string]$preflight.status } else { "not_run" }; detail = if ($preflight) { [string]$preflight.message } else { $preflightPath } },
    [ordered]@{ item = "latest_e2e_trace"; status = if ($trace) { [string]$trace.status } else { "not_run" }; detail = if ($trace) { "mode=$($trace.mode); run_id=$($trace.outputs.run_id)" } else { $tracePath } },
    [ordered]@{ item = "acceptance_audit"; status = if ($acceptance) { [string]$acceptance.status } else { "not_run" }; detail = if ($acceptance) { "failed=$($acceptance.failed_count); warnings=$($acceptance.warning_count)" } else { $acceptancePath } },
    [ordered]@{ item = "web_deploy_manifest"; status = if ($webDeployManifest) { [string]$webDeployManifest.status } else { "not_run" }; detail = if ($webDeployManifest) { [string]$webDeployManifest.target_url } else { $webDeployManifestPath } },
    [ordered]@{ item = "web_diagnostics"; status = if ($webDiagnostics) { [string]$webDiagnostics.status } else { "not_run" }; detail = if ($webDiagnostics) { "failed_critical=$($webDiagnostics.failed_critical_count); warnings=$($webDiagnostics.warning_count)" } else { $webDiagnosticsPath } },
    [ordered]@{ item = "cloud_evidence_file"; status = if ($evidence) { "present" } else { "not_run" }; detail = $evidencePath },
    [ordered]@{ item = "customer_summary"; status = if ($customerSummary) { [string]$customerSummary.status } else { "not_run" }; detail = $customerSummaryPath },
    [ordered]@{ item = "website_health"; status = if ($health.ok) { "ok" } elseif ($health.status) { [string]$health.status } else { "unknown" }; detail = "base_url=$BaseUrl" },
    [ordered]@{ item = "website_cloud_evidence"; status = if ($cloudEvidenceApi.available) { [string]$cloudEvidenceApi.status } elseif ($cloudEvidenceApi.status) { [string]$cloudEvidenceApi.status } else { "unknown" }; detail = "available=$($cloudEvidenceApi.available)" }
)

$recommendedBucket = if ($preflight.obs_bucket_name) {
    [string]$preflight.obs_bucket_name
}
elseif ($trace.outputs.obs_bucket_name) {
    [string]$trace.outputs.obs_bucket_name
}
else {
    "sat-agentic-<globally-unique-suffix>"
}
$nodeKey = if (Test-Configured "TF_VAR_node_key_pair_name") { $env:TF_VAR_node_key_pair_name } else { "<existing-key-pair>" }
$promptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"

$summary = [ordered]@{
    status = if ($customerSummary -and $cloudEvidenceApi.available -and $cloudEvidenceApi.status -eq "success") {
        "customer_demo_ready"
    }
    elseif ($missingMinimal.Count -eq 0 -and $preflight -and $preflight.status -eq "passed" -and $applySafety -and $applySafety.status -eq "passed" -and $lifecycleGuard -and $lifecycleGuard.status -eq "passed") {
        "ready_for_apply"
    }
    else {
        "operator_action_required"
    }
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    base_url = $BaseUrl.TrimEnd("/")
    missing_minimal_env = @($missingMinimal.name)
    status_rows = $statusRows
    paths = [ordered]@{
        preflight = $preflightPath
        trace = $tracePath
        acceptance = $acceptancePath
        credential_status = $credentialStatusPath
        apply_safety = $applySafetyPath
        lifecycle_guard = $lifecycleGuardPath
        readonly_probe = $readonlyProbePath
        pre_apply_readiness = $preApplyReadinessPath
        web_deploy_manifest = $webDeployManifestPath
        web_diagnostics = $webDiagnosticsPath
        cloud_evidence = $evidencePath
        customer_summary = $customerSummaryPath
    }
    commands = [ordered]@{
        credential_status = ".\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1"
        configure_user_env = ".\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1 -PersistUserEnv"
        configure_local_env = ".\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1 -WriteLocalEnv"
        apply_safety = ".\cloud_real_bigdata\scripts\14_validate_apply_safety.ps1 -EnableWebEcs -Apply"
        lifecycle_guard = ".\cloud_real_bigdata\scripts\16_validate_lifecycle_guard.ps1 -Apply"
        readonly_probe = ".\cloud_real_bigdata\scripts\17_run_readonly_cloud_probe.ps1"
        readiness = ".\cloud_real_bigdata\scripts\15_pre_apply_readiness.ps1 -EnableWebEcs -RunReadonlyCloudProbe -RunTerraformPreflight"
        validate_env = ".\cloud_real_bigdata\scripts\02_validate_env.ps1"
        preflight = ".\cloud_real_bigdata\scripts\10_real_cloud_preflight_plan.ps1 -EnableWebEcs"
        apply = ".\cloud_real_bigdata\scripts\05_run_real_e2e.ps1 -ObsBucketName `"$recommendedBucket`" -NodeKeyPairName `"$nodeKey`" -PromptFile `"$promptFile`" -EnableWebEcs -SshKeyPath `"<path-to-private-key.pem>`" -Apply"
        diagnose_web = ".\cloud_real_bigdata\scripts\13_diagnose_web_ecs.ps1 -WebPublicIp `"<web-eip>`" -SshKeyPath `"<path-to-private-key.pem>`""
        strict_acceptance = ".\cloud_real_bigdata\scripts\09_final_acceptance_audit.ps1 -BaseUrl `"http://<web-eip>`" -RequireCloudSuccess"
        cleanup = ".\cloud_real_bigdata\scripts\04_destroy.ps1 -ConfirmDestroy"
    }
}

$jsonPath = Join-Path $OutputDir "operator_handoff_summary.json"
$mdPath = Join-Path $OutputDir "operator_handoff.md"
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# SAT Agentic Operator Handoff",
    "",
    "- status: $($summary.status)",
    "- generated_at: $($summary.generated_at)",
    "- base_url: $($summary.base_url)",
    "",
    "## Current State",
    ""
)
$md += Render-StatusTable $statusRows
$md += @(
    "",
    "## Missing Minimal Environment Variables",
    ""
)
if ($summary.missing_minimal_env.Count -gt 0) {
    foreach ($name in $summary.missing_minimal_env) {
        $md += "- $name"
    }
}
else {
    $md += "- none"
}
$md += @(
    "",
    "## Execution Commands",
    "",
    '```powershell',
    $summary.commands.credential_status,
    "",
    $summary.commands.configure_user_env,
    "",
    $summary.commands.apply_safety,
    "",
    $summary.commands.lifecycle_guard,
    "",
    $summary.commands.readonly_probe,
    "",
    $summary.commands.readiness,
    "",
    $summary.commands.validate_env,
    "",
    $summary.commands.preflight,
    "",
    $summary.commands.apply,
    "",
    $summary.commands.diagnose_web,
    "",
    $summary.commands.strict_acceptance,
    "",
    $summary.commands.cleanup,
    '```',
    "",
    "## Troubleshooting Order",
    "",
    '1. Check `.cloud_real_bigdata_work/credential_status/credential_status_latest.json` before any paid apply.',
    '2. Check `.cloud_real_bigdata_work/apply_safety/apply_safety_latest.json` before any paid apply.',
    '3. Check `.cloud_real_bigdata_work/lifecycle_guard/lifecycle_guard_latest.json` before any paid apply.',
    '4. Check `.cloud_real_bigdata_work/readonly_probe/readonly_probe_latest.json` after credentials are set.',
    '5. Check `.cloud_real_bigdata_work/pre_apply_readiness/pre_apply_readiness_latest.json` for the combined gate.',
    '6. Check `.cloud_real_bigdata_work/e2e_traces/latest_e2e_trace.json` for the failing stage.',
    '7. Check `.cloud_real_bigdata_work/real_cloud_preflight/real_cloud_preflight_latest.json` before any paid apply.',
    '8. Check `.cloud_real_bigdata_work/web_diagnostics/web_diagnostics_latest.json` after ECS deployment.',
    '9. If Terraform apply fails, inspect `cloud_real_bigdata/terraform/terraform.tfstate` before cleanup.',
    "10. If MRS job fails, inspect the job id/name in the trace and the MRS console.",
    '11. If the website is unreachable, verify ECS EIP, security group HTTP/HTTPS rules, Nginx, and the `sat-agent-vibe` systemd service.',
    "",
    "## Safety Notes",
    "",
    "- This handoff does not contain AK/SK, passwords, private keys, cookies, or browser session data.",
    "- Do not use credentials stored in skills, chat messages, screenshots, browser cookies, saved passwords, or logs.",
    "- Set `TF_VAR_admin_cidr` to a trusted office/VPN CIDR before customer or commercial use.",
    "- Set `TF_VAR_demo_owner` and `TF_VAR_demo_expires_at` before creating paid resources.",
    '- Do not run `04_destroy.ps1` until you have preserved needed evidence.',
    "- DataArts and DWS remain optional and should stay disabled for the minimal first run."
)
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Operator handoff exported." -ForegroundColor Green
Write-Host "Summary: $jsonPath"
Write-Host "Report: $mdPath"
Write-Host "Status: $($summary.status)"
