param(
    [switch]$ConfigureCredentials,

    [switch]$PersistUserEnv,

    [switch]$WriteLocalEnv,

    [switch]$SetGuardDefaults,

    [switch]$DetectAdminCidr,

    [string]$AdminCidr = "",

    [string]$DemoOwner = "",

    [int]$DemoTtlHours = 24,

    [string]$DemoPurpose = "sat-agentic-customer-demo",

    [string]$Region = "la-south-2",

    [string]$ObsBucketName = "",

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$PromptFile = "",

    [string]$Scenario = "sat_padron_base_anual",

    [switch]$UseMaaS,

    [switch]$EnableWebEcs,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$RunTerraformPreflight,

    [switch]$SkipReadonlyCloudProbe,

    [string]$EnvFile = "",

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

if ($PersistUserEnv -and $WriteLocalEnv) {
    throw "Choose only one target: -PersistUserEnv or -WriteLocalEnv."
}

if ($ConfigureCredentials -and -not $PersistUserEnv -and -not $WriteLocalEnv) {
    $PersistUserEnv = $true
}

if ($SetGuardDefaults -and -not $PersistUserEnv -and -not $WriteLocalEnv) {
    throw "Use -SetGuardDefaults with -PersistUserEnv or -WriteLocalEnv so guard values persist beyond this PowerShell process."
}

function Get-ConfiguredValue {
    param(
        [string]$Name,
        [string]$DefaultValue = ""
    )
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "User") }
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine") }
    if (-not $value) { $value = $DefaultValue }
    return $value
}

