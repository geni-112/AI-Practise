param(
    [Parameter(Mandatory = $true)]
    [string]$WebPublicIp,

    [string]$SshKeyPath = "",

    [string]$SshUser = "root",

    [string]$RemoteDir = "/opt/sat-agent-vibe-poc",

    [int]$AppPort = 8788,

    [string]$OutputDir = "",

    [switch]$SkipSsh
)

$ErrorActionPreference = "Stop"

function Add-Check {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Status,
        [string]$Detail,
        [bool]$Critical = $false,
        [object]$Data = $null
    )
    $script:Checks += [ordered]@{
        id = $Id
        name = $Name
        status = $Status
        critical = $Critical
        detail = $Detail
        data = $Data
    }
}

function Require-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Required command not found: $Name"
    }
}

function ConvertTo-BashSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'`"`"'") + "'"
}

function Sanitize-Text {
    param([string]$Text)
    if ($null -eq $Text) {
        return ""
    }
    $sanitized = $Text -replace "(?i)(access[_-]?key|secret[_-]?key|api[_-]?key|password|passwd|token|credential|authorization)\s*[:=]\s*[^,\s;]+", '$1=<redacted>'
    return $sanitized.Trim()
}

function Invoke-RemoteCheck {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Command,
        [bool]$Critical = $false,
        [int]$TimeoutSeconds = 20
    )
    $sshTarget = "$SshUser@$WebPublicIp"
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & ssh `
            -i $SshKeyPath `
            -o StrictHostKeyChecking=accept-new `
            -o BatchMode=yes `
            -o ConnectTimeout=$TimeoutSeconds `
            $sshTarget `
            $Command 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    $text = Sanitize-Text (($output | Out-String).Trim())
    $status = if ($exitCode -eq 0) { "passed" } elseif ($Critical) { "failed" } else { "warning" }
    Add-Check -Id $Id -Name $Name -Status $status -Detail ($(if ($text) { $text } else { "exit_code=$exitCode" })) -Critical $Critical -Data ([ordered]@{
        exit_code = $exitCode
        output = $text
    })
}

function Invoke-PublicJsonCheck {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Url,
        [bool]$Critical = $false
    )
    try {
        $response = Invoke-RestMethod -Method Get -Uri $Url -Headers @{ "Cache-Control" = "no-cache" } -TimeoutSec 12
        Add-Check -Id $Id -Name $Name -Status "passed" -Detail "reachable: $Url" -Critical $Critical -Data $response
        return $response
    }
    catch {
        $status = if ($Critical) { "failed" } else { "warning" }
        Add-Check -Id $Id -Name $Name -Status $status -Detail $_.Exception.Message -Critical $Critical
        return $null
    }
}

