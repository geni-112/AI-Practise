$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
python -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-deploy.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Deployment dependency installation failed with exit code $LASTEXITCODE."
}
