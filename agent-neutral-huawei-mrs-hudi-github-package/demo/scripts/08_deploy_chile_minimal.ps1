param(
  [switch]$Execute,
  [int]$SmokeTables = 1
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Invoke-Step([string]$Title, [scriptblock]$Command) {
  Write-Host ""
  Write-Host "== $Title =="
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Title failed with exit code $LASTEXITCODE"
  }
}

if (-not $env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION = "la-south-2" }
if (-not $env:OBS_ENDPOINT) { $env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com" }
if (-not $env:DLI_ENDPOINT) { $env:DLI_ENDPOINT = "https://dli.la-south-2.myhuaweicloud.com" }
if (-not $env:DLI_QUEUE_NAME) { $env:DLI_QUEUE_NAME = "dli_demo_min" }
if (-not $env:DLI_SPARK_VERSION) { $env:DLI_SPARK_VERSION = "3.3.1" }
if (-not $env:DEMO_BUCKET) {
  $suffix = (Get-Date -Format "yyyyMMddHHmmss")
  $env:DEMO_BUCKET = "dockone-dli-hudi-demo-$suffix"
}

Write-Host "Target region: $env:HUAWEICLOUD_REGION"
Write-Host "Principle: minimal Chile deployment. Only OBS + DLI queue are created automatically."
Write-Host "Optional resources are not auto-created: CCE/JupyterHub, DWS, CDM, MRS."

Invoke-Step "Validate demo package" { python scripts\06_validate_demo_package.py }
Invoke-Step "Package DLI jobs" { powershell -ExecutionPolicy Bypass -File scripts\01_package_jobs.ps1 }

if ($Execute) {
  Invoke-Step "Create minimal Chile resources" { python scripts\07_create_minimal_chile_resources.py --execute }
  Invoke-Step "Upload assets to OBS" { python scripts\02_upload_assets_to_obs.py --execute }
  Invoke-Step "Build DLI payloads" { python scripts\03_build_dli_payloads.py }
  Invoke-Step "Submit DLI smoke jobs" { python scripts\04_submit_dli_jobs.py --execute --limit $SmokeTables }
  Invoke-Step "Poll DLI smoke jobs" { python scripts\05_poll_dli_jobs.py --execute }
} else {
  Invoke-Step "Dry run minimal Chile resources" { python scripts\07_create_minimal_chile_resources.py }
  Invoke-Step "Dry run OBS upload" { python scripts\02_upload_assets_to_obs.py }
  Invoke-Step "Build DLI payloads" { python scripts\03_build_dli_payloads.py }
  Invoke-Step "Dry run DLI smoke submit" { python scripts\04_submit_dli_jobs.py --limit $SmokeTables }
  Invoke-Step "Dry run DLI smoke poll" { python scripts\05_poll_dli_jobs.py }
}
