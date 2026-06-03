param(
  [string]$Bucket = "docktest",
  [string]$Queue = "default",
  [string]$AgencyName = "dli_management_agency",
  [ValidateSet("dli", "mrs")]
  [string]$Engine = "dli",
  [string]$MrsClusterId = "",
  [switch]$TransientMrsCluster,
  [int]$SmokeTables = 1,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$argsList = @(
  "notebooks\run_notebook_auto.py",
  "--bucket", $Bucket,
  "--queue", $Queue,
  "--agency-name", $AgencyName,
  "--engine", $Engine,
  "--smoke-tables", $SmokeTables
)

if ($MrsClusterId) {
  $argsList += @("--mrs-cluster-id", $MrsClusterId)
}
if ($TransientMrsCluster) {
  $argsList += "--transient-mrs-cluster"
}
if ($DryRun) {
  $argsList += "--dry-run"
}

python @argsList
if ($LASTEXITCODE -ne 0) {
  throw "Notebook auto workflow failed with exit code $LASTEXITCODE"
}
