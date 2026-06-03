param(
  [string]$Bucket = "docktest",
  [string]$ClusterId = "",
  [switch]$TransientCluster,
  [int]$SmokeTables = 1,
  [switch]$SkipUpload,
  [switch]$DryRun,
  [switch]$UseDpapiFallback
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$DemoRoot = Join-Path $PackageRoot "demo"
$DataRoot = Join-Path $PackageRoot "data"

. (Join-Path $PSScriptRoot "Set-AgentHuaweiAuth.ps1") `
  -Region "la-south-2" `
  -ProjectName "la-south-2" `
  -Bucket $Bucket `
  -DemoRoot $DemoRoot `
  -UseDpapiFallback:$UseDpapiFallback

$env:DEMO_BUCKET = $Bucket
$env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"
$env:SYNTHETIC_CDC_DATA_PATH = $DataRoot

Set-Location -LiteralPath $DemoRoot

python scripts\06_validate_demo_package.py
if ($LASTEXITCODE -ne 0) { throw "Package validation failed." }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\01_package_jobs.ps1
if ($LASTEXITCODE -ne 0) { throw "Job packaging failed." }

if (-not (Test-Path -LiteralPath (Join-Path $DemoRoot "dist\hudi-spark3.3-bundle_2.12-0.15.0.jar"))) {
  powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Fetch-HudiBundle.ps1") -DemoRoot $DemoRoot
}

$executeArg = @()
if (-not $DryRun) { $executeArg += "--execute" }

if (-not $SkipUpload) {
  python scripts\07_create_minimal_chile_resources.py @executeArg --skip-dli
  if ($LASTEXITCODE -ne 0) { throw "OBS bucket ensure failed." }
  python scripts\02_upload_assets_to_obs.py @executeArg
  if ($LASTEXITCODE -ne 0) { throw "OBS asset upload failed." }
  python scripts\17_prepare_mrs_assets.py @executeArg
  if ($LASTEXITCODE -ne 0) { throw "MRS asset preparation failed." }
}

$mrsArgs = @("--limit", "$SmokeTables", "--interval-seconds", "45", "--max-polls", "100")
if (-not $DryRun) { $mrsArgs += "--execute" }
if ($TransientCluster) {
  $mrsArgs += @("--transient-cluster", "--wait-transient", "--transient-submit-mode", "manual")
} elseif ($ClusterId) {
  $mrsArgs += @("--cluster-id", $ClusterId)
} else {
  throw "Provide -ClusterId for existing MRS or pass -TransientCluster."
}

python -u scripts\18_run_mrs_dataflow_workflow.py @mrsArgs
if ($LASTEXITCODE -ne 0) { throw "MRS smoke workflow failed." }

