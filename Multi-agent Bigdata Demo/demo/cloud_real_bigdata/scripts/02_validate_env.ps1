param(
    [switch]$RequireDws
)

$ErrorActionPreference = "Stop"

function Test-Configured {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    }
    return [bool]$value
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$Python = if (Test-Path $venvPython) { $venvPython } else { "python" }

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

$checks = @(
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "TF_VAR_mrs_manager_admin_password",
    "TF_VAR_node_key_pair_name"
)
if ($RequireDws) {
    $checks += "TF_VAR_dws_admin_password"
}

Write-Host "Checking local tools" -ForegroundColor Cyan
foreach ($cmd in @("terraform")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) {
        throw "Required command not found: $cmd"
    }
    Write-Host "  ok: $cmd -> $($found.Source)"
}
Write-Host "  ok: python -> $Python"

Write-Host ""
Write-Host "Checking Python cloud dependencies" -ForegroundColor Cyan
$pythonCheck = @"
mods = ["huaweicloudsdkcore", "huaweicloudsdkmrs", "huaweicloudsdkdws", "obs"]
for mod in mods:
    __import__(mod)
    print(f"  ok: {mod}")
"@
$pythonCheck | & $Python -
if ($LASTEXITCODE -ne 0) {
    throw "Python cloud dependencies are missing. Run: python -m pip install -r requirements-huaweicloud-readonly.txt"
}

Write-Host ""
Write-Host "Checking environment variables without printing secret values" -ForegroundColor Cyan
$missing = @()
foreach ($name in $checks) {
    if (Test-Configured $name) {
        Write-Host "  ok: $name is configured"
    }
    else {
        Write-Host "  missing: $name" -ForegroundColor Yellow
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}

Write-Host ""
Write-Host "Environment is ready for Terraform plan/apply." -ForegroundColor Green
