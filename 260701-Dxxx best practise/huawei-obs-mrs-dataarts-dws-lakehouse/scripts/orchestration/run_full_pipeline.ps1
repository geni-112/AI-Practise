param(
  [string]$RunDir = (Join-Path (Get-Location) "dockone-run"),
  [double]$TargetMiB = 50,
  [string]$Bucket = $env:DEPLOYMENT_OBS_BUCKET,
  [string]$Region = $(if ($env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION } else { "la-south-2" }),
  [string]$MrsClusterId = $env:DEPLOYMENT_MRS_CLUSTER_ID,
  [string]$DataArtsWorkspaceId = $env:DATAARTS_WORKSPACE_ID,
  [string]$DataArtsMrsJob = "dockone_obs_mrs_iceberg_golden",
  [string]$DataArtsDwsJob = "dockone_golden_to_dws",
  [switch]$DirectMrsSubmit,
  [switch]$SkipDwsLoad,
  [switch]$SkipQuery
)

$ErrorActionPreference = "Stop"
$SkillRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$Scripts = Join-Path $SkillRoot "scripts"
$BatchScripts = Join-Path $Scripts "batch"
$MrsScripts = Join-Path $Scripts "mrs"
$DataArtsScripts = Join-Path $Scripts "dataarts"
$DwsScripts = Join-Path $Scripts "dws"
$DataDir = Join-Path $RunDir "data"
$RuntimeDir = Join-Path $RunDir "runtime"
New-Item -ItemType Directory -Force -Path $RunDir, $RuntimeDir | Out-Null

function Run-Step([string]$Name, [scriptblock]$Block) {
  $start = Get-Date
  Write-Host "==> $Name started $($start.ToString("s"))"
  & $Block
  $end = Get-Date
  Write-Host "==> $Name finished $($end.ToString("s")) duration=$([int]($end-$start).TotalSeconds)s"
}

if (-not $Bucket) { throw "Missing DEPLOYMENT_OBS_BUCKET or -Bucket" }

Run-Step "Generate raw CDC" {
  python (Join-Path $BatchScripts "generate_dockone_cdc.py") --target-mib $TargetMiB --out $DataDir
}

Run-Step "Upload raw to OBS" {
  python (Join-Path $BatchScripts "upload_raw_to_obs.py") --data-dir $DataDir --bucket $Bucket --region $Region
}

Run-Step "Upload MRS assets" {
  python (Join-Path $BatchScripts "upload_mrs_assets.py") --data-dir $DataDir --bucket $Bucket --region $Region
}

if ($DirectMrsSubmit) {
  if (-not $MrsClusterId) { throw "Missing DEPLOYMENT_MRS_CLUSTER_ID or -MrsClusterId" }
  Run-Step "Run MRS Iceberg job directly" {
    python (Join-Path $MrsScripts "run_mrs_iceberg_job.py") --bucket $Bucket --cluster-id $MrsClusterId --region $Region --summary (Join-Path $RunDir "mrs-iceberg-job-summary.json")
  }
} else {
  if (-not $DataArtsWorkspaceId) { throw "Missing DATAARTS_WORKSPACE_ID or -DataArtsWorkspaceId" }
  Run-Step "Trigger DataArts MRS pipeline" {
    python (Join-Path $DataArtsScripts "trigger_dataarts_job.py") --job-name $DataArtsMrsJob --workspace-id $DataArtsWorkspaceId --region $Region --summary (Join-Path $RunDir "dataarts-mrs-summary.json")
  }
}

Run-Step "Download Golden CSV" {
  python (Join-Path $DwsScripts "download_golden_csv.py") --bucket $Bucket --region $Region --out (Join-Path $RuntimeDir "dockone_table_metrics.csv")
}

if (-not $SkipDwsLoad) {
  Run-Step "Load Golden metrics into DWS" {
    python (Join-Path $DwsScripts "load_dws_table_metrics.py") --csv (Join-Path $RuntimeDir "dockone_table_metrics.csv")
  }
}

if ($DataArtsWorkspaceId) {
  Run-Step "Trigger DataArts DWS publish job" {
    python (Join-Path $DataArtsScripts "trigger_dataarts_job.py") --job-name $DataArtsDwsJob --workspace-id $DataArtsWorkspaceId --region $Region --summary (Join-Path $RunDir "dataarts-dws-summary.json")
  }
}

if (-not $SkipQuery) {
  Run-Step "Query DWS serving view" {
    python (Join-Path $DwsScripts "query_dws.py")
  }
}
