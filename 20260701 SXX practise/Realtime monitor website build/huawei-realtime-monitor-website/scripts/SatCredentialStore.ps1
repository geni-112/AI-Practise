$script:SatCredentialProfilePath = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-realtime-monitor\credential-profile.xml"

function Convert-SatSecureStringToPlainText([securestring]$SecureValue) {
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

function Get-SatCredentialProfile {
  if (-not (Test-Path -LiteralPath $script:SatCredentialProfilePath)) {
    return $null
  }
  $profile = Import-Clixml -LiteralPath $script:SatCredentialProfilePath
  [pscustomobject]@{
    AccountName = [string]$profile.AccountName
    IamUser = [string]$profile.IamUser
    Region = [string]$profile.Region
    ProjectId = [string]$profile.ProjectId
    Password = Convert-SatSecureStringToPlainText $profile.Password
    AccessKey = [string]$profile.AccessKey
    SecretKey = Convert-SatSecureStringToPlainText $profile.SecretKey
  }
}

function Save-SatCredentialProfile(
  [string]$AccountName,
  [string]$IamUser,
  [string]$Password,
  [string]$Region,
  [string]$ProjectId = ""
) {
  if (-not $AccountName -or -not $IamUser -or -not $Password) {
    throw "Account name, IAM user, and password are required to save the SAT credential profile."
  }
  $profileDir = Split-Path -Parent $script:SatCredentialProfilePath
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  [pscustomobject]@{
    AccountName = $AccountName
    IamUser = $IamUser
    Region = $Region
    ProjectId = $ProjectId
    Password = ConvertTo-SecureString -String $Password -AsPlainText -Force
  } | Export-Clixml -LiteralPath $script:SatCredentialProfilePath
  return $script:SatCredentialProfilePath
}

function Save-SatAkSkProfile(
  [string]$AccessKey,
  [string]$SecretKey,
  [string]$Region,
  [string]$ProjectId
) {
  if (-not $AccessKey -or -not $SecretKey -or -not $Region -or -not $ProjectId) {
    throw "Access key, secret key, region, and project id are required to save the SAT AK/SK profile."
  }
  $existing = Get-SatCredentialProfile
  $profileDir = Split-Path -Parent $script:SatCredentialProfilePath
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  [pscustomobject]@{
    AccountName = if ($existing) { $existing.AccountName } else { "" }
    IamUser = if ($existing) { $existing.IamUser } else { "" }
    Region = $Region
    ProjectId = $ProjectId
    Password = if ($existing -and $existing.Password) { ConvertTo-SecureString -String $existing.Password -AsPlainText -Force } else { $null }
    AccessKey = $AccessKey
    SecretKey = ConvertTo-SecureString -String $SecretKey -AsPlainText -Force
  } | Export-Clixml -LiteralPath $script:SatCredentialProfilePath
  return $script:SatCredentialProfilePath
}
