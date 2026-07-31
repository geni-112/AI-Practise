param(
  [string]$ProfilePath = (Join-Path $env:LOCALAPPDATA "Codex\huawei-mrs-observability\secrets.xml")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ProfilePath)) {
  throw "Encrypted monitor secret profile was not found. Run Set-MonitorSecretsDialog.ps1 first."
}

function Convert-ProfileSecret([securestring]$Value) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$profile = Import-Clixml -LiteralPath $ProfilePath
$env:GRAFANA_ADMIN_PASSWORD = Convert-ProfileSecret $profile.GrafanaAdminPassword
$env:MRS_DUMP_PASSWORD = Convert-ProfileSecret $profile.MrsDumpPassword
Write-Host "Monitor secrets loaded into this PowerShell process."
