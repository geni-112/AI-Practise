param(
  [string]$Bucket = "docktest",
  [string]$ClusterId = "",
  [switch]$TransientCluster,
  [int]$SmokeTables = 1,
  [switch]$UseDpapiFallback
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$DemoRoot = Join-Path $PackageRoot "demo"
$DataRoot = Join-Path $PackageRoot "data"

$env:SYNTHETIC_CDC_DATA_PATH = $DataRoot
. (Join-Path $PSScriptRoot "Set-AgentHuaweiAuth.ps1") `
  -Region "la-south-2" `
  -ProjectName "la-south-2" `
  -Bucket $Bucket `
  -DemoRoot $DemoRoot `
  -UseDpapiFallback:$UseDpapiFallback

Set-Location -LiteralPath $DemoRoot

$argsList = @("-Engine", "mrs", "-Bucket", $Bucket, "-SmokeTables", "$SmokeTables")
if ($ClusterId) { $argsList += @("-MrsClusterId", $ClusterId) }
if ($TransientCluster) { $argsList += "-TransientMrsCluster" }
if (-not $ClusterId -and -not $TransientCluster) {
  throw "Provide -ClusterId for existing MRS or pass -TransientCluster."
}

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 @argsList
if ($LASTEXITCODE -ne 0) { throw "Notebook smoke workflow failed." }

