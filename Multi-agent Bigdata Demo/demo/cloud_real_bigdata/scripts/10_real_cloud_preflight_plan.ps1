param(
    [string]$ObsBucketName = "",

    [string]$BucketPrefix = "sat-agentic",

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$PromptFile = "",

    [string]$Scenario = "sat_padron_base_anual",

    [switch]$UseMaaS,

    [switch]$EnableWebEcs,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$AllowOpenIngressForDemo,

    [switch]$AllowLongLivedDemo
)

$ErrorActionPreference = "Stop"

function New-BucketName {
    param([string]$Prefix)
    $safePrefix = ($Prefix.ToLowerInvariant() -replace "[^a-z0-9-]", "-").Trim("-")
    if (-not $safePrefix) { $safePrefix = "sat-agentic" }
    if ($safePrefix.Length -gt 40) {
        $safePrefix = $safePrefix.Substring(0, 40).Trim("-")
    }
    $suffix = (Get-Date -Format "yyyyMMddHHmmss") + "-" + (Get-Random -Minimum 1000 -Maximum 9999)
    return "$safePrefix-$suffix"
}

function Save-PreflightReport {
    param(
        [string]$Status,
        [string]$Message,
        [string]$ReportPath,
        [string]$LogPath,
        [string]$Bucket,
        [string]$Prompt,
        [array]$Command
    )
    $report = [ordered]@{
        status = $Status
        message = $Message
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        creates_resources = $false
        submits_mrs_job = $false
        uploads_obs_objects = $false
        obs_bucket_name = $Bucket
        prompt_file = $Prompt
        log_path = $LogPath
        command = $Command
        next_action = if ($Status -eq "passed") {
            "Run 05_run_real_e2e.ps1 with the same arguments plus -Apply."
        }
        else {
            "Fix the reported issue before running any paid cloud apply."
        }
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $ObsBucketName) {
    $ObsBucketName = if ($env:TF_VAR_obs_bucket_name) { $env:TF_VAR_obs_bucket_name } else { New-BucketName -Prefix $BucketPrefix }
}
if (-not $NodeKeyPairName -and $env:TF_VAR_node_key_pair_name) {
    $NodeKeyPairName = $env:TF_VAR_node_key_pair_name
}
if (-not $PromptFile) {
    $PromptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"
}

$preflightDir = Join-Path $root ".cloud_real_bigdata_work\real_cloud_preflight"
New-Item -ItemType Directory -Force -Path $preflightDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $preflightDir "preflight_$stamp.log"
$reportPath = Join-Path $preflightDir "real_cloud_preflight_latest.json"

$command = @(
    ".\cloud_real_bigdata\scripts\05_run_real_e2e.ps1",
    "-ObsBucketName", $ObsBucketName,
    "-NodeKeyPairName", $NodeKeyPairName,
    "-PromptFile", $PromptFile,
    "-Scenario", $Scenario
)
if ($UseMaaS) { $command += "-UseMaaS" }
if ($EnableWebEcs) { $command += "-EnableWebEcs" }
if ($EnableDws) { $command += "-EnableDws" }
if ($EnableDataArts) { $command += "-EnableDataArts" }
if ($AllowOpenIngressForDemo) { $command += "-AllowOpenIngressForDemo" }
if ($AllowLongLivedDemo) { $command += "-AllowLongLivedDemo" }

Write-Host "SAT Agentic real-cloud preflight plan" -ForegroundColor Cyan
Write-Host "  bucket: $ObsBucketName"
Write-Host "  prompt: $PromptFile"
Write-Host "  web ecs: $($EnableWebEcs.IsPresent)"
Write-Host "  dws: $($EnableDws.IsPresent)"
Write-Host "  dataarts: $($EnableDataArts.IsPresent)"
Write-Host "  open ingress override: $($AllowOpenIngressForDemo.IsPresent)"
Write-Host "  long-lived demo override: $($AllowLongLivedDemo.IsPresent)"
Write-Host "  creates resources: false"
Write-Host ""

try {
    Push-Location $root
    try {
        $preflightParams = @{
            ObsBucketName = $ObsBucketName
            NodeKeyPairName = $NodeKeyPairName
            PromptFile = $PromptFile
            Scenario = $Scenario
        }
        if ($UseMaaS) { $preflightParams.UseMaaS = $true }
        if ($EnableWebEcs) { $preflightParams.EnableWebEcs = $true }
        if ($EnableDws) { $preflightParams.EnableDws = $true }
        if ($EnableDataArts) { $preflightParams.EnableDataArts = $true }
        if ($AllowOpenIngressForDemo) { $preflightParams.AllowOpenIngressForDemo = $true }
        if ($AllowLongLivedDemo) { $preflightParams.AllowLongLivedDemo = $true }
        $output = & (Join-Path $scriptDir "05_run_real_e2e.ps1") @preflightParams 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    ($output | Out-String) | Set-Content -LiteralPath $logPath -Encoding UTF8
    if ($exitCode -ne 0) {
        throw "Preflight command failed with exit code $exitCode. See $logPath"
    }
    Save-PreflightReport -Status "passed" -Message "Terraform plan completed without applying resources." -ReportPath $reportPath -LogPath $logPath -Bucket $ObsBucketName -Prompt $PromptFile -Command $command
    Write-Host "Preflight passed. No resources were created." -ForegroundColor Green
}
catch {
    $message = $_.Exception.Message
    if (-not (Test-Path -LiteralPath $logPath)) {
        $message | Set-Content -LiteralPath $logPath -Encoding UTF8
    }
    Save-PreflightReport -Status "failed" -Message $message -ReportPath $reportPath -LogPath $logPath -Bucket $ObsBucketName -Prompt $PromptFile -Command $command
    Write-Host "Preflight failed. No resources were created." -ForegroundColor Red
    Write-Host $message -ForegroundColor Red
    Write-Host "Report: $reportPath"
    exit 1
}

Write-Host "Report: $reportPath"
Write-Host "Log: $logPath"
