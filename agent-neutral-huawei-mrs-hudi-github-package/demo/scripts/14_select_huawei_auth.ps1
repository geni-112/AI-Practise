$ForceFallback = $false
foreach ($arg in $args) {
  if ($arg -eq "-ForceFallback") {
    $ForceFallback = $true
  }
}

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function ConvertFrom-LocalSecureString([SecureString]$SecureValue) {
  if ($null -eq $SecureValue) {
    return ""
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Set-DefaultEndpoints {
  if (-not $env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION = "la-south-2" }
  if (-not $env:OBS_ENDPOINT) { $env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com" }
  if (-not $env:DLI_ENDPOINT) { $env:DLI_ENDPOINT = "https://dli.la-south-2.myhuaweicloud.com" }
}

function Write-ActiveAuth([string]$Mode, [string]$Source, [string]$ProjectId, [string]$ProjectName) {
  New-Item -ItemType Directory -Force -Path (Join-Path $root "runtime") | Out-Null
  @{
    mode = $Mode
    source = $Source
    project_id = $ProjectId
    project_name = $ProjectName
    region = $env:HUAWEICLOUD_REGION
    selected_at = (Get-Date).ToString("s")
  } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path (Join-Path $root "runtime\active-auth.json")
}

function Try-ExistingAkSk {
  $path = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata\credentials.xml"
  if (-not (Test-Path $path)) {
    Write-Host "No existing AK/SK DPAPI file found."
    return $false
  }

  $stored = Import-Clixml $path
  $env:HUAWEICLOUD_ACCESS_KEY = ConvertFrom-LocalSecureString $stored.AccessKey
  $env:HUAWEICLOUD_SECRET_KEY = ConvertFrom-LocalSecureString $stored.SecretKey
  $env:HUAWEICLOUD_REGION = "la-south-2"
  Set-DefaultEndpoints

  Write-Host "Testing existing AK/SK credentials..."
  python scripts\11_discover_project_with_aksk.py | Write-Host
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Existing AK/SK test failed. Will try IAM fallback credentials."
    $env:HUAWEICLOUD_ACCESS_KEY = ""
    $env:HUAWEICLOUD_SECRET_KEY = ""
    return $false
  }

  $resolved = Get-Content (Join-Path $root "runtime\resolved-project.json") -Raw | ConvertFrom-Json
  $env:HUAWEICLOUD_PROJECT_ID = $resolved.project_id
  $env:HUAWEICLOUD_AUTH_MODE = "sdk"
  Write-ActiveAuth "sdk" "existing-aksk-dpapi" $resolved.project_id $resolved.project_name
  Write-Host "Using existing AK/SK credentials for project_name=$($resolved.project_name)."
  return $true
}

function Use-IamFallback {
  $path = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata\iam-fallback-credentials.xml"
  if (-not (Test-Path $path)) {
    throw "No IAM fallback credential file found at $path. Run scripts\13_capture_iam_fallback_credentials.ps1 first."
  }

  $stored = Import-Clixml $path
  $domain = $stored.DomainName
  $user = $stored.IamUserName
  $password = ConvertFrom-LocalSecureString $stored.IamPassword
  $region = if ($stored.Region) { $stored.Region } else { "la-south-2" }
  $env:HUAWEICLOUD_REGION = $region
  Set-DefaultEndpoints

  Write-Host "Testing IAM fallback credentials for region=$region..."
  $body = @{
    auth = @{
      identity = @{
        methods = @("password")
        password = @{
          user = @{
            domain = @{ name = $domain }
            name = $user
            password = $password
          }
        }
      }
      scope = @{ project = @{ name = $region } }
    }
  } | ConvertTo-Json -Depth 10

  try {
    $resp = Invoke-WebRequest `
      -Uri "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true" `
      -Method Post `
      -ContentType "application/json;charset=utf8" `
      -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
      -UseBasicParsing
  }
  catch {
    throw "IAM fallback login failed: $($_.Exception.Message)"
  }

  $token = $resp.Headers["X-Subject-Token"]
  $json = $resp.Content | ConvertFrom-Json
  $projectId = $json.token.project.id
  $projectName = $json.token.project.name
  if (-not $token -or -not $projectId) {
    throw "IAM fallback response did not include token/project id."
  }

  $env:HUAWEICLOUD_X_AUTH_TOKEN = $token
  $env:HUAWEICLOUD_PROJECT_ID = $projectId
  $env:HUAWEICLOUD_AUTH_MODE = "token"

  $stsBody = @{
    auth = @{
      identity = @{
        methods = @("token")
        token = @{ duration_seconds = 3600 }
      }
    }
  } | ConvertTo-Json -Depth 10

  try {
    $stsResp = Invoke-WebRequest `
      -Uri "https://iam.myhuaweicloud.com/v3.0/OS-CREDENTIAL/securitytokens" `
      -Method Post `
      -ContentType "application/json;charset=utf8" `
      -Headers @{ "X-Auth-Token" = $token } `
      -Body ([System.Text.Encoding]::UTF8.GetBytes($stsBody)) `
      -UseBasicParsing
    $stsJson = $stsResp.Content | ConvertFrom-Json
    $credential = $stsJson.credential
    if ($credential.access -and $credential.secret -and $credential.securitytoken) {
      $env:HUAWEICLOUD_ACCESS_KEY = $credential.access
      $env:HUAWEICLOUD_SECRET_KEY = $credential.secret
      $env:HUAWEICLOUD_SECURITY_TOKEN = $credential.securitytoken
      $env:HUAWEICLOUD_TEMP_CREDENTIALS = "1"
      Write-Host "Temporary AK/SK acquired for OBS operations."
    } else {
      Write-Host "Temporary AK/SK response did not include all fields. OBS create/upload may require permanent AK/SK."
    }
  }
  catch {
    Write-Host "Could not obtain temporary AK/SK from IAM token. OBS create/upload may require permanent AK/SK. Error: $($_.Exception.Message)"
  }

  Write-ActiveAuth "token" "iam-fallback-dpapi" $projectId $projectName
  Write-Host "Using IAM fallback token for project_name=$projectName."
}

Set-DefaultEndpoints
if ($ForceFallback) {
  Write-Host "ForceFallback requested. Skipping existing AK/SK test."
  Use-IamFallback
}
elseif (-not (Try-ExistingAkSk)) {
  Use-IamFallback
}
