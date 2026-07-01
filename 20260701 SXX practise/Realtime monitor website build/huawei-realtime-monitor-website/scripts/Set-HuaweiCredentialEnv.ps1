param(
  [string]$Region = "la-north-2",
  [string]$ProjectId = "",
  [switch]$SaveEncryptedProfile,
  [switch]$RunInventory
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText([securestring]$SecureValue) {
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

$accountName = Read-Host "Huawei Cloud account name"
$iamUser = Read-Host "IAM user name"
$securePassword = Read-Host "IAM user password" -AsSecureString

$env:HUAWEICLOUD_ACCOUNT_NAME = $accountName
$env:HUAWEICLOUD_IAM_USER = $iamUser
$env:HUAWEICLOUD_IAM_PASSWORD = Convert-SecureStringToPlainText $securePassword
$env:HUAWEICLOUD_REGION = $Region
if ($ProjectId) {
  $env:HUAWEICLOUD_PROJECT_ID = $ProjectId
}

if ($SaveEncryptedProfile) {
  $profileDir = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-realtime-monitor"
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  $profilePath = Join-Path $profileDir "credential-profile.xml"
  [pscustomobject]@{
    AccountName = $accountName
    IamUser = $iamUser
    Region = $Region
    ProjectId = $ProjectId
    Password = $securePassword
  } | Export-Clixml -LiteralPath $profilePath
  Write-Host "Encrypted SAT Mexico credential profile saved under LOCALAPPDATA. It can only be decrypted by this Windows user."
}

Write-Host "Huawei Cloud environment variables are set for this PowerShell process."

if ($RunInventory) {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  python (Join-Path $PSScriptRoot "huawei_inventory.py")
  python (Join-Path $PSScriptRoot "analyze_bigdata_assets.py")
  Write-Host "Inventory and assessment completed."
}
