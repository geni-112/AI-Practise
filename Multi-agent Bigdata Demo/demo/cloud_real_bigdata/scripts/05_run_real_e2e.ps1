param(
    [Parameter(Mandatory = $true)]
    [string]$ObsBucketName,

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$RunId = "",

    [string]$Prompt = "",

    [string]$PromptFile = "",

    [string]$Scenario = "sat_padron_base_anual",

    [switch]$UseMaaS,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$EnableWebEcs,

    [string]$SshKeyPath = "",

    [string]$SshUser = "root",

    [switch]$SkipWebDeploy,

    [switch]$DestroyOnFailure,

    [switch]$AllowOpenIngressForDemo,

    [switch]$AllowLongLivedDemo,

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$script:RunTrace = [ordered]@{
    status = "running"
    mode = "unknown"
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
    options = [ordered]@{}
    steps = @()
    outputs = [ordered]@{}
    error = $null
}
$script:RunTracePaths = @()

function Write-RunTrace {
    if (-not $script:RunTracePaths -or $script:RunTracePaths.Count -eq 0) {
        return
    }
    $script:RunTrace.updated_at = (Get-Date).ToUniversalTime().ToString("o")
    foreach ($path in $script:RunTracePaths) {
        if (-not $path) { continue }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
        $script:RunTrace | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    }
}

function Add-TraceStep {
    param(
        [string]$Name,
        [string]$Status = "started",
        [string]$Detail = ""
    )
    $script:RunTrace.steps += [ordered]@{
        at = (Get-Date).ToUniversalTime().ToString("o")
        name = $Name
        status = $Status
        detail = $Detail
    }
    Write-RunTrace
}

function Set-TraceOutput {
    param(
        [string]$Name,
        [object]$Value
    )
    $script:RunTrace.outputs[$Name] = $Value
    Write-RunTrace
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
    Add-TraceStep -Name $Message
}

function Mirror-HuaweiEnv {
    if ($env:HUAWEICLOUD_ACCESS_KEY -and -not $env:HW_ACCESS_KEY) { $env:HW_ACCESS_KEY = $env:HUAWEICLOUD_ACCESS_KEY }
    if ($env:HUAWEICLOUD_SECRET_KEY -and -not $env:HW_SECRET_KEY) { $env:HW_SECRET_KEY = $env:HUAWEICLOUD_SECRET_KEY }
    if ($env:HUAWEICLOUD_REGION -and -not $env:HW_REGION_NAME) { $env:HW_REGION_NAME = $env:HUAWEICLOUD_REGION }
    if ($env:HUAWEICLOUD_PROJECT_ID -and -not $env:HW_PROJECT_ID) { $env:HW_PROJECT_ID = $env:HUAWEICLOUD_PROJECT_ID }
}

$script:DestroyEligible = $false
trap {
    $script:RunTrace.status = "failed"
    $script:RunTrace.error = [ordered]@{
        at = (Get-Date).ToUniversalTime().ToString("o")
        message = $_.Exception.Message
        category = [string]$_.CategoryInfo.Category
    }
    Write-RunTrace
    if ($DestroyOnFailure -and $script:DestroyEligible) {
        Write-Host ""
        Write-Host "E2E failed after real apply started. Running destroy because -DestroyOnFailure was set." -ForegroundColor Yellow
        try {
            & (Join-Path $scriptDir "04_destroy.ps1") -ConfirmDestroy -AutoApprove
        }
        catch {
            Write-Host "Automatic destroy also failed. Inspect Terraform state before retrying." -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
        }
    }
    break
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$tfDir = Resolve-Path (Join-Path $scriptDir "..\terraform")
$publicEvidenceDir = Join-Path $root "cloud_real_bigdata\public_evidence"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$Python = if (Test-Path $venvPython) { $venvPython } else { "python" }
$latestTracePath = Join-Path $root ".cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json"
$script:RunTracePaths += $latestTracePath
$script:RunTrace.mode = if ($Apply) { "apply" } else { "plan" }
$script:RunTrace.options = [ordered]@{
    enable_dws = [bool]$EnableDws
    enable_dataarts = [bool]$EnableDataArts
    enable_web_ecs = [bool]$EnableWebEcs
    skip_web_deploy = [bool]$SkipWebDeploy
    destroy_on_failure = [bool]$DestroyOnFailure
    use_maas = [bool]$UseMaaS
    allow_open_ingress_for_demo = [bool]$AllowOpenIngressForDemo
    allow_long_lived_demo = [bool]$AllowLongLivedDemo
}
Set-TraceOutput -Name "latest_trace_path" -Value $latestTracePath

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet
Mirror-HuaweiEnv
if (-not $NodeKeyPairName -and $env:TF_VAR_node_key_pair_name) {
    $NodeKeyPairName = $env:TF_VAR_node_key_pair_name
}
if ($NodeKeyPairName) {
    $env:TF_VAR_node_key_pair_name = $NodeKeyPairName
}
& (Join-Path $scriptDir "14_validate_apply_safety.ps1") `
    -EnableWebEcs:$EnableWebEcs `
    -Apply:$Apply `
    -AllowOpenIngressForDemo:$AllowOpenIngressForDemo
& (Join-Path $scriptDir "16_validate_lifecycle_guard.ps1") `
    -Apply:$Apply `
    -AllowLongLivedDemo:$AllowLongLivedDemo
if ($Apply -and $EnableWebEcs -and -not $SkipWebDeploy) {
    if (-not $SshKeyPath) {
        throw "EnableWebEcs requires -SshKeyPath unless -SkipWebDeploy is set."
    }
    if (-not (Test-Path -LiteralPath $SshKeyPath)) {
        throw "SSH key path not found: $SshKeyPath"
    }
}
if ($DestroyOnFailure -and -not $Apply) {
    Write-Host ""
    Write-Host "-DestroyOnFailure is ignored in plan-only mode." -ForegroundColor Yellow
}
if ($PromptFile -and -not (Test-Path -LiteralPath $PromptFile)) {
    throw "Prompt file not found: $PromptFile"
}

Write-Step "Create local agent package from business prompt"
$agentArgs = @(
    (Join-Path $scriptDir "create_agent_run_package.py"),
    "--scenario", $Scenario
)
if ($UseMaaS) { $agentArgs += "--use-maas" }
if ($PromptFile) {
    $agentArgs += "--prompt-file"
    $agentArgs += (Resolve-Path -LiteralPath $PromptFile)
}
elseif ($Prompt) {
    $agentArgs += "--prompt"
    $agentArgs += $Prompt
}

Push-Location $root
try {
    $agentOutput = & $Python @agentArgs
    if ($LASTEXITCODE -ne 0) { throw "Agent package generation failed." }
}
finally {
    Pop-Location
}

$agentText = ($agentOutput | Out-String).Trim()
$agentRun = $agentText | ConvertFrom-Json
if (-not $RunId) {
    $RunId = $agentRun.run_id
}
$agentGeneratedDirRelative = "generated\$($agentRun.run_id)"
$agentGeneratedDirAbsolute = Join-Path $root $agentGeneratedDirRelative
if (-not (Test-Path -LiteralPath $agentGeneratedDirAbsolute)) {
    throw "Agent generated directory not found: $agentGeneratedDirAbsolute"
}
$agentReleasePrefix = "obs://$ObsBucketName/release/$RunId/agent_generated/"
Write-Host "  agent run id : $($agentRun.run_id)"
Write-Host "  cloud run id : $RunId"
Write-Host "  generated dir: $agentGeneratedDirAbsolute"
Set-TraceOutput -Name "agent_run_id" -Value $agentRun.run_id
Set-TraceOutput -Name "run_id" -Value $RunId
Set-TraceOutput -Name "obs_bucket_name" -Value $ObsBucketName
Set-TraceOutput -Name "agent_generated_dir" -Value $agentGeneratedDirAbsolute
Set-TraceOutput -Name "agent_release_prefix" -Value $agentReleasePrefix

$workDir = Join-Path $root ".cloud_real_bigdata_work\$RunId"
$evidencePath = Join-Path $workDir "e2e_result.json"
$runTracePath = Join-Path $workDir "operator_run_trace.json"
$script:RunTracePaths += $runTracePath
Set-TraceOutput -Name "work_dir" -Value $workDir
Set-TraceOutput -Name "run_trace_path" -Value $runTracePath

Write-Step "Validate local environment"
& (Join-Path $scriptDir "02_validate_env.ps1") -RequireDws:$EnableDws

Write-Step "Create or plan base real resources"
$applyParams = @{
    ObsBucketName = $ObsBucketName
    NodeKeyPairName = $NodeKeyPairName
    RunId = $RunId
}
if ($EnableDws) { $applyParams.EnableDws = $true }
if ($EnableDataArts) { $applyParams.EnableDataArts = $true }
if ($EnableWebEcs) { $applyParams.EnableWebEcs = $true }
if ($AllowOpenIngressForDemo) { $applyParams.AllowOpenIngressForDemo = $true }
if ($AllowLongLivedDemo) { $applyParams.AllowLongLivedDemo = $true }
if ($Apply) {
    $script:DestroyEligible = $true
    $applyParams.Apply = $true
}
& (Join-Path $scriptDir "03_apply.ps1") @applyParams
Add-TraceStep -Name "Terraform base resources plan/apply finished" -Status "completed"

if (-not $Apply) {
    Write-Host ""
    Write-Host "Plan-only mode finished. Re-run with -Apply to create resources, upload data, submit MRS, and fetch gold output." -ForegroundColor Yellow
    $script:RunTrace.status = "planned"
    $script:RunTrace.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    Write-RunTrace
    exit 0
}

Write-Step "Upload sample raw data and reviewed Spark script to OBS"
Push-Location $root
try {
    & $Python (Join-Path $scriptDir "generate_sample_and_upload.py") `
        --bucket $ObsBucketName `
        --run-id $RunId `
        --agent-run-id $agentRun.run_id `
        --generated-run-dir $agentGeneratedDirRelative
}
finally {
    Pop-Location
}
Set-TraceOutput -Name "raw_object" -Value "obs://$ObsBucketName/raw/sat/$RunId/taxpayer_registry.csv"
Set-TraceOutput -Name "spark_script" -Value "obs://$ObsBucketName/scripts/sat_taxpayer_etl.py"
Add-TraceStep -Name "OBS sample and release upload finished" -Status "completed"

Write-Step "Submit MRS Spark smoke job through Terraform"
$submitParams = @{
    ObsBucketName = $ObsBucketName
    NodeKeyPairName = $NodeKeyPairName
    RunId = $RunId
    SubmitSmokeJob = $true
    Apply = $true
}
if ($EnableDws) { $submitParams.EnableDws = $true }
if ($EnableDataArts) { $submitParams.EnableDataArts = $true }
if ($EnableWebEcs) { $submitParams.EnableWebEcs = $true }
if ($AllowOpenIngressForDemo) { $submitParams.AllowOpenIngressForDemo = $true }
if ($AllowLongLivedDemo) { $submitParams.AllowLongLivedDemo = $true }
$maxSubmitAttempts = 6
$submitSucceeded = $false
for ($attempt = 1; $attempt -le $maxSubmitAttempts; $attempt++) {
    try {
        & (Join-Path $scriptDir "03_apply.ps1") @submitParams
        $submitSucceeded = $true
        break
    }
    catch {
        if ($attempt -ge $maxSubmitAttempts) {
            throw
        }
        Write-Host "MRS JobGateway is not ready yet. Retrying Spark submission in 30 seconds ($attempt/$maxSubmitAttempts)." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
    }
}
if (-not $submitSucceeded) {
    throw "MRS Spark job submission did not succeed after $maxSubmitAttempts attempts."
}
Add-TraceStep -Name "MRS smoke job submit finished" -Status "completed"

Write-Step "Read Terraform outputs"
Push-Location $tfDir
try {
    $summary = terraform output -json resource_summary | ConvertFrom-Json
    $jobIdRaw = terraform output -raw mrs_smoke_job_id 2>$null
    $jobNameRaw = terraform output -raw mrs_smoke_job_name 2>$null
}
finally {
    Pop-Location
}

if (-not $summary.mrs_cluster_id) {
    throw "MRS cluster id was not returned by Terraform output."
}
Set-TraceOutput -Name "terraform_resource_summary" -Value $summary
Set-TraceOutput -Name "mrs_smoke_job_id" -Value "$jobIdRaw"
Set-TraceOutput -Name "mrs_smoke_job_name" -Value "$jobNameRaw"

Write-Step "Wait for MRS job and fetch OBS gold output"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
& $Python (Join-Path $scriptDir "wait_mrs_and_fetch_gold.py") `
    --bucket $ObsBucketName `
    --run-id $RunId `
    --cluster-id $summary.mrs_cluster_id `
    --job-id "$jobIdRaw" `
    --job-name "$jobNameRaw" `
    --agent-run-id $agentRun.run_id `
    --agent-release-prefix $agentReleasePrefix `
    --output $evidencePath `
    --publish-dir $publicEvidenceDir
if ($LASTEXITCODE -ne 0) {
    throw "MRS job or Gold evidence validation failed with exit code $LASTEXITCODE."
}
Set-TraceOutput -Name "evidence_json" -Value $evidencePath
Set-TraceOutput -Name "frontend_evidence" -Value (Join-Path $publicEvidenceDir "latest_e2e_result.json")
Set-TraceOutput -Name "gold_output" -Value "obs://$ObsBucketName/gold/sat/$RunId/taxpayer_gold_csv/"
Set-TraceOutput -Name "iceberg_table" -Value "spark_catalog.tax_gold.taxpayer_regime_year"
Set-TraceOutput -Name "iceberg_warehouse" -Value "obs://$ObsBucketName/lakehouse/iceberg/sat/"
Add-TraceStep -Name "MRS gold fetch and evidence publish finished" -Status "completed"

Write-Step "E2E evidence"
Write-Host "Evidence JSON: $evidencePath"
Write-Host "Frontend evidence: $publicEvidenceDir\latest_e2e_result.json"
Write-Host "Agent release path: $agentReleasePrefix"
Write-Host "OBS audit JSON: obs://$ObsBucketName/audit/$RunId/e2e_result.json"
Write-Host "Gold data path: obs://$ObsBucketName/gold/sat/$RunId/taxpayer_gold_csv/"
Write-Host "Iceberg table: spark_catalog.tax_gold.taxpayer_regime_year"
Write-Host "Iceberg warehouse: obs://$ObsBucketName/lakehouse/iceberg/sat/"

$demoBaseUrl = "http://127.0.0.1:8788"
if ($EnableWebEcs -and $summary.web_public_ip) {
    $demoBaseUrl = "http://$($summary.web_public_ip)"
}

Write-Step "Export customer demo report"
& $Python (Join-Path $scriptDir "export_customer_demo_package.py") `
    --base-url $demoBaseUrl
Set-TraceOutput -Name "demo_base_url" -Value $demoBaseUrl
Set-TraceOutput -Name "customer_report" -Value (Join-Path $publicEvidenceDir "customer_demo_report.html")
Set-TraceOutput -Name "customer_report_url" -Value "$demoBaseUrl/cloud-evidence/customer_demo_report.html"
Add-TraceStep -Name "Customer demo report export finished" -Status "completed"
Write-Host "Customer report: $publicEvidenceDir\customer_demo_report.html"
Write-Host "Customer report URL: $demoBaseUrl/cloud-evidence/customer_demo_report.html"

if ($EnableWebEcs -and -not $SkipWebDeploy) {
    if (-not $SshKeyPath) {
        Write-Host ""
        Write-Host "Web ECS was created, but frontend deployment was skipped because -SshKeyPath was not provided." -ForegroundColor Yellow
        Write-Host "Run 06_deploy_frontend_to_ecs.ps1 with WebPublicIp=$($summary.web_public_ip) after the SSH key is available."
    }
    else {
        if (-not $summary.web_public_ip) {
            throw "Web ECS was enabled but Terraform did not return web_public_ip."
        }
        Write-Step "Deploy frontend and published evidence to ECS"
        & (Join-Path $scriptDir "06_deploy_frontend_to_ecs.ps1") `
            -WebPublicIp $summary.web_public_ip `
            -SshKeyPath $SshKeyPath `
            -SshUser $SshUser

        Write-Step "Diagnose customer demo ECS"
        & (Join-Path $scriptDir "13_diagnose_web_ecs.ps1") `
            -WebPublicIp $summary.web_public_ip `
            -SshKeyPath $SshKeyPath `
            -SshUser $SshUser
        Add-TraceStep -Name "Customer demo ECS diagnostics finished" -Status "completed"

        Write-Step "Verify customer demo website"
        & (Join-Path $scriptDir "07_verify_customer_demo.ps1") `
            -BaseUrl "http://$($summary.web_public_ip)"
        Add-TraceStep -Name "Customer demo website verification finished" -Status "completed"
    }
}

$script:RunTrace.status = "completed"
$script:RunTrace.completed_at = (Get-Date).ToUniversalTime().ToString("o")
Write-RunTrace
