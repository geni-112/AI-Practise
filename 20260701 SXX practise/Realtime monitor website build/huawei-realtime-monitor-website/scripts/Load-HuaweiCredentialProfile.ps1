param(
  [string]$ProfilePath = ""
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText([securestring]$SecureValue) {
  if (-not $SecureValue) {
    return ""
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

if (-not $ProfilePath) {
  $ProfilePath = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-realtime-monitor\credential-profile.xml"
}

$profile = Import-Clixml -LiteralPath $ProfilePath
$env:HUAWEICLOUD_ACCOUNT_NAME = $profile.AccountName
$env:HUAWEICLOUD_IAM_USER = $profile.IamUser
$env:HUAWEICLOUD_IAM_PASSWORD = Convert-SecureStringToPlainText $profile.Password
$env:HUAWEICLOUD_REGION = $profile.Region
if ($profile.ProjectId) {
  $env:HUAWEICLOUD_PROJECT_ID = $profile.ProjectId
}
if ($profile.AccessKey) {
  $env:HUAWEICLOUD_ACCESS_KEY = $profile.AccessKey
}
if ($profile.SecretKey) {
  $env:HUAWEICLOUD_SECRET_KEY = Convert-SecureStringToPlainText $profile.SecretKey
}

Write-Host "SAT Mexico Huawei Cloud credential profile loaded into this PowerShell process."
