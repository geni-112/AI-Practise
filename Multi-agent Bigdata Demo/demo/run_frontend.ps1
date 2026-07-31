param(
  [int]$Port = 8788,
  [string]$HostAddress = "127.0.0.1",
  [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  python -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Set-Location $Root
$UvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", $Port)
if (-not $NoReload) {
  $UvicornArgs += "--reload"
}
& $Python @UvicornArgs
