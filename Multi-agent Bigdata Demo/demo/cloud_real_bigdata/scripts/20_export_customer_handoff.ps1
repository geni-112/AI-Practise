param(
    [string]$BaseUrl = "http://127.0.0.1:8788",

    [switch]$RequireCloudSuccess,

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
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )
    $script:Checks += [ordered]@{
        name = $Name
        status = $Status
        detail = $Detail
    }
}

function Escape-Html {
    param([string]$Value)
    return [System.Net.WebUtility]::HtmlEncode($Value)
}

function Convert-MarkdownTable {
    param([array]$Rows)
    if (-not $Rows -or $Rows.Count -eq 0) {
        return "_No preview rows available._"
    }
    $headers = @($Rows[0].PSObject.Properties.Name)
    $lines = @(
        "| " + ($headers -join " | ") + " |",
        "| " + (($headers | ForEach-Object { "---" }) -join " | ") + " |"
    )
    foreach ($row in $Rows | Select-Object -First 12) {
        $values = foreach ($header in $headers) {
            ([string]$row.$header).Replace("|", "\|")
        }
        $lines += "| " + ($values -join " | ") + " |"
    }
    return ($lines -join "`n")
}

function Write-HandoffFiles {
    param(
        [object]$Handoff,
        [string]$JsonPath,
        [string]$MarkdownPath,
        [string]$HtmlPath
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $JsonPath) | Out-Null
    $Handoff | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $JsonPath -Encoding UTF8

    $checkLines = foreach ($check in $Handoff.checks) {
        "- $($check.status): $($check.name) - $($check.detail)"
    }
    $commercialLines = foreach ($item in $Handoff.commercial_readiness.required_before_commercial) {
        "- $item"
    }
    $goldTable = Convert-MarkdownTable -Rows $Handoff.gold_preview_rows
    $markdown = @"
# SAT Agentic Customer Handoff

- Status: $($Handoff.status)
- Base URL: $($Handoff.base_url)
- Customer report: $($Handoff.customer_report_url)
- API evidence: $($Handoff.api_evidence_url)
- Run ID: $($Handoff.run_id)
- Region: $($Handoff.region)
- OBS bucket: $($Handoff.bucket)
- MRS cluster: $($Handoff.cluster_id)
- Gold rows: $($Handoff.gold_row_count)
- Values printed: false

## Checks

$($checkLines -join "`n")

## Gold Preview

$goldTable

## Cleanup

```powershell
$($Handoff.cleanup.command)
```

$($Handoff.cleanup.note)

## Commercial Readiness

- Current level: $($Handoff.commercial_readiness.current_level)
- Recommendation: $($Handoff.commercial_readiness.recommendation)

$($commercialLines -join "`n")

## Source Reports

- Cloud evidence: $($Handoff.paths.cloud_evidence)
- Customer summary: $($Handoff.paths.customer_summary)
- Final audit: $($Handoff.paths.final_audit)
- Demo once: $($Handoff.paths.customer_demo_once)
"@
    $markdown | Set-Content -LiteralPath $MarkdownPath -Encoding UTF8

    $htmlChecks = ($Handoff.checks | ForEach-Object {
        "<li><strong>$(Escape-Html $_.status)</strong>: $(Escape-Html $_.name) - $(Escape-Html $_.detail)</li>"
    }) -join "`n"
    $htmlCommercial = ($Handoff.commercial_readiness.required_before_commercial | ForEach-Object {
        "<li>$(Escape-Html $_)</li>"
    }) -join "`n"
    $htmlRows = ""
    if ($Handoff.gold_preview_rows -and $Handoff.gold_preview_rows.Count -gt 0) {
        $headers = @($Handoff.gold_preview_rows[0].PSObject.Properties.Name)
        $htmlRows += "<table><thead><tr>"
        foreach ($header in $headers) { $htmlRows += "<th>$(Escape-Html $header)</th>" }
        $htmlRows += "</tr></thead><tbody>"
        foreach ($row in $Handoff.gold_preview_rows | Select-Object -First 12) {
            $htmlRows += "<tr>"
            foreach ($header in $headers) { $htmlRows += "<td>$(Escape-Html ([string]$row.$header))</td>" }
            $htmlRows += "</tr>"
        }
        $htmlRows += "</tbody></table>"
    }
    else {
        $htmlRows = "<p>No preview rows available.</p>"
    }
    $html = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SAT Agentic Customer Handoff</title>
  <style>
    body { margin: 0; background: #f6f7f9; color: #1f2933; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Arial, sans-serif; line-height: 1.45; }
    main { max-width: 980px; margin: 0 auto; padding: 28px 18px 48px; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    h2 { margin-top: 26px; font-size: 18px; }
    .status { display: inline-block; border: 1px solid #a9d8bd; background: #edf8f1; color: #24724d; border-radius: 999px; padding: 5px 10px; font-weight: 650; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
    .metric { border: 1px solid #d9dee7; border-radius: 8px; background: #fff; padding: 12px; }
    .metric span { display: block; color: #667085; font-size: 12px; }
    .metric strong { display: block; margin-top: 4px; overflow-wrap: anywhere; }
    section { border-top: 1px solid #d9dee7; margin-top: 24px; padding-top: 16px; }
    li { margin: 6px 0; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { border-bottom: 1px solid #d9dee7; padding: 8px; text-align: left; font-size: 13px; }
    th { color: #667085; background: #f8fafc; }
    code { display: block; white-space: pre-wrap; background: #111827; color: #f7fafc; border-radius: 8px; padding: 12px; }
    a { color: #255f9e; }
  </style>
</head>
<body>
<main>
  <h1>SAT Agentic Customer Handoff</h1>
  <div class="status">$(Escape-Html $Handoff.status)</div>
  <div class="grid">
    <div class="metric"><span>Run ID</span><strong>$(Escape-Html $Handoff.run_id)</strong></div>
    <div class="metric"><span>Job</span><strong>$(Escape-Html $Handoff.job_status)</strong></div>
    <div class="metric"><span>Gold rows</span><strong>$(Escape-Html ([string]$Handoff.gold_row_count))</strong></div>
    <div class="metric"><span>RFC</span><strong>$(if ($Handoff.direct_rfc_exposed) { "exposed" } else { "masked" })</strong></div>
  </div>
  <section>
    <h2>Links</h2>
    <ul>
      <li><a href="$(Escape-Html $Handoff.customer_report_url)">Customer report</a></li>
      <li><a href="$(Escape-Html $Handoff.api_evidence_url)">API evidence</a></li>
    </ul>
  </section>
  <section>
    <h2>Checks</h2>
    <ul>$htmlChecks</ul>
  </section>
  <section>
    <h2>Gold Preview</h2>
    $htmlRows
  </section>
  <section>
    <h2>Cleanup</h2>
    <code>$(Escape-Html $Handoff.cleanup.command)</code>
    <p>$(Escape-Html $Handoff.cleanup.note)</p>
  </section>
  <section>
    <h2>Commercial Readiness</h2>
    <p><strong>Current level:</strong> $(Escape-Html $Handoff.commercial_readiness.current_level)</p>
    <p>$(Escape-Html $Handoff.commercial_readiness.recommendation)</p>
    <ul>$htmlCommercial</ul>
  </section>
</main>
</body>
</html>
"@
    $html | Set-Content -LiteralPath $HtmlPath -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\customer_handoff"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$publicEvidenceDir = Join-Path $root "cloud_real_bigdata\public_evidence"
$evidencePath = Join-Path $publicEvidenceDir "latest_e2e_result.json"
$summaryPath = Join-Path $publicEvidenceDir "customer_demo_summary.json"
$auditPath = Join-Path $root ".cloud_real_bigdata_work\acceptance_audit\final_acceptance_audit.json"
$demoOncePath = Join-Path $root ".cloud_real_bigdata_work\customer_demo_once\customer_demo_once_latest.json"
$webDeployPath = Join-Path $root ".cloud_real_bigdata_work\web_deploy\web_deploy_manifest.json"
$webDiagPath = Join-Path $root ".cloud_real_bigdata_work\web_diagnostics\web_diagnostics_latest.json"
$lifecyclePath = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"

$evidence = Read-JsonFile $evidencePath
$summary = Read-JsonFile $summaryPath
$audit = Read-JsonFile $auditPath
$demoOnce = Read-JsonFile $demoOncePath
$webDeploy = Read-JsonFile $webDeployPath
$webDiag = Read-JsonFile $webDiagPath
$lifecycle = Read-JsonFile $lifecyclePath

$script:Checks = @()
$jobStatus = if ($evidence) { [string]$evidence.job.terminal_status } else { "not_run" }
$goldRows = 0
if ($evidence -and $null -ne $evidence.gold_row_count) {
    $goldRows = [int]$evidence.gold_row_count
}
$directRfcExposed = if ($evidence) { [bool]$evidence.direct_rfc_exposed } else { $true }
$duckdbUsed = if ($evidence) { [bool]$evidence.duckdb_used } else { $true }

Add-Check -Name "Real cloud evidence" -Status ($(if ($jobStatus -eq "success") { "passed" } else { "warning" })) -Detail "job_status=$jobStatus"
Add-Check -Name "Gold output is non-empty" -Status ($(if ($goldRows -gt 0) { "passed" } else { "warning" })) -Detail "gold_row_count=$goldRows"
Add-Check -Name "Direct RFC masked" -Status ($(if (-not $directRfcExposed) { "passed" } else { "warning" })) -Detail "direct_rfc_exposed=$directRfcExposed"
Add-Check -Name "DuckDB not used" -Status ($(if (-not $duckdbUsed) { "passed" } else { "warning" })) -Detail "duckdb_used=$duckdbUsed"
Add-Check -Name "Customer summary" -Status ($(if ($summary -and $summary.status -eq "ready_for_customer_demo") { "passed" } else { "warning" })) -Detail "status=$($summary.status)"
Add-Check -Name "Final audit" -Status ($(if ($audit -and $audit.status -eq "ready_for_customer_demo") { "passed" } else { "warning" })) -Detail "status=$($audit.status)"
Add-Check -Name "Website deploy manifest" -Status ($(if ($webDeploy) { "passed" } else { "warning" })) -Detail ($(if ($webDeploy) { "web_public_ip=$($webDeploy.web_public_ip)" } else { "not found" }))
Add-Check -Name "Website diagnostics" -Status ($(if ($webDiag -and $webDiag.failed_critical_count -eq 0) { "passed" } else { "warning" })) -Detail ($(if ($webDiag) { "status=$($webDiag.status)" } else { "not found" }))
Add-Check -Name "Lifecycle guard" -Status ($(if ($lifecycle -and $lifecycle.status -eq "passed") { "passed" } else { "warning" })) -Detail ($(if ($lifecycle) { "owner=$($lifecycle.demo_owner); expires_at=$($lifecycle.demo_expires_at)" } else { "not found" }))

$failedRequired = @($script:Checks | Where-Object {
    $_.name -in @("Real cloud evidence", "Gold output is non-empty", "Direct RFC masked", "DuckDB not used", "Customer summary", "Final audit") -and $_.status -ne "passed"
})
$status = if ($failedRequired.Count -eq 0) { "ready_for_customer_handoff" } else { "pending_cloud_evidence" }
if ($RequireCloudSuccess -and $status -ne "ready_for_customer_handoff") {
    $status = "failed"
}

$goldPreviewRows = @()
if ($evidence -and $evidence.gold_preview_rows) {
    $goldPreviewRows = @($evidence.gold_preview_rows)
}

$base = $BaseUrl.TrimEnd("/")
if ($summary -and $summary.customer_report_url) {
    $baseFromSummary = ([string]$summary.customer_report_url) -replace "/cloud-evidence/customer_demo_report.html$", ""
    if ($baseFromSummary) { $base = $baseFromSummary }
}

$handoff = [ordered]@{
    status = $status
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = $false
    uploads_obs_objects = $false
    submits_mrs_job = $false
    base_url = $base
    customer_report_url = "$base/cloud-evidence/customer_demo_report.html"
    api_evidence_url = "$base/api/cloud/e2e-evidence"
    run_id = if ($evidence) { $evidence.run_id } else { "" }
    agent_run_id = if ($evidence) { $evidence.agent_run_id } else { "" }
    region = if ($evidence) { $evidence.region } else { "" }
    bucket = if ($evidence) { $evidence.bucket } else { "" }
    cluster_id = if ($evidence) { $evidence.cluster_id } else { "" }
    job_status = $jobStatus
    gold_prefix = if ($evidence) { $evidence.gold_prefix } else { "" }
    gold_row_count = $goldRows
    direct_rfc_exposed = $directRfcExposed
    duckdb_used = $duckdbUsed
    gold_preview_rows = [object[]]$goldPreviewRows
    checks = $script:Checks
    cleanup = [ordered]@{
        command = ".\cloud_real_bigdata\scripts\04_destroy.ps1 -ConfirmDestroy"
        note = "Destroy only after the customer has finished reviewing the website, evidence, OBS audit output, and final acceptance report."
    }
    commercial_readiness = [ordered]@{
        current_level = if ($status -eq "ready_for_customer_handoff") { "customer-demo-ready" } else { "not-demo-ready" }
        recommendation = "This minimal stack is suitable for a controlled customer demo after strict audit passes. Treat commercial production as a follow-on hardening phase."
        required_before_commercial = @(
            "Move cloud credentials to IAM agency or cloud secret service; avoid workstation-stored AK/SK.",
            "Use a managed domain with HTTPS/TLS and production ingress controls.",
            "Confirm quota, sizing, cost owner, monitoring, alerting, backup, and retention policies.",
            "Store Terraform state in a controlled remote backend with access review.",
            "Define operational SLOs, incident ownership, and data retention/deletion rules.",
            "Run security review for IAM least privilege, network egress, logs, and audit trails."
        )
    }
    paths = [ordered]@{
        cloud_evidence = $evidencePath
        customer_summary = $summaryPath
        final_audit = $auditPath
        customer_demo_once = $demoOncePath
        web_deploy = $webDeployPath
        web_diagnostics = $webDiagPath
        lifecycle_guard = $lifecyclePath
    }
}

$jsonPath = Join-Path $OutputDir "customer_handoff_latest.json"
$mdPath = Join-Path $OutputDir "customer_handoff.md"
$htmlPath = Join-Path $OutputDir "customer_handoff.html"
Write-HandoffFiles -Handoff $handoff -JsonPath $jsonPath -MarkdownPath $mdPath -HtmlPath $htmlPath

if ($PublishToEvidence) {
    New-Item -ItemType Directory -Force -Path $publicEvidenceDir | Out-Null
    Copy-Item -LiteralPath $jsonPath -Destination (Join-Path $publicEvidenceDir "customer_handoff.json") -Force
    Copy-Item -LiteralPath $mdPath -Destination (Join-Path $publicEvidenceDir "customer_handoff.md") -Force
    Copy-Item -LiteralPath $htmlPath -Destination (Join-Path $publicEvidenceDir "customer_handoff.html") -Force
}

Write-Host "Customer handoff status: $($handoff.status)" -ForegroundColor ($(if ($handoff.status -eq "ready_for_customer_handoff") { "Green" } elseif ($handoff.status -eq "failed") { "Red" } else { "Yellow" }))
Write-Host "Customer handoff JSON: $jsonPath"
Write-Host "Customer handoff report: $mdPath"
Write-Host "Customer handoff HTML: $htmlPath"
if ($RequireCloudSuccess -and $handoff.status -ne "ready_for_customer_handoff") {
    exit 1
}
