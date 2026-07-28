param(
    [string]$BaseUrl = "http://127.0.0.1:8788",

    [switch]$AllowNoCloudEvidence
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Get-Json {
    param([string]$Url)
    Invoke-RestMethod -Method Get -Uri $Url -Headers @{ "Cache-Control" = "no-cache" }
}

$base = $BaseUrl.TrimEnd("/")
Write-Host "Verifying customer demo at $base" -ForegroundColor Cyan

$health = Get-Json "$base/api/health"
Assert-True ([bool]$health.ok) "Health check failed."
Write-Host "  ok: health"

$evidence = Get-Json "$base/api/cloud/e2e-evidence"
if (-not $evidence.available) {
    if ($AllowNoCloudEvidence) {
        Write-Host "  warning: no real cloud evidence is published yet" -ForegroundColor Yellow
        exit 0
    }
    throw "No real cloud E2E evidence is published. Run 05_run_real_e2e.ps1 first."
}

Assert-True ($evidence.status -eq "success") "Cloud E2E job did not finish successfully. status=$($evidence.status)"
Assert-True ([int]$evidence.gold_row_count -gt 0) "Cloud E2E gold output is empty."
Assert-True (-not [bool]$evidence.direct_rfc_exposed) "Cloud E2E evidence reports direct RFC exposure."
Assert-True (-not [bool]$evidence.duckdb_used) "Cloud E2E evidence reports DuckDB usage."

Write-Host "  ok: cloud evidence"
Write-Host "  run_id: $($evidence.run_id)"
Write-Host "  gold_rows: $($evidence.gold_row_count)"
Write-Host "  gold_prefix: $($evidence.gold_prefix)"

$goldQuery = Get-Json "$base/api/cloud/gold-query"
Assert-True ([bool]$goldQuery.available) "Cloud gold query API is not available."
Assert-True ([int]$goldQuery.filtered_count -gt 0) "Cloud gold query API returned no rows."
Assert-True ([int]$goldQuery.summary.group_count -gt 0) "Cloud gold query summary has no groups."
Write-Host "  ok: gold query API"

$summary = Get-Json "$base/cloud-evidence/customer_demo_summary.json"
Assert-True ($summary.status -eq "ready_for_customer_demo") "Customer demo summary is not ready."
Assert-True ($summary.job_status -eq "success") "Customer demo summary does not report a successful job."
Assert-True ([int]$summary.gold_row_count -gt 0) "Customer demo summary has no gold rows."
Assert-True (-not [bool]$summary.direct_rfc_exposed) "Customer demo summary reports direct RFC exposure."
Assert-True (-not [bool]$summary.duckdb_used) "Customer demo summary reports DuckDB usage."
Write-Host "  ok: customer report summary"

Write-Host "Customer demo verification passed." -ForegroundColor Green
