param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$DeployArgs
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $env:GRAFANA_ADMIN_PASSWORD -or -not $env:MRS_DUMP_PASSWORD) {
  . (Join-Path $PSScriptRoot "Load-MonitorSecretsProfile.ps1")
}
foreach ($name in @(
  "HUAWEICLOUD_ACCESS_KEY",
  "HUAWEICLOUD_SECRET_KEY",
  "HUAWEICLOUD_REGION",
  "HUAWEICLOUD_PROJECT_ID"
)) {
  if (-not [Environment]::GetEnvironmentVariable($name)) {
    throw "Required environment variable is missing: $name"
  }
}

python (Join-Path $PSScriptRoot "deploy_existing_host.py") @DeployArgs
if ($LASTEXITCODE -ne 0) {
  throw "Existing monitor deployment failed with exit code $LASTEXITCODE."
}