function Render-MarkdownTable {
    param([array]$Rows)
    $lines = @(
        "| status | critical | id | name | detail |",
        "| --- | --- | --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $detail = ([string]$row.detail).Replace("|", "\|").Replace("`r", " ").Replace("`n", "<br>")
        $name = ([string]$row.name).Replace("|", "\|")
        $lines += "| $($row.status) | $($row.critical) | $($row.id) | $name | $detail |"
    }
    return $lines
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\web_diagnostics"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$script:Checks = @()
$startedAt = (Get-Date).ToUniversalTime().ToString("o")
$baseUrl = "http://$WebPublicIp"

Write-Host "SAT Agentic web ECS diagnostics" -ForegroundColor Cyan
Write-Host "  target: $baseUrl"
Write-Host "  ssh checks: $(-not $SkipSsh)"
Write-Host ""

if (-not $SkipSsh) {
    Require-Command "ssh"
    if (-not $SshKeyPath) {
        throw "SshKeyPath is required unless -SkipSsh is used."
    }
    if (-not (Test-Path -LiteralPath $SshKeyPath)) {
        throw "SSH key path not found: $SshKeyPath"
    }

    $qRemoteDir = ConvertTo-BashSingleQuoted $RemoteDir
    $qEvidenceDir = ConvertTo-BashSingleQuoted "$RemoteDir/cloud_real_bigdata/public_evidence"

    Invoke-RemoteCheck -Id "SSH-001" -Name "SSH remote shell" -Command "printf connected" -Critical $true
    Invoke-RemoteCheck -Id "REMOTE-001" -Name "Application directory exists" -Command "test -d $qRemoteDir && printf present || (printf missing; exit 1)" -Critical $true
    Invoke-RemoteCheck -Id "SYSTEMD-001" -Name "sat-agent-vibe service active" -Command "systemctl is-active sat-agent-vibe" -Critical $true
    Invoke-RemoteCheck -Id "SYSTEMD-002" -Name "sat-agent-vibe service enabled" -Command "systemctl is-enabled sat-agent-vibe" -Critical $false
    Invoke-RemoteCheck -Id "NGINX-001" -Name "nginx service active" -Command "systemctl is-active nginx" -Critical $true
    Invoke-RemoteCheck -Id "NGINX-002" -Name "nginx config test" -Command "sudo nginx -t" -Critical $true
    Invoke-RemoteCheck -Id "LOCAL-API-001" -Name "Local FastAPI health" -Command "curl -fsS http://127.0.0.1:$AppPort/api/health" -Critical $true
    Invoke-RemoteCheck -Id "LOCAL-API-002" -Name "Local cloud evidence API" -Command "curl -fsS http://127.0.0.1:$AppPort/api/cloud/e2e-evidence" -Critical $false
    Invoke-RemoteCheck -Id "LOCAL-API-003" -Name "Local gold query API" -Command "curl -fsS http://127.0.0.1:$AppPort/api/cloud/gold-query" -Critical $false
    Invoke-RemoteCheck -Id "EVIDENCE-REMOTE-001" -Name "Remote evidence file inventory" -Command "if test -d $qEvidenceDir; then find $qEvidenceDir -maxdepth 1 -type f -printf '%f\n' | sort; else printf 'missing evidence directory'; exit 2; fi" -Critical $false
    Invoke-RemoteCheck -Id "LOGS-001" -Name "Recent application logs" -Command "journalctl -u sat-agent-vibe -n 40 --no-pager || true" -Critical $false
}
else {
    Add-Check -Id "SSH-000" -Name "SSH checks skipped" -Status "warning" -Detail "-SkipSsh was used" -Critical $false
}

$health = Invoke-PublicJsonCheck -Id "PUBLIC-001" -Name "Public website health API" -Url "$baseUrl/api/health" -Critical $true
$evidence = Invoke-PublicJsonCheck -Id "PUBLIC-002" -Name "Public cloud evidence API" -Url "$baseUrl/api/cloud/e2e-evidence" -Critical $true
$goldQuery = Invoke-PublicJsonCheck -Id "PUBLIC-003" -Name "Public gold query API" -Url "$baseUrl/api/cloud/gold-query" -Critical $true
$summary = Invoke-PublicJsonCheck -Id "PUBLIC-004" -Name "Public customer summary" -Url "$baseUrl/cloud-evidence/customer_demo_summary.json" -Critical $false

$failedCritical = @($script:Checks | Where-Object { $_.critical -and $_.status -eq "failed" })
$warnings = @($script:Checks | Where-Object { $_.status -eq "warning" })
$finalStatus = if ($failedCritical.Count -gt 0) {
    "failed"
}
elseif ($evidence -and [bool]$evidence.available -and [string]$evidence.status -eq "success" -and $goldQuery -and [int]$goldQuery.filtered_count -gt 0 -and $summary -and [string]$summary.status -eq "ready_for_customer_demo") {
    "ready_for_customer_demo"
}
elseif ($health -and [bool]$health.ok) {
    "deployed_no_cloud_evidence"
}
else {
    "deployed_needs_attention"
}

$report = [ordered]@{
    status = $finalStatus
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    started_at = $startedAt
    values_printed = $false
    target = [ordered]@{
        base_url = $baseUrl
        web_public_ip = $WebPublicIp
        ssh_user = if ($SkipSsh) { "" } else { $SshUser }
        remote_dir = $RemoteDir
        app_port = $AppPort
        ssh_checked = -not [bool]$SkipSsh
    }
    failed_critical_count = $failedCritical.Count
    warning_count = $warnings.Count
    checks = $script:Checks
    next_action = if ($finalStatus -eq "ready_for_customer_demo") {
        "Run 09_final_acceptance_audit.ps1 -BaseUrl `"$baseUrl`" -RequireCloudSuccess."
    }
    elseif ($finalStatus -eq "deployed_no_cloud_evidence") {
        "Run the real MRS E2E flow, then redeploy or refresh public_evidence and rerun this diagnostic."
    }
    else {
        "Inspect failed checks, then rerun 06_deploy_frontend_to_ecs.ps1 or the failing remote service command."
    }
}

$jsonPath = Join-Path $OutputDir "web_diagnostics_latest.json"
$mdPath = Join-Path $OutputDir "web_diagnostics.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# SAT Agentic Web ECS Diagnostics",
    "",
    "- status: $($report.status)",
    "- generated_at: $($report.generated_at)",
    "- base_url: $baseUrl",
    "- failed_critical_count: $($report.failed_critical_count)",
    "- warning_count: $($report.warning_count)",
    "- values_printed: false",
    "",
    "## Checks",
    ""
)
$md += Render-MarkdownTable $script:Checks
$md += @(
    "",
    "## Next Action",
    "",
    $report.next_action
)
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

foreach ($check in $script:Checks) {
    $color = switch ($check.status) {
        "passed" { "Green" }
        "warning" { "Yellow" }
        default { "Red" }
    }
    Write-Host "[$($check.status)] $($check.name) - $($check.detail)" -ForegroundColor $color
}
Write-Host ""
Write-Host "Diagnostics JSON: $jsonPath"
Write-Host "Diagnostics report: $mdPath"
Write-Host "Final status: $finalStatus" -ForegroundColor ($(if ($finalStatus -eq "failed") { "Red" } else { "Green" }))

if ($finalStatus -eq "failed") {
    exit 1
}
