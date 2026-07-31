param(
    [string]$ObsBucketName = "",

    [string]$BucketPrefix = "sat-agentic",

    [string]$OutputDir = ""
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

function Render-MarkdownTable {
    param([array]$Rows)
    $lines = @(
        "| status | check | detail |",
        "| --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $status = ([string]$row.status).Replace("|", "\|")
        $name = ([string]$row.name).Replace("|", "\|")
        $detail = ""
        if ($row.error) {
            $detail = [string]$row.error.message
        }
        elseif ($row.details) {
            $detail = (($row.details | ConvertTo-Json -Compress -Depth 5) -replace "\|", "\|")
        }
        $detail = $detail.Replace("`r", " ").Replace("`n", " ")
        $lines += "| $status | $name | $detail |"
    }
    return $lines
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$Python = if (Test-Path $venvPython) { $venvPython } else { "python" }
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $ObsBucketName) {
    $ObsBucketName = if ($env:TF_VAR_obs_bucket_name) { $env:TF_VAR_obs_bucket_name } else { New-BucketName -Prefix $BucketPrefix }
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\readonly_probe"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$jsonPath = Join-Path $OutputDir "readonly_probe_latest.json"
$mdPath = Join-Path $OutputDir "readonly_probe.md"
$region = if ($env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION } elseif ($env:HW_REGION_NAME) { $env:HW_REGION_NAME } else { "la-south-2" }
$tfDir = Join-Path $root "cloud_real_bigdata\terraform"
$allowExistingOwnedBucket = $false
if (Test-Path -LiteralPath (Join-Path $tfDir "terraform.tfstate")) {
    Push-Location $tfDir
    try {
        $stateJson = terraform show -json 2>$null
        if ($LASTEXITCODE -eq 0 -and $stateJson) {
            $state = $stateJson | ConvertFrom-Json
            $resources = @($state.values.root_module.resources)
            $managedBucket = $resources | Where-Object {
                $_.address -eq "huaweicloud_obs_bucket.lake" -and
                [string]$_.values.bucket -eq $ObsBucketName
            } | Select-Object -First 1
            $allowExistingOwnedBucket = [bool]$managedBucket
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "SAT Agentic Huawei Cloud read-only probe" -ForegroundColor Cyan
Write-Host "  bucket: $ObsBucketName"
Write-Host "  region: $region"
Write-Host "  state-managed bucket recovery: $allowExistingOwnedBucket"
Write-Host "  creates resources: false"
Write-Host ""

$probeArgs = @(
    (Join-Path $scriptDir "readonly_cloud_probe.py"),
    "--bucket", $ObsBucketName,
    "--output", $jsonPath
)
if ($allowExistingOwnedBucket) {
    $probeArgs += "--allow-existing-owned-bucket"
}
$probeOutput = & $Python @probeArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    $probeOutput | Set-Content -LiteralPath (Join-Path $OutputDir "readonly_probe_error.log") -Encoding UTF8
    throw "Read-only cloud probe failed before report generation."
}
$report = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json

$md = @(
    "# SAT Agentic Huawei Cloud Read-Only Probe",
    "",
    "- status: $($report.status)",
    "- generated_at: $($report.generated_at)",
    "- region: $($report.region)",
    "- target_bucket: $($report.target_bucket)",
    "- creates_resources: false",
    "- uploads_obs_objects: false",
    "- submits_mrs_job: false",
    "- network_calls: $($report.network_calls)",
    "- write_calls: $($report.write_calls)",
    "- values_printed: false",
    ""
)
if ($report.missing_required -and $report.missing_required.Count -gt 0) {
    $md += "## Missing Required"
    $md += ""
    foreach ($name in $report.missing_required) {
        $md += "- $name"
    }
    $md += ""
}
if ($report.checks -and $report.checks.Count -gt 0) {
    $md += "## Checks"
    $md += ""
    $md += Render-MarkdownTable $report.checks
    $md += ""
}
$md += "## Next Action"
$md += ""
if ($report.status -eq "passed") {
    $md += "Run `15_pre_apply_readiness.ps1 -EnableWebEcs -RunTerraformPreflight`."
}
elseif ($report.status -eq "missing_credentials") {
    $md += "Configure Huawei Cloud credentials through environment variables or ignored `.env.local`, then rerun this probe."
}
else {
    $md += "Fix failed read-only probe checks before paid apply."
}
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Read-only probe status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "passed") { "Green" } elseif ($report.status -eq "missing_credentials") { "Yellow" } else { "Red" }))
Write-Host "Probe JSON: $jsonPath"
Write-Host "Probe report: $mdPath"

if ($report.status -eq "failed") {
    exit 1
}
