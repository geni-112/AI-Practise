param(
  [string]$Bucket = "docktest",
  [string]$Queue = "default",
  [string]$AgencyName = "dli_management_agency",
  [int]$SmokeTables = 1,
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

function ConvertFrom-LocalSecureString([SecureString]$SecureValue) {
  if ($null -eq $SecureValue) {
    return ""
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$env:HUAWEICLOUD_REGION = "la-south-2"
$env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"
$env:DLI_ENDPOINT = "https://dli.la-south-2.myhuaweicloud.com"
$env:DEMO_BUCKET = $Bucket
$env:DLI_QUEUE_NAME = $Queue
$env:DLI_AGENCY_NAME = $AgencyName
$env:DLI_SPARK_VERSION = "3.3.1"
if (-not $env:DLI_AGENCY_URN) { $env:DLI_AGENCY_URN = "" }

Write-Host "Using OBS bucket: $env:DEMO_BUCKET"
Write-Host "Using DLI queue: $env:DLI_QUEUE_NAME"
Write-Host "Using DLI agency name: $env:DLI_AGENCY_NAME"

if ($ForceFallbackAuth) {
  Invoke-Step "Select Huawei Cloud authentication" { . scripts\14_select_huawei_auth.ps1 -ForceFallback }
} else {
  Invoke-Step "Select Huawei Cloud authentication" { . scripts\14_select_huawei_auth.ps1 }
}
$authMode = if ($env:HUAWEICLOUD_AUTH_MODE) { $env:HUAWEICLOUD_AUTH_MODE } else { "sdk" }
Write-Host "Active auth mode: $authMode"

Invoke-Step "Validate demo package" { python scripts\06_validate_demo_package.py }
Invoke-Step "Package DLI jobs" { powershell -ExecutionPolicy Bypass -File scripts\01_package_jobs.ps1 }

if ($Execute) {
  if ($env:HUAWEICLOUD_ACCESS_KEY -and $env:HUAWEICLOUD_SECRET_KEY) {
    Invoke-Step "Ensure OBS bucket exists" { python scripts\07_create_minimal_chile_resources.py --execute --skip-dli }
    Invoke-Step "Upload assets to OBS bucket" { python scripts\02_upload_assets_to_obs.py --execute }
  } else {
    throw "OBS upload/create needs AK/SK or temporary AK/SK. Active auth did not provide OBS credentials."
  }
  Invoke-Step "Build DLI payloads" { python scripts\03_build_dli_payloads.py }
  Invoke-Step "Run notebook dataflow workflow" { python scripts\16_run_dataflow_workflow.py --execute --limit $SmokeTables --auth $authMode --interval-seconds 15 --max-polls 20 }
} else {
  if ($env:HUAWEICLOUD_ACCESS_KEY -and $env:HUAWEICLOUD_SECRET_KEY) {
    Invoke-Step "Dry run OBS bucket ensure" { python scripts\07_create_minimal_chile_resources.py --skip-dli }
    Invoke-Step "Dry run OBS upload" { python scripts\02_upload_assets_to_obs.py }
  } else {
    Write-Host "Skipping OBS dry run because active auth has no OBS credentials."
  }
  Invoke-Step "Build DLI payloads" { python scripts\03_build_dli_payloads.py }
  Invoke-Step "Dry run notebook dataflow workflow" { python scripts\16_run_dataflow_workflow.py --limit $SmokeTables --auth $authMode }
}
