param(
  [string]$RunDir = (Join-Path (Get-Location) "dockone-stream-run"),
  [double]$TargetMiB = 8,
  [string]$Bucket = $env:DEPLOYMENT_OBS_BUCKET,
  [string]$Region = $(if ($env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION } else { "la-south-2" }),
  [string]$MrsClusterId = $env:DEPLOYMENT_MRS_CLUSTER_ID,
  [string]$DataArtsWorkspaceId = $env:DATAARTS_WORKSPACE_ID,
  [string]$KafkaBootstrapServers = $env:DMS_KAFKA_BOOTSTRAP_SERVERS,
  [string]$KafkaTopic = $(if ($env:DMS_KAFKA_TOPIC) { $env:DMS_KAFKA_TOPIC } else { "dockone.billing.contracts" }),
  [string]$DataArtsMrsJob = "dockone_obs_mrs_iceberg_golden",
  [string]$DataArtsDwsJob = "dockone_golden_to_dws",
  [switch]$SkipRdsLoad,
  [switch]$PublishFromJsonl,
  [switch]$SkipKafkaPublish,
  [switch]$UploadFlinkSql,
  [switch]$ContinueAfterFlink,
  [switch]$DirectMrsSubmit,
  [switch]$SkipDwsLoad,
  [switch]$SkipQuery
)

$ErrorActionPreference = "Stop"
$SkillRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$Scripts = Join-Path $SkillRoot "scripts"
$BatchScripts = Join-Path $Scripts "batch"
$DataArtsScripts = Join-Path $Scripts "dataarts"
$DwsScripts = Join-Path $Scripts "dws"
$MrsScripts = Join-Path $Scripts "mrs"
$StreamingScripts = Join-Path $Scripts "streaming"
$DataDir = Join-Path $RunDir "data"
$RuntimeDir = Join-Path $RunDir "runtime"
$FlinkSql = Join-Path $RunDir "flink_contracts_kafka_to_obs.sql"
$RenderBucket = $(if ($Bucket) { $Bucket } else { "<OBS_BUCKET>" })
$RenderBootstrapServers = $(if ($KafkaBootstrapServers) { $KafkaBootstrapServers } else { "<DMS_KAFKA_BOOTSTRAP_SERVERS>" })
New-Item -ItemType Directory -Force -Path $RunDir, $RuntimeDir | Out-Null

function Run-Step([string]$Name, [scriptblock]$Block) {
  $start = Get-Date
  Write-Host "==> $Name started $($start.ToString("s"))"
  & $Block
  $end = Get-Date
  Write-Host "==> $Name finished $($end.ToString("s")) duration=$([int]($end-$start).TotalSeconds)s"
}

Run-Step "Generate RDS contracts data" {
  python (Join-Path $StreamingScripts "generate_contracts_rds_data.py") --target-mib $TargetMiB --out $DataDir
}

if (-not $SkipRdsLoad) {
  Run-Step "Load contracts into RDS PostgreSQL" {
    python (Join-Path $StreamingScripts "load_contracts_to_postgres.py") --csv (Join-Path $DataDir "contracts.csv") --replace --summary (Join-Path $RunDir "contracts-rds-load-summary.json")
  }
}

if (-not $SkipKafkaPublish) {
  if (-not $KafkaBootstrapServers) { throw "Missing DMS_KAFKA_BOOTSTRAP_SERVERS or -KafkaBootstrapServers" }
  if ($PublishFromJsonl) {
    Run-Step "Publish generated contracts JSONL to DMS Kafka" {
      python (Join-Path $StreamingScripts "publish_contracts_to_dms_kafka.py") --source jsonl --jsonl (Join-Path $DataDir "contracts_cdc.jsonl") --topic $KafkaTopic --bootstrap-servers $KafkaBootstrapServers --summary (Join-Path $RunDir "contracts-kafka-publish-summary.json")
    }
  } else {
    Run-Step "Publish RDS contracts rows to DMS Kafka" {
      python (Join-Path $StreamingScripts "publish_contracts_to_dms_kafka.py") --source db --topic $KafkaTopic --bootstrap-servers $KafkaBootstrapServers --summary (Join-Path $RunDir "contracts-kafka-publish-summary.json")
    }
  }
}

Run-Step "Render MRS Flink SQL" {
  python (Join-Path $StreamingScripts "render_contracts_flink_sql.py") --bucket $RenderBucket --topic $KafkaTopic --bootstrap-servers $RenderBootstrapServers --out $FlinkSql
}

if ($UploadFlinkSql) {
  if (-not $Bucket) { throw "Missing DEPLOYMENT_OBS_BUCKET or -Bucket" }
  Run-Step "Upload Flink SQL to OBS" {
    python (Join-Path $StreamingScripts "upload_flink_contracts_assets.py") --sql $FlinkSql --bucket $Bucket --region $Region --summary (Join-Path $RunDir "flink-contracts-upload-summary.json")
  }
}

Write-Host "Flink SQL ready: $FlinkSql"
Write-Host "Submit this SQL on MRS Flink, then continue after it writes OBS raw JSON under raw/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.billing.contracts"

if ($ContinueAfterFlink) {
  if (-not $Bucket) { throw "Missing DEPLOYMENT_OBS_BUCKET or -Bucket" }
  Run-Step "Upload MRS Spark assets and streaming manifest" {
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
}
