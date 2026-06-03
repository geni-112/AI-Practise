param(
  [switch]$Execute,
  [int]$SmokeTables = 1,
  [switch]$SkipDliJobs
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

function ConvertFrom-LocalSecureString([SecureString]$SecureValue) {
  if ($null -eq $SecureValue) {
    return ""
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Set-DpapiHuaweiEnv {
  $path = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata\credentials.xml"
  if (-not (Test-Path $path)) {
    throw "No DPAPI credential file found at $path"
  }

  $stored = Import-Clixml $path
  $env:HUAWEICLOUD_ACCESS_KEY = ConvertFrom-LocalSecureString $stored.AccessKey
  $env:HUAWEICLOUD_SECRET_KEY = ConvertFrom-LocalSecureString $stored.SecretKey
  $env:HUAWEICLOUD_ACCOUNT_NAME = $stored.AccountName
  $env:HUAWEICLOUD_ACCOUNT_PASSWORD = ConvertFrom-LocalSecureString $stored.AccountPassword
  $env:HUAWEICLOUD_REGION = if ($stored.Region) { $stored.Region } else { "la-south-2" }
  if ($stored.ProjectId) {
    $env:HUAWEICLOUD_PROJECT_ID = $stored.ProjectId
  }
}

function Set-DemoDefaults {
  if (-not $env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION = "la-south-2" }
  if ($env:HUAWEICLOUD_REGION -ne "la-south-2") {
    throw "This deployment is pinned to Chile LA-Santiago la-south-2, current region is $env:HUAWEICLOUD_REGION"
  }
  if (-not $env:OBS_ENDPOINT) { $env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com" }
  if (-not $env:DLI_ENDPOINT) { $env:DLI_ENDPOINT = "https://dli.la-south-2.myhuaweicloud.com" }
  if (-not $env:DLI_QUEUE_NAME) { $env:DLI_QUEUE_NAME = "dli_demo_min" }
  if (-not $env:DLI_SPARK_VERSION) { $env:DLI_SPARK_VERSION = "3.3.1" }
  if (-not $env:DLI_AGENCY_URN) { $env:DLI_AGENCY_URN = "" }
  if (-not $env:DEMO_BUCKET) {
    $suffix = (Get-Date -Format "yyyyMMddHHmmss")
    $env:DEMO_BUCKET = "dockone-dli-hudi-demo-$suffix"
  }
}

function Set-HuaweiProjectId {
  if ($env:HUAWEICLOUD_PROJECT_ID) {
    Write-Host "Huawei Cloud project id already set in environment."
    return
  }

  Invoke-Step "Discover Chile project with AK/SK" { python scripts\11_discover_project_with_aksk.py }
  $resolvedPath = Join-Path $root "runtime\resolved-project.json"
  if (-not (Test-Path $resolvedPath)) {
    throw "Project discovery did not create runtime\resolved-project.json"
  }
  $resolved = Get-Content $resolvedPath -Raw | ConvertFrom-Json
  if (-not $resolved.project_id) {
    throw "Project discovery did not return a project id."
  }
  $env:HUAWEICLOUD_PROJECT_ID = $resolved.project_id
  Write-Host "Huawei Cloud project id loaded for project_name=$($resolved.project_name)"
}

Set-DpapiHuaweiEnv
Set-DemoDefaults

Write-Host "Loaded local DPAPI credentials. Secret values are not printed."
Write-Host "Target region: $env:HUAWEICLOUD_REGION"
Write-Host "Target bucket: $env:DEMO_BUCKET"
Write-Host "Target DLI queue: $env:DLI_QUEUE_NAME"

Set-HuaweiProjectId

if ($SkipDliJobs) {
  $resourceArgs = @("--skip-dli")
  $uploadArgs = @()
  if ($Execute) {
    $resourceArgs = @("--execute", "--skip-dli")
    $uploadArgs = @("--execute")
  }
  Invoke-Step "Create minimal Chile resources" { python scripts\07_create_minimal_chile_resources.py @resourceArgs }
  Invoke-Step "Upload assets to OBS" { python scripts\02_upload_assets_to_obs.py @uploadArgs }
  exit 0
}

$deployArgs = @("-SmokeTables", $SmokeTables)
if ($Execute) {
  $deployArgs = @("-Execute", "-SmokeTables", $SmokeTables)
}
Invoke-Step "Run Chile minimal deployment workflow" { powershell -ExecutionPolicy Bypass -File scripts\08_deploy_chile_minimal.ps1 @deployArgs }
