param(
    [switch]$EnableWebEcs,

    [switch]$Apply,

    [switch]$AllowOpenIngressForDemo,

    [switch]$EmitReportOnly,

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

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

function Add-Check {
    param(
        [string]$Id,
        [string]$Status,
        [string]$Detail,
        [bool]$Blocking = $false
    )
    $script:Checks += [ordered]@{
        id = $Id
        status = $Status
        blocking = $Blocking
        detail = $Detail
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\apply_safety"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$script:Checks = @()
$adminCidr = Get-ConfiguredValue -Name "TF_VAR_admin_cidr" -DefaultValue "0.0.0.0/0"
$webCidr = Get-ConfiguredValue -Name "TF_VAR_web_cidr" -DefaultValue "0.0.0.0/0"
$nodeKeyPairName = Get-ConfiguredValue -Name "TF_VAR_node_key_pair_name"
$createsSshIngress = [bool]$EnableWebEcs -or [bool]$nodeKeyPairName
$openAdminIngress = $adminCidr -in @("0.0.0.0/0", "::/0")
$openWebIngress = $webCidr -in @("0.0.0.0/0", "::/0")
$status = "passed"

if ($createsSshIngress) {
    if ($openAdminIngress -and -not $AllowOpenIngressForDemo) {
        Add-Check -Id "INGRESS-SSH" -Status "failed" -Blocking $true -Detail "SSH administration is open through TF_VAR_admin_cidr=$adminCidr. Restrict it to an operator/VPN CIDR."
        $status = "failed"
    }
    elseif ($openAdminIngress -and $AllowOpenIngressForDemo) {
        Add-Check -Id "INGRESS-SSH" -Status "warning" -Blocking $false -Detail "Open SSH was explicitly allowed for a disposable demo. Restrict it before deployment whenever possible."
        if ($status -ne "failed") { $status = "warning" }
    }
    else {
        Add-Check -Id "INGRESS-SSH" -Status "passed" -Blocking $false -Detail "SSH administration is restricted to $adminCidr."
    }
}
else {
    Add-Check -Id "INGRESS-SSH" -Status "passed" -Blocking $false -Detail "No SSH ingress is requested."
}

if ($EnableWebEcs) {
    if ($openWebIngress -and -not $AllowOpenIngressForDemo) {
        Add-Check -Id "INGRESS-WEB" -Status "failed" -Blocking $true -Detail "Public web ingress requires explicit -AllowOpenIngressForDemo approval."
        $status = "failed"
    }
    elseif ($openWebIngress) {
        Add-Check -Id "INGRESS-WEB" -Status "warning" -Blocking $false -Detail "HTTP/HTTPS is intentionally public for the disposable demo; SSH remains governed separately."
        if ($status -ne "failed") { $status = "warning" }
    }
    else {
        Add-Check -Id "INGRESS-WEB" -Status "passed" -Blocking $false -Detail "Web ingress is restricted to $webCidr."
    }
}

if ($Apply -and $AllowOpenIngressForDemo) {
    Add-Check -Id "APPLY-OPEN-INGRESS" -Status "warning" -Blocking $false -Detail "Real apply may create open ingress because -AllowOpenIngressForDemo was used."
    if ($status -ne "failed") { $status = "warning" }
}

$report = [ordered]@{
    status = $status
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    apply = [bool]$Apply
    enable_web_ecs = [bool]$EnableWebEcs
    node_key_pair_configured = [bool]$nodeKeyPairName
    admin_cidr = $adminCidr
    web_cidr = $webCidr
    allow_open_ingress_for_demo = [bool]$AllowOpenIngressForDemo
    checks = $script:Checks
    next_action = if ($status -eq "failed") {
        "Set TF_VAR_admin_cidr to a trusted CIDR, then rerun preflight/apply. For throwaway demos only, pass -AllowOpenIngressForDemo."
    }
    elseif ($status -eq "warning") {
        "Continue only for a disposable demo; tighten TF_VAR_admin_cidr before customer or commercial use."
    }
    else {
        "Continue with preflight/apply."
    }
}

$jsonPath = Join-Path $OutputDir "apply_safety_latest.json"
$mdPath = Join-Path $OutputDir "apply_safety.md"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = @(
    "# SAT Agentic Apply Safety",
    "",
    "- status: $($report.status)",
    "- apply: $($report.apply)",
    "- enable_web_ecs: $($report.enable_web_ecs)",
    "- admin_cidr: $($report.admin_cidr)",
    "- web_cidr: $($report.web_cidr)",
    "- allow_open_ingress_for_demo: $($report.allow_open_ingress_for_demo)",
    "- values_printed: false",
    "",
    "## Checks",
    "",
    "| status | blocking | id | detail |",
    "| --- | --- | --- | --- |"
)
foreach ($check in $script:Checks) {
    $detail = ([string]$check.detail).Replace("|", "\|")
    $lines += "| $($check.status) | $($check.blocking) | $($check.id) | $detail |"
}
$lines += @(
    "",
    "## Next Action",
    "",
    $report.next_action
)
$lines | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Apply safety status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "failed") { "Red" } elseif ($report.status -eq "warning") { "Yellow" } else { "Green" }))
foreach ($check in $script:Checks) {
    $color = if ($check.status -eq "failed") { "Red" } elseif ($check.status -eq "warning") { "Yellow" } else { "Green" }
    Write-Host "  [$($check.status)] $($check.detail)" -ForegroundColor $color
}
Write-Host "Safety JSON: $jsonPath"
Write-Host "Safety report: $mdPath"

if (-not $EmitReportOnly -and $status -eq "failed") {
    throw "Apply safety failed. $($report.next_action)"
}
