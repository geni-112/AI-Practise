param([switch]$Strict)

$required = @("HUAWEICLOUD_REGION", "HUAWEICLOUD_PROJECT_ID", "DEMO_BUCKET", "DLI_ENDPOINT", "DLI_QUEUE_NAME")
$missing = @()
foreach ($name in $required) {
  if (-not [Environment]::GetEnvironmentVariable($name)) {
    $missing += $name
  }
}

python --version
if ($LASTEXITCODE -ne 0) { throw "Python is required." }

if ($missing.Count -gt 0) {
  Write-Warning ("Missing environment variables: " + ($missing -join ", "))
  if ($Strict) { throw "Set required environment variables before continuing." }
}

Write-Host "Prerequisite check finished. Use -Strict for cloud execution checks."
