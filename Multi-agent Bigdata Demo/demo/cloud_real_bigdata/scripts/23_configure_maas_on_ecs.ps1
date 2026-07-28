param(
    [Parameter(Mandatory = $true)]
    [string]$WebPublicIp,

    [Parameter(Mandatory = $true)]
    [string]$SshKeyPath,

    [string]$SshUser = "root",

    [string]$ServiceName = "sat-agent-vibe",

    [string]$RemoteEnvironmentFile = "/etc/sat-agent-vibe/maas.env"
)

$ErrorActionPreference = "Stop"

function Get-RequiredSecret {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required process environment variable is missing: $Name"
    }
    return $value
}

function Escape-EnvironmentValue {
    param([string]$Value)
    return $Value.Replace("\", "\\").Replace('"', '\"')
}

if (-not (Test-Path -LiteralPath $SshKeyPath)) {
    throw "SSH key path not found: $SshKeyPath"
}

$apiKey = Get-RequiredSecret "HUAWEI_MAAS_API_KEY"
$baseUrl = [Environment]::GetEnvironmentVariable("HUAWEI_MAAS_BASE_URL", "Process")
$model = [Environment]::GetEnvironmentVariable("HUAWEI_MAAS_MODEL", "Process")
if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    $baseUrl = "https://api-ap-southeast-1.modelarts-maas.com/openai/v1"
}
if ([string]::IsNullOrWhiteSpace($model)) {
    $model = "glm-5.2"
}

$tempEnvironmentFile = Join-Path $env:TEMP ("sat-agent-maas-{0}.env" -f ([guid]::NewGuid().ToString("N")))
$remoteTempFile = "/tmp/sat-agent-maas.env"
$sshTarget = "$SshUser@$WebPublicIp"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

try {
    $content = @(
        "HUAWEI_MAAS_API_KEY=`"$(Escape-EnvironmentValue $apiKey)`"",
        "HUAWEI_MAAS_BASE_URL=`"$(Escape-EnvironmentValue $baseUrl)`"",
        "HUAWEI_MAAS_MODEL=`"$(Escape-EnvironmentValue $model)`""
    ) -join "`n"
    [System.IO.File]::WriteAllText($tempEnvironmentFile, "$content`n", $utf8NoBom)

    Write-Host "Uploading MaaS configuration without printing secret values" -ForegroundColor Cyan
    & scp -q -i $SshKeyPath -o StrictHostKeyChecking=accept-new $tempEnvironmentFile "${sshTarget}:$remoteTempFile"
    if ($LASTEXITCODE -ne 0) {
        throw "MaaS environment upload failed"
    }

    $remoteDirectory = $RemoteEnvironmentFile -replace "/[^/]+$", ""
    $dropInDirectory = "/etc/systemd/system/$ServiceName.service.d"
    $dropInFile = "$dropInDirectory/10-maas.conf"
    $remoteCommand = @(
        "set -euo pipefail",
        "install -d -m 700 '$remoteDirectory'",
        "install -m 600 '$remoteTempFile' '$RemoteEnvironmentFile'",
        "rm -f '$remoteTempFile'",
        "install -d -m 755 '$dropInDirectory'",
        "printf '[Service]\nEnvironmentFile=$RemoteEnvironmentFile\n' > '$dropInFile'",
        "chmod 644 '$dropInFile'",
        "systemctl daemon-reload",
        "systemctl restart '$ServiceName'",
        "systemctl is-active --quiet '$ServiceName'",
        "test `$(stat -c '%a' '$RemoteEnvironmentFile') = 600"
    ) -join "; "

    & ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new $sshTarget $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Remote MaaS service configuration failed"
    }

    $base = "http://$WebPublicIp"
    $health = $null
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 10
            if ($health.ok -and $health.maas_configured) { break }
        } catch {
            $health = $null
        }
        Start-Sleep -Seconds 2
    }
    if (-not $health -or -not $health.maas_configured) {
        throw "Remote service did not report MaaS as configured"
    }

    $testBody = @{
        prompt = "Return compact JSON with status ok and purpose MaaS connectivity test."
    } | ConvertTo-Json
    $testResult = Invoke-RestMethod -Method Post -Uri "$base/api/maas/test" -ContentType "application/json" -Body $testBody -TimeoutSec 120
    if (-not $testResult.ok) {
        throw "Remote MaaS connectivity test failed: $($testResult.error)"
    }

    $root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    $reportDir = Join-Path $root ".cloud_real_bigdata_work\maas_deploy"
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    $report = [ordered]@{
        status = "configured"
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        target_url = $base
        service = $ServiceName
        environment_file = $RemoteEnvironmentFile
        environment_file_mode = "600"
        model = $testResult.model
        health_ok = [bool]$health.ok
        maas_configured = [bool]$health.maas_configured
        connectivity_test_ok = [bool]$testResult.ok
        secret_values_printed = $false
    }
    $reportPath = Join-Path $reportDir "maas_deploy_latest.json"
    $report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    Write-Host "MaaS configured and tested successfully" -ForegroundColor Green
    Write-Host "Model: $($testResult.model)"
    Write-Host "Report: $reportPath"
} finally {
    if (Test-Path -LiteralPath $tempEnvironmentFile) {
        Remove-Item -LiteralPath $tempEnvironmentFile -Force
    }
}
