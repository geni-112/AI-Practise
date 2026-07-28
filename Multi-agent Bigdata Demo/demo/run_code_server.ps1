param(
  [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command code-server -ErrorAction SilentlyContinue)) {
  Write-Host "code-server is not installed on this machine."
  Write-Host "Install it when the IDE shell is needed, then rerun this script."
  exit 1
}

code-server $Root --bind-addr "127.0.0.1:$Port" --auth none
