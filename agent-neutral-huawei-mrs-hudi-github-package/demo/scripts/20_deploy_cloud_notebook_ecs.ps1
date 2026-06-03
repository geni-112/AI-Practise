param(
  [string]$Bucket = "docktest",
  [string]$Name = "dockone-notebook-scheduler",
  [string]$AgencyName = "MRS_ECS_DEFAULT_AGENCY",
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

. .\scripts\14_select_huawei_auth.ps1 -ForceFallback

$secretDir = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata"
New-Item -ItemType Directory -Force -Path $secretDir | Out-Null

function New-SecretString([int]$Length = 32) {
  $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@$%^-_=+"
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  while ($true) {
    $bytes = New-Object byte[] $Length
    $rng.GetBytes($bytes)
    $value = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
    if ($value -cmatch "[A-Z]" -and $value -cmatch "[a-z]" -and $value -match "[0-9]" -and $value -match "[!@`$%\\^\\-_=\+]") {
      return $value
    }
  }
}

$env:ECS_ADMIN_PASSWORD = New-SecretString 24
$env:JUPYTER_TOKEN = New-SecretString 36
$env:DEMO_BUCKET = $Bucket
$env:CLOUD_NOTEBOOK_NAME = $Name
$env:ECS_AGENCY_NAME = $AgencyName

$secretPath = Join-Path $secretDir "cloud-notebook-credentials.xml"
[pscustomobject]@{
  ecs_admin_password = ConvertTo-SecureString $env:ECS_ADMIN_PASSWORD -AsPlainText -Force
  jupyter_token = ConvertTo-SecureString $env:JUPYTER_TOKEN -AsPlainText -Force
  name = $Name
  bucket = $Bucket
  created_at = (Get-Date).ToString("o")
} | Export-Clixml -Path $secretPath

$argsList = @("--name", $Name, "--bucket", $Bucket, "--agency-name", $AgencyName)
if ($Execute) { $argsList += "--execute" }

python .\scripts\20_deploy_cloud_notebook_ecs.py @argsList

Write-Host "Cloud notebook local credentials were stored with Windows DPAPI at: $secretPath"
