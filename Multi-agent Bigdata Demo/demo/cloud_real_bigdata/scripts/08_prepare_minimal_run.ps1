param(
    [string]$BucketPrefix = "sat-agentic",

    [string]$PromptFile = "",

    [switch]$UseMaaS,

    [switch]$EnableWebEcs,

    [string]$SshKeyPath = "",

    [switch]$EnableDws,

    [switch]$AllowOpenIngressForDemo,

    [switch]$AllowLongLivedDemo
)

$ErrorActionPreference = "Stop"

function Test-Configured {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "User") }
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine") }
    return [bool]$value
}

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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $PromptFile) {
    $PromptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"
}

$bucketName = if ($env:TF_VAR_obs_bucket_name) { $env:TF_VAR_obs_bucket_name } else { New-BucketName -Prefix $BucketPrefix }
$missing = @()
foreach ($name in @(
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "TF_VAR_mrs_manager_admin_password",
    "TF_VAR_node_key_pair_name"
)) {
    if (-not (Test-Configured $name)) {
        $missing += $name
    }
}
if ($EnableDws -and -not (Test-Configured "TF_VAR_dws_admin_password")) {
    $missing += "TF_VAR_dws_admin_password"
}

Write-Host "SAT Agentic minimal real-cloud run draft" -ForegroundColor Cyan
Write-Host ""
Write-Host "Bucket name : $bucketName"
Write-Host "Prompt file : $PromptFile"
Write-Host "Web ECS     : $($EnableWebEcs.IsPresent)"
Write-Host "DWS         : $($EnableDws.IsPresent)"
Write-Host "MaaS        : $($UseMaaS.IsPresent)"
Write-Host "Open ingress override: $($AllowOpenIngressForDemo.IsPresent)"
Write-Host "Long-lived demo override: $($AllowLongLivedDemo.IsPresent)"
Write-Host ""

if ($missing.Count -gt 0) {
    Write-Host "Missing required local environment variables:" -ForegroundColor Yellow
    foreach ($name in $missing) {
        Write-Host "  - $name"
    }
    Write-Host ""
    Write-Host "Put values in your shell or in ignored .env.local, then run 02_validate_env.ps1." -ForegroundColor Yellow
}
else {
    Write-Host "Environment variables required for this run are present." -ForegroundColor Green
}

Write-Host ""
Write-Host "Apply safety preview:" -ForegroundColor Cyan
& (Join-Path $scriptDir "14_validate_apply_safety.ps1") `
    -EnableWebEcs:$EnableWebEcs `
    -Apply `
    -AllowOpenIngressForDemo:$AllowOpenIngressForDemo `
    -EmitReportOnly

Write-Host ""
Write-Host "Lifecycle preview:" -ForegroundColor Cyan
& (Join-Path $scriptDir "16_validate_lifecycle_guard.ps1") `
    -Apply `
    -AllowLongLivedDemo:$AllowLongLivedDemo `
    -EmitReportOnly

$nodeKeyForCommand = if ($env:TF_VAR_node_key_pair_name) { $env:TF_VAR_node_key_pair_name } else { "<existing-key-pair>" }
$command = @(
    ".\cloud_real_bigdata\scripts\05_run_real_e2e.ps1",
    "  -ObsBucketName `"$bucketName`"",
    "  -NodeKeyPairName `"$nodeKeyForCommand`"",
    "  -PromptFile `"$PromptFile`""
)
if ($UseMaaS) { $command += "  -UseMaaS" }
if ($EnableDws) { $command += "  -EnableDws" }
if ($EnableWebEcs) {
    $command += "  -EnableWebEcs"
    if ($SshKeyPath) {
        $command += "  -SshKeyPath `"$SshKeyPath`""
    }
    else {
        $command += "  -SshKeyPath `"<path-to-private-key.pem>`""
    }
}
if ($AllowOpenIngressForDemo) { $command += "  -AllowOpenIngressForDemo" }
if ($AllowLongLivedDemo) { $command += "  -AllowLongLivedDemo" }
$command += "  -Apply"

Write-Host ""
Write-Host "Command:" -ForegroundColor Cyan
for ($index = 0; $index -lt $command.Count; $index += 1) {
    if ($index -lt ($command.Count - 1)) {
        Write-Host "$($command[$index]) ``"
    }
    else {
        Write-Host $command[$index]
    }
}
Write-Host ""
Write-Host "Cleanup command after the demo:" -ForegroundColor Cyan
Write-Host ".\cloud_real_bigdata\scripts\04_destroy.ps1 -ConfirmDestroy"
