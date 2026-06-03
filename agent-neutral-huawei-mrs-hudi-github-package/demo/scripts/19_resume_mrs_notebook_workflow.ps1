param(
  [string]$Bucket = "docktest",
  [string]$MrsClusterId = "",
  [int]$SmokeTables = 1,
  [switch]$TransientCluster,
  [switch]$ForceFallbackAuth,
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Invoke-Step([string]$Title, [scriptblock]$Command) {
  Write-Host ""
  Write-Host "== $Title =="
  & $Command
  if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "$Title failed with exit code $LASTEXITCODE"
  }
}

$env:HUAWEICLOUD_REGION = "la-south-2"
$env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"
$env:DEMO_BUCKET = $Bucket
if ($MrsClusterId) { $env:MRS_CLUSTER_ID = $MrsClusterId }

Write-Host "Using OBS bucket: $env:DEMO_BUCKET"
Write-Host "Using MRS cluster id: $env:MRS_CLUSTER_ID"
Write-Host "Transient MRS cluster: $TransientCluster"

if ($env:HUAWEICLOUD_ACCESS_KEY -and $env:HUAWEICLOUD_SECRET_KEY -and $env:HUAWEICLOUD_PROJECT_ID) {
  Write-Host "Using existing HUAWEICLOUD_* environment credentials."
} elseif ($ForceFallbackAuth) {
  Invoke-Step "Select Huawei Cloud authentication" { . scripts\14_select_huawei_auth.ps1 -ForceFallback }
} else {
  Invoke-Step "Select Huawei Cloud authentication" { . scripts\14_select_huawei_auth.ps1 }
}

Invoke-Step "Validate demo package" { python scripts\06_validate_demo_package.py }
Invoke-Step "Package Spark jobs" { powershell -ExecutionPolicy Bypass -File scripts\01_package_jobs.ps1 }

if ($Execute) {
  Invoke-Step "Ensure OBS bucket exists" { python scripts\07_create_minimal_chile_resources.py --execute --skip-dli }
  Invoke-Step "Upload Python and SQL assets to OBS" { python scripts\02_upload_assets_to_obs.py --execute }
  Invoke-Step "Prepare MRS Hudi assets" { python scripts\17_prepare_mrs_assets.py --execute }
  $mrsArgs = @("--execute", "--limit", $SmokeTables)
  if ($MrsClusterId) { $mrsArgs += @("--cluster-id", $MrsClusterId) }
  if ($TransientCluster) { $mrsArgs += @("--transient-cluster", "--wait-transient", "--transient-submit-mode", "manual") }
  Invoke-Step "Run MRS notebook dataflow workflow" { python scripts\18_run_mrs_dataflow_workflow.py @mrsArgs }
} else {
  Invoke-Step "Dry run OBS bucket ensure" { python scripts\07_create_minimal_chile_resources.py --skip-dli }
  Invoke-Step "Dry run OBS upload" { python scripts\02_upload_assets_to_obs.py }
  Invoke-Step "Dry run MRS Hudi assets" { python scripts\17_prepare_mrs_assets.py }
  $mrsArgs = @("--limit", $SmokeTables)
  if ($MrsClusterId) { $mrsArgs += @("--cluster-id", $MrsClusterId) }
  if ($TransientCluster) { $mrsArgs += @("--transient-cluster", "--wait-transient", "--transient-submit-mode", "manual") }
  Invoke-Step "Dry run MRS notebook dataflow workflow" { python scripts\18_run_mrs_dataflow_workflow.py @mrsArgs }
}