function Set-UserEnvValue {
    param(
        [string]$Name,
        [string]$Value
    )
    if ($null -eq $Value -or $Value -eq "") {
        return
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Read-EnvFilePairs {
    param([string]$Path)
    $pairs = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $pairs
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $index = $trimmed.IndexOf("=")
        if ($index -le 0) {
            continue
        }
        $name = $trimmed.Substring(0, $index).Trim()
        $value = $trimmed.Substring($index + 1)
        if ($name) {
            $pairs[$name] = $value
        }
    }
    return $pairs
}

function Write-EnvFilePairs {
    param(
        [string]$Path,
        [System.Collections.IDictionary]$Pairs
    )
    $lines = @(
        "# Local Huawei Cloud environment for SAT Agentic POC.",
        "# Generated or updated by cloud_real_bigdata/scripts/18_bootstrap_operator_session.ps1.",
        "# This file is ignored by git. Do not paste its values into chat or commit it.",
        ""
    )
    foreach ($name in $Pairs.Keys | Sort-Object) {
        $value = [string]$Pairs[$name]
        if ($value -match "[`r`n]") {
            throw "$name contains a newline and cannot be written to .env.local."
        }
        $lines += "$name=$value"
    }
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $lines | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Set-BootstrapEnvValue {
    param(
        [string]$Name,
        [string]$Value,
        [System.Collections.IDictionary]$LocalPairs
    )
    if ($null -eq $Value -or $Value -eq "") {
        return
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    if ($PersistUserEnv) {
        Set-UserEnvValue -Name $Name -Value $Value
    }
    if ($WriteLocalEnv) {
        $LocalPairs[$Name] = $Value
    }
}

function Resolve-PublicIpv4 {
    $services = @(
        "https://api.ipify.org",
        "https://ifconfig.me/ip"
    )
    foreach ($service in $services) {
        try {
            $value = (Invoke-RestMethod -Uri $service -UseBasicParsing -TimeoutSec 8).ToString().Trim()
            if ($value -match "^\d{1,3}(\.\d{1,3}){3}$") {
                return $value
            }
        }
        catch {
            continue
        }
    }
    return ""
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
if (-not $EnvFile) {
    $EnvFile = Join-Path $root ".env.local"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\operator_bootstrap"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet -EnvFile $EnvFile

$localPairs = Read-EnvFilePairs -Path $EnvFile
$chosenRegion = Get-ConfiguredValue -Name "HUAWEICLOUD_REGION" -DefaultValue $Region
$chosenAdminCidr = $AdminCidr
$detectedPublicIp = ""
if (-not $chosenAdminCidr -and $DetectAdminCidr) {
    $detectedPublicIp = Resolve-PublicIpv4
    if ($detectedPublicIp) {
        $chosenAdminCidr = "$detectedPublicIp/32"
    }
}
if (-not $chosenAdminCidr) {
    $chosenAdminCidr = Get-ConfiguredValue -Name "TF_VAR_admin_cidr"
}

$chosenOwner = $DemoOwner
if (-not $chosenOwner) {
    $chosenOwner = Get-ConfiguredValue -Name "TF_VAR_demo_owner"
}
if (-not $chosenOwner -and $SetGuardDefaults) {
    $userName = Get-ConfiguredValue -Name "USERNAME" -DefaultValue "local-operator"
    $chosenOwner = "$userName-local"
}

$chosenPurpose = if ($DemoPurpose) { $DemoPurpose } else { Get-ConfiguredValue -Name "TF_VAR_demo_purpose" -DefaultValue "sat-agentic-customer-demo" }
$existingExpiresAt = Get-ConfiguredValue -Name "TF_VAR_demo_expires_at"
$chosenExpiresAt = $existingExpiresAt
if ($SetGuardDefaults -or $ConfigureCredentials) {
    $chosenExpiresAt = [DateTimeOffset]::UtcNow.AddHours($DemoTtlHours).ToString("yyyy-MM-ddTHH:mm:ssZ")
}

if ($SetGuardDefaults) {
    Set-BootstrapEnvValue -Name "HUAWEICLOUD_REGION" -Value $chosenRegion -LocalPairs $localPairs
    Set-BootstrapEnvValue -Name "TF_VAR_region" -Value $chosenRegion -LocalPairs $localPairs
    Set-BootstrapEnvValue -Name "TF_VAR_admin_cidr" -Value $chosenAdminCidr -LocalPairs $localPairs
    Set-BootstrapEnvValue -Name "TF_VAR_demo_owner" -Value $chosenOwner -LocalPairs $localPairs
    Set-BootstrapEnvValue -Name "TF_VAR_demo_purpose" -Value $chosenPurpose -LocalPairs $localPairs
    Set-BootstrapEnvValue -Name "TF_VAR_demo_expires_at" -Value $chosenExpiresAt -LocalPairs $localPairs
    if ($NodeKeyPairName) {
        Set-BootstrapEnvValue -Name "TF_VAR_node_key_pair_name" -Value $NodeKeyPairName -LocalPairs $localPairs
    }
    if ($WriteLocalEnv) {
        Write-EnvFilePairs -Path $EnvFile -Pairs $localPairs
        & (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet -EnvFile $EnvFile
    }
}

if ($ConfigureCredentials) {
    $credentialParams = @{}
    if ($WriteLocalEnv) {
        $credentialParams["WriteLocalEnv"] = $true
        $credentialParams["EnvFile"] = $EnvFile
    }
    else {
        $credentialParams["PersistUserEnv"] = $true
    }
    $credentialParams["Region"] = (Get-ConfiguredValue -Name "HUAWEICLOUD_REGION" -DefaultValue "la-south-2")
    if (Get-ConfiguredValue -Name "HUAWEICLOUD_PROJECT_ID") {
        $credentialParams["ProjectId"] = (Get-ConfiguredValue -Name "HUAWEICLOUD_PROJECT_ID")
    }
    if ($NodeKeyPairName) {
        $credentialParams["NodeKeyPairName"] = $NodeKeyPairName
    }
    if ($chosenAdminCidr) {
        $credentialParams["AdminCidr"] = $chosenAdminCidr
    }
    if ($chosenOwner) {
        $credentialParams["DemoOwner"] = $chosenOwner
    }
    if ($chosenPurpose) {
        $credentialParams["DemoPurpose"] = $chosenPurpose
    }
    if ($chosenExpiresAt) {
        $credentialParams["DemoExpiresAt"] = $chosenExpiresAt
    }
    if ($EnableDws) {
        $credentialParams["IncludeDws"] = $true
    }

    & (Join-Path $scriptDir "12_configure_cloud_credentials.ps1") @credentialParams
    & (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet -EnvFile $EnvFile
}
else {
    & (Join-Path $scriptDir "12_configure_cloud_credentials.ps1")
}

if (-not $ObsBucketName) {
    $ObsBucketName = Get-ConfiguredValue -Name "TF_VAR_obs_bucket_name"
}
if (-not $ObsBucketName) {
    $ObsBucketName = New-BucketName -Prefix "sat-agentic"
}
if ($SetGuardDefaults) {
    Set-BootstrapEnvValue -Name "TF_VAR_obs_bucket_name" -Value $ObsBucketName -LocalPairs $localPairs
    if ($WriteLocalEnv) {
        Write-EnvFilePairs -Path $EnvFile -Pairs $localPairs
        & (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet -EnvFile $EnvFile
    }
}
if (-not $NodeKeyPairName) {
    $NodeKeyPairName = Get-ConfiguredValue -Name "TF_VAR_node_key_pair_name"
}
if (-not $PromptFile) {
    $PromptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"
}

$readinessParams = @{
    ObsBucketName = $ObsBucketName
    NodeKeyPairName = $NodeKeyPairName
    PromptFile = $PromptFile
    Scenario = $Scenario
}
if ($UseMaaS) { $readinessParams["UseMaaS"] = $true }
if ($EnableWebEcs) { $readinessParams["EnableWebEcs"] = $true }
if ($EnableDws) { $readinessParams["EnableDws"] = $true }
if ($EnableDataArts) { $readinessParams["EnableDataArts"] = $true }
if (-not $SkipReadonlyCloudProbe) { $readinessParams["RunReadonlyCloudProbe"] = $true }
if ($RunTerraformPreflight) { $readinessParams["RunTerraformPreflight"] = $true }

& (Join-Path $scriptDir "15_pre_apply_readiness.ps1") @readinessParams

$readinessPath = Join-Path $root ".cloud_real_bigdata_work\pre_apply_readiness\pre_apply_readiness_latest.json"
$credentialPath = Join-Path $root ".cloud_real_bigdata_work\credential_status\credential_status_latest.json"
$minimalPlanPath = Join-Path $root ".cloud_real_bigdata_work\minimal_cost_quota_plan\minimal_cost_quota_plan_latest.json"
$readinessStatus = "unknown"
if (Test-Path -LiteralPath $readinessPath) {
    try {
        $readinessStatus = (Get-Content -LiteralPath $readinessPath -Raw -Encoding UTF8 | ConvertFrom-Json).status
    }
    catch {
        $readinessStatus = "invalid_json"
    }
}

$report = [ordered]@{
    status = $readinessStatus
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = $false
    uploads_obs_objects = $false
    submits_mrs_job = $false
    configured_credentials = [bool]$ConfigureCredentials
    set_guard_defaults = [bool]$SetGuardDefaults
    persist_user_env = [bool]$PersistUserEnv
    write_local_env = [bool]$WriteLocalEnv
    detect_admin_cidr = [bool]$DetectAdminCidr
    detected_public_ip = if ($detectedPublicIp) { "detected" } else { "" }
    admin_cidr_configured = [bool]$chosenAdminCidr
    demo_owner_configured = [bool]$chosenOwner
    demo_expires_at_configured = [bool]$chosenExpiresAt
    region = $chosenRegion
    obs_bucket_name = $ObsBucketName
    minimal_cost_quota_plan = $minimalPlanPath
    readiness_report = $readinessPath
    credential_report = $credentialPath
    next_action = if ($readinessStatus -eq "ready_for_apply") {
        ".\cloud_real_bigdata\scripts\05_run_real_e2e.ps1 -ObsBucketName `"$ObsBucketName`" -NodeKeyPairName `"$NodeKeyPairName`" -PromptFile `"$PromptFile`" -Scenario `"$Scenario`"$(if ($UseMaaS) { ' -UseMaaS' })$(if ($EnableWebEcs) { ' -EnableWebEcs -SshKeyPath `"<path-to-private-key.pem>`"' })$(if ($EnableDws) { ' -EnableDws' })$(if ($EnableDataArts) { ' -EnableDataArts' }) -Apply"
    }
    else {
        ".\cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1 -ConfigureCredentials -PersistUserEnv -SetGuardDefaults -DetectAdminCidr -EnableWebEcs -RunTerraformPreflight"
    }
}

$jsonPath = Join-Path $OutputDir "operator_bootstrap_latest.json"
$mdPath = Join-Path $OutputDir "operator_bootstrap.md"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# SAT Agentic Operator Bootstrap",
    "",
    "- status: $($report.status)",
    "- values_printed: false",
    "- creates_resources: false",
    "- uploads_obs_objects: false",
    "- submits_mrs_job: false",
    "- configured_credentials: $($report.configured_credentials)",
    "- set_guard_defaults: $($report.set_guard_defaults)",
    "",
    "## Reports",
    "",
    "- credential_report: $credentialPath",
    "- minimal_cost_quota_plan: $minimalPlanPath",
    "- readiness_report: $readinessPath",
    "",
    "## Next Action",
    "",
    '```powershell',
    $report.next_action,
    '```'
)
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Operator bootstrap status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "ready_for_apply") { "Green" } elseif ($report.status -eq "pending_readiness") { "Yellow" } else { "Cyan" }))
Write-Host "Bootstrap JSON: $jsonPath"
Write-Host "Bootstrap report: $mdPath"
Write-Host "No cloud resources were created, no OBS objects were uploaded, and no MRS jobs were submitted."
