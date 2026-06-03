param()

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$DemoRoot = Join-Path $PackageRoot "demo"
$DataRoot = Join-Path $PackageRoot "data"

$required = @(
  "$DemoRoot\scripts\18_run_mrs_dataflow_workflow.py",
  "$DemoRoot\scripts\19_resume_mrs_notebook_workflow.ps1",
  "$DemoRoot\scripts\15_run_notebook_auto.ps1",
  "$DemoRoot\config\mrs-config.json",
  "$DataRoot\schema\inferred-table-schemas.json",
  "$DataRoot\raw-map.json",
  "$DataRoot\raw\dockone_exampleapp_payment_outbox.json"
)

$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
  $missing | ForEach-Object { Write-Host "missing $_" }
  throw "Package validation failed."
}

Set-Location -LiteralPath $DemoRoot
$env:SYNTHETIC_CDC_DATA_PATH = $DataRoot
python scripts\06_validate_demo_package.py
python -m py_compile scripts\18_run_mrs_dataflow_workflow.py

if (-not (Test-Path -LiteralPath "$DemoRoot\dist\hudi-spark3.3-bundle_2.12-0.15.0.jar")) {
  Write-Host "Hudi bundle is intentionally not committed. Run automation\Fetch-HudiBundle.ps1 before cloud upload."
}

Write-Host "Agent package validation passed."

