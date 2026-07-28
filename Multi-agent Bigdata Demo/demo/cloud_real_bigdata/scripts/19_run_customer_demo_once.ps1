param(
    [string]$ObsBucketName = "",

    [string]$NodeKeyPairName = $env:TF_VAR_node_key_pair_name,

    [string]$PromptFile = "",

    [string]$Scenario = "sat_padron_base_anual",

    [switch]$ConfigureCredentials,

    [switch]$PersistUserEnv,

    [switch]$WriteLocalEnv,

    [switch]$SetGuardDefaults,

    [switch]$DetectAdminCidr,

    [switch]$UseMaaS,

    [switch]$EnableWebEcs,

    [string]$SshKeyPath = "",

    [string]$SshUser = "root",

    [switch]$SkipWebDeploy,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$SkipReadonlyCloudProbe,

    [switch]$SkipTerraformPreflight,

    [switch]$DestroyOnFailure,

    [switch]$Apply,

    [switch]$ConfirmPaidResources,

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

if ($Apply -and -not $ConfirmPaidResources) {
    throw "Real cloud apply requires both -Apply and -ConfirmPaidResources."
}

if ($Apply -and $EnableWebEcs -and -not $SkipWebDeploy -and -not $SshKeyPath) {
    throw "For a customer-demo ECS deployment, pass -SshKeyPath or use -SkipWebDeploy."
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return [ordered]@{
            status = "invalid_json"
            path = $Path
            error = $_.Exception.Message
        }
    }
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

function Write-DemoReport {
    param(
        [object]$Report,
        [string]$JsonPath,
        [string]$MarkdownPath
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $JsonPath) | Out-Null
    $Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $JsonPath -Encoding UTF8
    $lines = @(
        "# SAT Agentic Customer Demo Once",
        "",
        "- status: $($Report.status)",
        "- mode: $($Report.mode)",
        "- values_printed: false",
        "- creates_resources: $($Report.creates_resources)",
        "- uploads_obs_objects: $($Report.uploads_obs_objects)",
        "- submits_mrs_job: $($Report.submits_mrs_job)",
        "- obs_bucket_name: $($Report.obs_bucket_name)",
        "- base_url: $($Report.base_url)",
        "",
        "## Reports",
        "",
        "- readiness_report: $($Report.readiness_report)",
        "- e2e_trace: $($Report.e2e_trace)",
        "- final_audit: $($Report.final_audit)",
        "",
        "## Next Action",
        "",
        '```powershell',
        $Report.next_action,
        '```'
    )
    $lines | Set-Content -LiteralPath $MarkdownPath -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\customer_demo_once"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not $ObsBucketName) {
    $ObsBucketName = Get-ConfiguredValue -Name "TF_VAR_obs_bucket_name"
}
if (-not $ObsBucketName) {
    $ObsBucketName = New-BucketName -Prefix "sat-agentic"
}
if (-not $NodeKeyPairName) {
    $NodeKeyPairName = Get-ConfiguredValue -Name "TF_VAR_node_key_pair_name"
}
if (-not $PromptFile) {
    $PromptFile = Join-Path $root "cloud_real_bigdata\examples\sat_prompt.txt"
}

$readinessPath = Join-Path $root ".cloud_real_bigdata_work\pre_apply_readiness\pre_apply_readiness_latest.json"
$e2eTracePath = Join-Path $root ".cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json"
$auditPath = Join-Path $root ".cloud_real_bigdata_work\acceptance_audit\final_acceptance_audit.json"
$jsonPath = Join-Path $OutputDir "customer_demo_once_latest.json"
$mdPath = Join-Path $OutputDir "customer_demo_once.md"

Write-Host "SAT Agentic customer demo once" -ForegroundColor Cyan
Write-Host "  mode: $($(if ($Apply) { 'apply' } else { 'preflight-only' }))"
Write-Host "  bucket: $ObsBucketName"
Write-Host "  web ecs: $($EnableWebEcs.IsPresent)"
Write-Host ""

$bootstrapParams = @{
    ObsBucketName = $ObsBucketName
    NodeKeyPairName = $NodeKeyPairName
    PromptFile = $PromptFile
    Scenario = $Scenario
}
if ($ConfigureCredentials) { $bootstrapParams["ConfigureCredentials"] = $true }
if ($PersistUserEnv) { $bootstrapParams["PersistUserEnv"] = $true }
if ($WriteLocalEnv) { $bootstrapParams["WriteLocalEnv"] = $true }
if ($SetGuardDefaults) { $bootstrapParams["SetGuardDefaults"] = $true }
if ($DetectAdminCidr) { $bootstrapParams["DetectAdminCidr"] = $true }
if ($UseMaaS) { $bootstrapParams["UseMaaS"] = $true }
if ($EnableWebEcs) { $bootstrapParams["EnableWebEcs"] = $true }
if ($EnableDws) { $bootstrapParams["EnableDws"] = $true }
if ($EnableDataArts) { $bootstrapParams["EnableDataArts"] = $true }
if ($SkipReadonlyCloudProbe) { $bootstrapParams["SkipReadonlyCloudProbe"] = $true }
if (-not $SkipTerraformPreflight) { $bootstrapParams["RunTerraformPreflight"] = $true }

& (Join-Path $scriptDir "18_bootstrap_operator_session.ps1") @bootstrapParams

$readiness = Read-JsonFile $readinessPath
$readinessStatus = if ($readiness) { [string]$readiness.status } else { "not_run" }
$baseUrl = "http://127.0.0.1:8788"
$report = [ordered]@{
    status = $readinessStatus
    mode = if ($Apply) { "apply" } else { "preflight_only" }
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = [bool]$Apply
    uploads_obs_objects = [bool]$Apply
    submits_mrs_job = [bool]$Apply
    obs_bucket_name = $ObsBucketName
    base_url = $baseUrl
    readiness_report = $readinessPath
    e2e_trace = $e2eTracePath
    final_audit = $auditPath
    next_action = ""
}

if ($Apply -and $readinessStatus -ne "ready_for_apply") {
    $report.status = "blocked_before_apply"
    $report.creates_resources = $false
    $report.uploads_obs_objects = $false
    $report.submits_mrs_job = $false
    $report.next_action = ".\cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1 -ConfigureCredentials -PersistUserEnv -SetGuardDefaults -DetectAdminCidr -EnableWebEcs -RunTerraformPreflight"
    Write-DemoReport -Report $report -JsonPath $jsonPath -MarkdownPath $mdPath
    throw "Readiness is $readinessStatus, not ready_for_apply. Real apply was not started."
}

if (-not $Apply) {
    $report.next_action = ".\cloud_real_bigdata\scripts\19_run_customer_demo_once.ps1 -ObsBucketName `"$ObsBucketName`" -NodeKeyPairName `"$NodeKeyPairName`" -PromptFile `"$PromptFile`" -Scenario `"$Scenario`"$(if ($UseMaaS) { ' -UseMaaS' })$(if ($EnableWebEcs) { ' -EnableWebEcs -SshKeyPath `"<path-to-private-key.pem>`"' })$(if ($EnableDws) { ' -EnableDws' })$(if ($EnableDataArts) { ' -EnableDataArts' }) -Apply -ConfirmPaidResources"
    Write-DemoReport -Report $report -JsonPath $jsonPath -MarkdownPath $mdPath
    Write-Host "Preflight-only mode finished. No cloud resources were created." -ForegroundColor Yellow
    Write-Host "Customer demo once JSON: $jsonPath"
    Write-Host "Customer demo once report: $mdPath"
    exit 0
}

$e2eParams = @{
    ObsBucketName = $ObsBucketName
    NodeKeyPairName = $NodeKeyPairName
    PromptFile = $PromptFile
    Scenario = $Scenario
    Apply = $true
}
if ($UseMaaS) { $e2eParams["UseMaaS"] = $true }
if ($EnableWebEcs) { $e2eParams["EnableWebEcs"] = $true }
if ($EnableDws) { $e2eParams["EnableDws"] = $true }
if ($EnableDataArts) { $e2eParams["EnableDataArts"] = $true }
if ($SshKeyPath) { $e2eParams["SshKeyPath"] = $SshKeyPath }
if ($SshUser) { $e2eParams["SshUser"] = $SshUser }
if ($SkipWebDeploy) { $e2eParams["SkipWebDeploy"] = $true }
if ($DestroyOnFailure) { $e2eParams["DestroyOnFailure"] = $true }

& (Join-Path $scriptDir "05_run_real_e2e.ps1") @e2eParams

$trace = Read-JsonFile $e2eTracePath
if ($trace -and $trace.outputs -and $trace.outputs.demo_base_url) {
    $baseUrl = [string]$trace.outputs.demo_base_url
}

& (Join-Path $scriptDir "09_final_acceptance_audit.ps1") -BaseUrl $baseUrl -RequireCloudSuccess

$audit = Read-JsonFile $auditPath
$auditStatus = if ($audit) { [string]$audit.status } else { "not_run" }
if ($auditStatus -eq "ready_for_customer_demo") {
    & (Join-Path $scriptDir "20_export_customer_handoff.ps1") -BaseUrl $baseUrl -RequireCloudSuccess -PublishToEvidence
    & (Join-Path $scriptDir "22_validate_customer_commercial_readiness.ps1") -BaseUrl $baseUrl -PublishToEvidence
}
$report.status = $auditStatus
$report.base_url = $baseUrl
$report.next_action = if ($auditStatus -eq "ready_for_customer_demo") {
    "Open $baseUrl and use cloud-evidence/customer_demo_report.html plus cloud-evidence/customer_handoff.html for the customer demonstration."
}
else {
    "Inspect .cloud_real_bigdata_work\e2e_traces\latest_e2e_trace.json and final_acceptance_audit.md."
}
Write-DemoReport -Report $report -JsonPath $jsonPath -MarkdownPath $mdPath

Write-Host "Customer demo once JSON: $jsonPath"
Write-Host "Customer demo once report: $mdPath"
Write-Host "Final customer demo status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "ready_for_customer_demo") { "Green" } else { "Yellow" }))
