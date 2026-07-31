param(
    [switch]$ConfirmDestroy,

    [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmDestroy) {
    throw "Refusing to destroy the cloud cleanup controller without -ConfirmDestroy."
}
if (-not $AutoApprove) {
    throw "Non-interactive cleanup requires -AutoApprove."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$terraformDir = Join-Path $root "cloud_real_bigdata\cloud_cleanup\terraform"
$roleScript = Join-Path $root "cloud_real_bigdata\cloud_cleanup\scripts\manage_dayu_role.py"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

Push-Location $terraformDir
try {
    terraform destroy -input=false -auto-approve -parallelism=1
    if ($LASTEXITCODE -ne 0) { throw "Cloud cleanup controller destroy failed." }

    $remaining = @(terraform state list 2>$null | Where-Object { $_.Trim() })
    if ($LASTEXITCODE -ne 0) { throw "Unable to validate the cleanup controller state." }
    if ($remaining.Count -gt 0) {
        throw "Cleanup controller Terraform state is not empty: $($remaining -join ', ')"
    }
}
finally {
    Pop-Location
}

& $python $roleScript remove
if ($LASTEXITCODE -ne 0) { throw "Failed to remove the temporary DAYU Administrator role." }

Write-Host "Cloud cleanup controller and temporary IAM grants were removed." -ForegroundColor Green
