param(
    [switch]$Apply,

    [int]$MaxTtlHours = 168,

    [switch]$AllowLongLivedDemo,

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
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\lifecycle_guard"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$script:Checks = @()
$owner = Get-ConfiguredValue -Name "TF_VAR_demo_owner"
$purpose = Get-ConfiguredValue -Name "TF_VAR_demo_purpose" -DefaultValue "sat-agentic-customer-demo"
$expiresAtRaw = Get-ConfiguredValue -Name "TF_VAR_demo_expires_at"
$now = [DateTimeOffset]::UtcNow
$status = "passed"
$parsedExpiresAt = $null
$ttlHours = $null

if (-not $owner) {
    Add-Check -Id "LIFECYCLE-OWNER" -Status "failed" -Blocking $true -Detail "TF_VAR_demo_owner is required for cleanup ownership."
    $status = "failed"
}
else {
    Add-Check -Id "LIFECYCLE-OWNER" -Status "passed" -Detail "demo_owner=$owner"
}

if (-not $purpose) {
    Add-Check -Id "LIFECYCLE-PURPOSE" -Status "failed" -Blocking $true -Detail "TF_VAR_demo_purpose is required."
    $status = "failed"
}
else {
    Add-Check -Id "LIFECYCLE-PURPOSE" -Status "passed" -Detail "demo_purpose=$purpose"
}

if (-not $expiresAtRaw) {
    Add-Check -Id "LIFECYCLE-EXPIRES" -Status "failed" -Blocking $true -Detail "TF_VAR_demo_expires_at is required, for example 2026-07-10T18:00:00Z."
    $status = "failed"
}
else {
    $parsed = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($expiresAtRaw, [ref]$parsed)) {
        Add-Check -Id "LIFECYCLE-EXPIRES" -Status "failed" -Blocking $true -Detail "TF_VAR_demo_expires_at is not parseable as a timestamp: $expiresAtRaw"
        $status = "failed"
    }
    else {
        $parsedExpiresAt = $parsed.ToUniversalTime()
        $ttlHours = ($parsedExpiresAt - $now).TotalHours
        if ($ttlHours -le 0) {
            Add-Check -Id "LIFECYCLE-EXPIRES" -Status "failed" -Blocking $true -Detail "TF_VAR_demo_expires_at is not in the future: $($parsedExpiresAt.ToString('o'))"
            $status = "failed"
        }
        elseif ($ttlHours -gt $MaxTtlHours -and -not $AllowLongLivedDemo) {
            Add-Check -Id "LIFECYCLE-TTL" -Status "failed" -Blocking $true -Detail ("TTL is {0:N1} hours, greater than MaxTtlHours={1}. Use a nearer expiration or pass -AllowLongLivedDemo." -f $ttlHours, $MaxTtlHours)
            $status = "failed"
        }
        elseif ($ttlHours -gt $MaxTtlHours -and $AllowLongLivedDemo) {
            Add-Check -Id "LIFECYCLE-TTL" -Status "warning" -Blocking $false -Detail ("Long-lived demo explicitly allowed. TTL is {0:N1} hours." -f $ttlHours)
            if ($status -ne "failed") { $status = "warning" }
        }
        else {
            Add-Check -Id "LIFECYCLE-EXPIRES" -Status "passed" -Detail ("expires_at={0}; ttl_hours={1:N1}" -f $parsedExpiresAt.ToString("o"), $ttlHours)
        }
    }
}

$report = [ordered]@{
    status = $status
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    apply = [bool]$Apply
    max_ttl_hours = $MaxTtlHours
    allow_long_lived_demo = [bool]$AllowLongLivedDemo
    demo_owner = $owner
    demo_purpose = $purpose
    demo_expires_at = if ($parsedExpiresAt) { $parsedExpiresAt.ToString("o") } else { $expiresAtRaw }
    ttl_hours = $ttlHours
    checks = $script:Checks
    next_action = if ($status -eq "failed") {
        "Set TF_VAR_demo_owner and a future TF_VAR_demo_expires_at before preflight/apply."
    }
    elseif ($status -eq "warning") {
        "Continue only if the long-lived demo has an owner and cleanup commitment."
    }
    else {
        "Continue with preflight/apply."
    }
}

$jsonPath = Join-Path $OutputDir "lifecycle_guard_latest.json"
$mdPath = Join-Path $OutputDir "lifecycle_guard.md"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = @(
    "# SAT Agentic Lifecycle Guard",
    "",
    "- status: $($report.status)",
    "- apply: $($report.apply)",
    "- demo_owner: $($report.demo_owner)",
    "- demo_purpose: $($report.demo_purpose)",
    "- demo_expires_at: $($report.demo_expires_at)",
    "- ttl_hours: $($report.ttl_hours)",
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

Write-Host "Lifecycle status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "failed") { "Red" } elseif ($report.status -eq "warning") { "Yellow" } else { "Green" }))
foreach ($check in $script:Checks) {
    $color = if ($check.status -eq "failed") { "Red" } elseif ($check.status -eq "warning") { "Yellow" } else { "Green" }
    Write-Host "  [$($check.status)] $($check.detail)" -ForegroundColor $color
}
Write-Host "Lifecycle JSON: $jsonPath"
Write-Host "Lifecycle report: $mdPath"

if (-not $EmitReportOnly -and $status -eq "failed") {
    throw "Lifecycle guard failed. $($report.next_action)"
}
