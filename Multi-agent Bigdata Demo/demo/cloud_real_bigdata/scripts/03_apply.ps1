param(
    [Parameter(Mandatory = $true)]
    [string]$ObsBucketName,

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$RunId = "manual",

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$EnableWebEcs,

    [switch]$SubmitSmokeJob,

    [switch]$AllowOpenIngressForDemo,

    [switch]$AllowLongLivedDemo,

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Mirror-HuaweiEnv {
    if ($env:HUAWEICLOUD_ACCESS_KEY -and -not $env:HW_ACCESS_KEY) { $env:HW_ACCESS_KEY = $env:HUAWEICLOUD_ACCESS_KEY }
    if ($env:HUAWEICLOUD_SECRET_KEY -and -not $env:HW_SECRET_KEY) { $env:HW_SECRET_KEY = $env:HUAWEICLOUD_SECRET_KEY }
    if ($env:HUAWEICLOUD_REGION -and -not $env:HW_REGION_NAME) { $env:HW_REGION_NAME = $env:HUAWEICLOUD_REGION }
    if ($env:HUAWEICLOUD_PROJECT_ID -and -not $env:HW_PROJECT_ID) { $env:HW_PROJECT_ID = $env:HUAWEICLOUD_PROJECT_ID }
}

Mirror-HuaweiEnv

if (-not $NodeKeyPairName) {
    throw "NodeKeyPairName is required. Pass -NodeKeyPairName or set TF_VAR_node_key_pair_name."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tfDir = Resolve-Path (Join-Path $scriptDir "..\terraform")

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet
Mirror-HuaweiEnv
if (-not $NodeKeyPairName -and $env:TF_VAR_node_key_pair_name) {
    $NodeKeyPairName = $env:TF_VAR_node_key_pair_name
}

$env:TF_VAR_obs_bucket_name = $ObsBucketName
$env:TF_VAR_node_key_pair_name = $NodeKeyPairName
$env:TF_VAR_run_id = $RunId
$env:TF_VAR_enable_dws = if ($EnableDws) { "true" } else { "false" }
$env:TF_VAR_enable_dataarts = if ($EnableDataArts) { "true" } else { "false" }
$env:TF_VAR_enable_web_ecs = if ($EnableWebEcs) { "true" } else { "false" }
$env:TF_VAR_submit_smoke_job = if ($SubmitSmokeJob) { "true" } else { "false" }

& (Join-Path $scriptDir "14_validate_apply_safety.ps1") `
    -EnableWebEcs:$EnableWebEcs `
    -Apply:$Apply `
    -AllowOpenIngressForDemo:$AllowOpenIngressForDemo

& (Join-Path $scriptDir "16_validate_lifecycle_guard.ps1") `
    -Apply:$Apply `
    -AllowLongLivedDemo:$AllowLongLivedDemo

& (Join-Path $scriptDir "02_validate_env.ps1") -RequireDws:$EnableDws

# Safety and lifecycle checks reload the persisted environment. Re-apply the
# command-scoped switches so this invocation remains authoritative.
$env:TF_VAR_obs_bucket_name = $ObsBucketName
$env:TF_VAR_node_key_pair_name = $NodeKeyPairName
$env:TF_VAR_run_id = $RunId
$env:TF_VAR_enable_dws = if ($EnableDws) { "true" } else { "false" }
$env:TF_VAR_enable_dataarts = if ($EnableDataArts) { "true" } else { "false" }
$env:TF_VAR_enable_web_ecs = if ($EnableWebEcs) { "true" } else { "false" }
$env:TF_VAR_submit_smoke_job = if ($SubmitSmokeJob) { "true" } else { "false" }

Write-Host ""
Write-Host "SAT Agentic real-cloud resource switches" -ForegroundColor Cyan
Write-Host "  OBS/VPC/SecurityGroup/MRS : enabled"
Write-Host "  DWS SQL serving           : $($EnableDws.IsPresent)"
Write-Host "  DataArts prepaid instance : $($EnableDataArts.IsPresent)"
Write-Host "  Web ECS + EIP             : $($EnableWebEcs.IsPresent)"
Write-Host "  MRS smoke job             : $($SubmitSmokeJob.IsPresent)"
Write-Host "  Open ingress override     : $($AllowOpenIngressForDemo.IsPresent)"
Write-Host "  Long-lived demo override  : $($AllowLongLivedDemo.IsPresent)"
if ($EnableDataArts) {
    Write-Host "  note: DataArts Studio is prepaid in the Terraform provider." -ForegroundColor Yellow
}

Push-Location $tfDir
try {
    terraform init
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    terraform plan -out tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }

    if ($Apply) {
        terraform apply tfplan
        if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }
        terraform output
    }
    else {
        Write-Host ""
        Write-Host "Plan complete. Re-run with -Apply to create real cloud resources." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
