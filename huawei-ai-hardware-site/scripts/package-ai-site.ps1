$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$staging = Join-Path $repoRoot ".local\ai-hardware-config-site"
$deploy = Join-Path $repoRoot "deploy"
$archive = Join-Path $deploy "ai-hardware-config-site.tar.gz"

if (Test-Path $staging) {
  Remove-Item -LiteralPath $staging -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $staging | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $staging "data") | Out-Null
New-Item -ItemType Directory -Force -Path $deploy | Out-Null

Copy-Item -Path (Join-Path $repoRoot "public\index.html") -Destination $staging
Copy-Item -Path (Join-Path $repoRoot "public\styles.css") -Destination $staging
Copy-Item -Path (Join-Path $repoRoot "public\dashboard.js") -Destination $staging
Copy-Item -Path (Join-Path $repoRoot "data\ai-hardware-config.json") -Destination (Join-Path $staging "data")

if (Test-Path $archive) {
  Remove-Item -LiteralPath $archive -Force
}

Push-Location $staging
try {
  tar -czf $archive .
}
finally {
  Pop-Location
}

Write-Host "Packaged AI hardware configuration site:"
Write-Host $archive
