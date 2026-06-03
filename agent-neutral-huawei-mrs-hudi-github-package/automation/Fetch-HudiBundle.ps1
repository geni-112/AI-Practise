param(
  [string]$Version = "0.15.0",
  [string]$ScalaSparkArtifact = "hudi-spark3.3-bundle_2.12",
  [string]$DemoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $DemoRoot) {
  $PackageRoot = Split-Path -Parent $PSScriptRoot
  $DemoRoot = Join-Path $PackageRoot "demo"
}

$dist = Join-Path $DemoRoot "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null

$jarName = "$ScalaSparkArtifact-$Version.jar"
$target = Join-Path $dist $jarName
if (Test-Path -LiteralPath $target) {
  Write-Host "Hudi bundle already exists: $target"
  return
}

$url = "https://repo1.maven.org/maven2/org/apache/hudi/$ScalaSparkArtifact/$Version/$jarName"
Write-Host "Downloading $url"
Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing

$size = (Get-Item -LiteralPath $target).Length
if ($size -lt 100000000) {
  throw "Downloaded Hudi jar is unexpectedly small: $size bytes"
}

Write-Host "Downloaded Hudi bundle: $target"

