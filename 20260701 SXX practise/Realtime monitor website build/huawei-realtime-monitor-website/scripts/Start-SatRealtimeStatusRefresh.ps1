param(
  [int]$IntervalSeconds = 20,
  [string]$Region = "la-north-2",
  [string]$Bucket = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot "logs"
$exportDir = Join-Path $repoRoot "exports"
$pidFile = Join-Path $exportDir "sat_live_refresh.pid"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null

if (Test-Path -LiteralPath $pidFile) {
  $existingPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($existingPid) {
    $existingProcess = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
    if ($existingProcess) {
      Write-Host "SAT realtime status refresher is already running as PID $existingPid."
      return
    }
  }
}
Set-Content -LiteralPath $pidFile -Value ([string]$PID) -Encoding ASCII

. (Join-Path $PSScriptRoot "Load-HuaweiCredentialProfile.ps1")
$env:HUAWEICLOUD_REGION = $Region

$args = @(
  "-X", "utf8",
  (Join-Path $PSScriptRoot "refresh_live_status.py"),
  "--region", $Region,
  "--interval", [string]$IntervalSeconds,
  "--loop"
)
if ($Bucket) {
  $args += @("--bucket", $Bucket)
}

try {
  python @args 2>&1 | Tee-Object -FilePath (Join-Path $logDir "sat_live_refresh_process.log") -Append
} finally {
  $currentPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($currentPid -eq ([string]$PID)) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  }
}
