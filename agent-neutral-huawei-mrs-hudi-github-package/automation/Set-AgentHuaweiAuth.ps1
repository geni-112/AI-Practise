param(
  [string]$Region = "la-south-2",
  [string]$ProjectName = "",
  [string]$Bucket = "docktest",
  [string]$DemoRoot = "",
  [switch]$UseDpapiFallback
)

$ErrorActionPreference = "Stop"

if (-not $ProjectName) { $ProjectName = $Region }
$env:HUAWEICLOUD_REGION = $Region
$env:HUAWEICLOUD_PROJECT_NAME = $ProjectName
$env:DEMO_BUCKET = $Bucket
if (-not $env:OBS_ENDPOINT) {
  $env:OBS_ENDPOINT = "https://obs.$Region.myhuaweicloud.com"
}

if ($env:HUAWEICLOUD_ACCESS_KEY -and $env:HUAWEICLOUD_SECRET_KEY -and $env:HUAWEICLOUD_PROJECT_ID) {
  Write-Host "Using existing HUAWEICLOUD_* AK/SK environment for region=$Region."
  return
}

if ($env:HUAWEICLOUD_DOMAIN_NAME -and $env:HUAWEICLOUD_IAM_USER_NAME -and $env:HUAWEICLOUD_IAM_PASSWORD) {
  Write-Host "Exchanging IAM password for temporary project token and security token. Secrets will not be printed."
  $projectBody = @{
    auth = @{
      identity = @{
        methods = @("password")
        password = @{
          user = @{
            name = $env:HUAWEICLOUD_IAM_USER_NAME
            password = $env:HUAWEICLOUD_IAM_PASSWORD
            domain = @{ name = $env:HUAWEICLOUD_DOMAIN_NAME }
          }
        }
      }
      scope = @{ project = @{ name = $ProjectName } }
    }
  } | ConvertTo-Json -Depth 20

  $projectResponse = Invoke-WebRequest `
    -Method Post `
    -Uri "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true" `
    -ContentType "application/json" `
    -Body $projectBody `
    -UseBasicParsing

  $projectToken = $projectResponse.Headers["X-Subject-Token"]
  $project = (($projectResponse.Content | ConvertFrom-Json).token.project)

  $stsBody = @{ auth = @{ identity = @{ methods = @("token"); token = @{ duration_seconds = 3600 } } } } | ConvertTo-Json -Depth 10
  $stsResponse = Invoke-WebRequest `
    -Method Post `
    -Uri "https://iam.myhuaweicloud.com/v3.0/OS-CREDENTIAL/securitytokens" `
    -Headers @{ "X-Auth-Token" = $projectToken } `
    -ContentType "application/json" `
    -Body $stsBody `
    -UseBasicParsing
  $credential = (($stsResponse.Content | ConvertFrom-Json).credential)

  $env:HUAWEICLOUD_ACCESS_KEY = $credential.access
  $env:HUAWEICLOUD_SECRET_KEY = $credential.secret
  $env:HUAWEICLOUD_SECURITY_TOKEN = $credential.securitytoken
  $env:HUAWEICLOUD_PROJECT_ID = $project.id
  Write-Host "Temporary Huawei Cloud credentials acquired for project=$($project.name)."
  return
}

if ($UseDpapiFallback) {
  if (-not $DemoRoot) {
    $PackageRoot = Split-Path -Parent $PSScriptRoot
    $DemoRoot = Join-Path $PackageRoot "demo"
  }
  $selector = Join-Path $DemoRoot "scripts\14_select_huawei_auth.ps1"
  if (Test-Path -LiteralPath $selector) {
    Write-Host "Using local DPAPI fallback selector from demo scripts."
    . $selector -ForceFallback
    return
  }
}

throw "No usable Huawei Cloud auth found. Set temporary AK/SK env vars, set IAM env vars, or pass -UseDpapiFallback on the original Windows host."

