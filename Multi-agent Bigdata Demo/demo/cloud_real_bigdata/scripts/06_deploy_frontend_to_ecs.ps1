param(
    [Parameter(Mandatory = $true)]
    [string]$WebPublicIp,

    [Parameter(Mandatory = $true)]
    [string]$SshKeyPath,

    [string]$SshUser = "root",

    [string]$RemoteDir = "/opt/sat-agent-vibe-poc",

    [int]$AppPort = 8788
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Required command not found: $Name"
    }
    return $cmd.Source
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$workDir = Join-Path $root ".cloud_real_bigdata_work\web_deploy"
$stagingDir = Join-Path $workDir "package_root"
$packagePath = Join-Path $workDir "sat-agent-vibe-poc.tar.gz"
$remotePackage = "/tmp/sat-agent-vibe-poc.tar.gz"

Write-Step "Checking local deploy tools"
Require-Command "ssh" | Out-Null
Require-Command "scp" | Out-Null
Require-Command "tar" | Out-Null
if (-not (Test-Path -LiteralPath $SshKeyPath)) {
    throw "SSH key path not found: $SshKeyPath"
}

Write-Step "Packaging frontend application"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
if (Test-Path -LiteralPath $packagePath) {
    Remove-Item -LiteralPath $packagePath -Force
}
if (Test-Path -LiteralPath $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

$excludeRegex = "\\.git\\|\\.venv\\|\\.terraform\\|\\.cloud_real_bigdata_work\\|generated\\|evaluations\\|logs\\|__pycache__|\\.pyc$|terraform\\.tfstate|terraform\\.tfstate\\.backup|tfplan$|\\.tfplan$|\\.pem$|\\.key$|\\.pfx$|\\.p12$"
$secretFileRegex = '^\.env($|\.)'
$rootText = $root.Path.TrimEnd("\")
$files = @(Get-ChildItem -Path $root -Recurse -File | Where-Object {
    $_.Name -notmatch $secretFileRegex -and $_.FullName -notmatch $excludeRegex
})
foreach ($file in $files) {
    $relative = $file.FullName.Substring($rootText.Length + 1)
    $destination = Join-Path $stagingDir $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}
$runtimeStatusDir = Join-Path $stagingDir "cloud_real_bigdata\runtime_status"
$runtimeStatusSources = @(
    @{ Source = ".cloud_real_bigdata_work\credential_status\credential_status_latest.json"; Name = "credential_status.json" },
    @{ Source = ".cloud_real_bigdata_work\apply_safety\apply_safety_latest.json"; Name = "apply_safety.json" },
    @{ Source = ".cloud_real_bigdata_work\lifecycle_guard\lifecycle_guard_latest.json"; Name = "lifecycle_guard.json" },
    @{ Source = ".cloud_real_bigdata_work\minimal_cost_quota_plan\minimal_cost_quota_plan_latest.json"; Name = "minimal_cost_quota_plan.json" },
    @{ Source = ".cloud_real_bigdata_work\readonly_probe\readonly_probe_latest.json"; Name = "readonly_probe.json" },
    @{ Source = ".cloud_real_bigdata_work\pre_apply_readiness\pre_apply_readiness_latest.json"; Name = "pre_apply_readiness.json" },
    @{ Source = ".cloud_real_bigdata_work\operator_bootstrap\operator_bootstrap_latest.json"; Name = "operator_bootstrap.json" },
    @{ Source = ".cloud_real_bigdata_work\customer_handoff\customer_handoff_latest.json"; Name = "customer_handoff.json" },
    @{ Source = ".cloud_real_bigdata_work\customer_commercial_readiness\customer_commercial_readiness_latest.json"; Name = "customer_commercial_readiness.json" },
    @{ Source = ".cloud_real_bigdata_work\real_cloud_preflight\real_cloud_preflight_latest.json"; Name = "real_cloud_preflight.json" },
    @{ Source = ".cloud_real_bigdata_work\acceptance_audit\final_acceptance_audit.json"; Name = "final_acceptance_audit.json" },
    @{ Source = ".cloud_real_bigdata_work\web_diagnostics\web_diagnostics_latest.json"; Name = "web_diagnostics.json" }
)
$runtimeStatusCount = 0
foreach ($statusSource in $runtimeStatusSources) {
    $sourcePath = Join-Path $root $statusSource.Source
    if (-not (Test-Path -LiteralPath $sourcePath)) { continue }
    New-Item -ItemType Directory -Force -Path $runtimeStatusDir | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $runtimeStatusDir $statusSource.Name) -Force
    $runtimeStatusCount++
}
& tar -czf $packagePath -C $stagingDir .
if ($LASTEXITCODE -ne 0) {
    throw "tar package creation failed"
}
$forbiddenEntries = @(& tar -tzf $packagePath | Where-Object { $_ -match "(^|/)\.env($|\.)" })
if ($LASTEXITCODE -ne 0) {
    throw "tar package inspection failed"
}
if ($forbiddenEntries.Count -gt 0) {
    throw "Deployment package contains forbidden environment files. Upload was blocked."
}

Write-Step "Uploading package to ECS"
$sshTarget = "$SshUser@$WebPublicIp"
& scp -i $SshKeyPath -o StrictHostKeyChecking=accept-new $packagePath "${sshTarget}:$remotePackage"
if ($LASTEXITCODE -ne 0) {
    throw "scp upload failed"
}

Write-Step "Installing service on ECS"
$remoteScript = @"
set -euo pipefail
sudo mkdir -p $RemoteDir
sudo apt-get update
sudo apt-get install -y python3 python3-venv nginx
sudo tar -xzf $remotePackage -C $RemoteDir
sudo rm -f -- $RemoteDir/.env $RemoteDir/.env.*
sudo chown -R ${SshUser}:${SshUser} $RemoteDir
cd $RemoteDir
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [ -f requirements-huaweicloud-readonly.txt ]; then
  python -m pip install -r requirements-huaweicloud-readonly.txt
fi
sudo tee /etc/systemd/system/sat-agent-vibe.service >/dev/null <<'EOF'
[Unit]
Description=SAT Agentic Vibe FastAPI
After=network.target

[Service]
Type=simple
WorkingDirectory=$RemoteDir
ExecStart=$RemoteDir/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $AppPort
Restart=always
RestartSec=5
User=$SshUser
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/nginx/sites-available/sat-agent-vibe >/dev/null <<'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:$AppPort;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/sat-agent-vibe /etc/nginx/sites-enabled/sat-agent-vibe
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl daemon-reload
sudo systemctl enable sat-agent-vibe
sudo systemctl restart sat-agent-vibe
sudo nginx -t
sudo systemctl reload nginx
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:$AppPort/api/health; then
    break
  fi
  if [ "`$attempt" -eq 30 ]; then
    echo "FastAPI health check did not become ready." >&2
    exit 1
  fi
  sleep 2
done
rm -f -- $remotePackage
"@

$tempScript = Join-Path $workDir "install_web.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$remoteScriptLf = $remoteScript -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($tempScript, $remoteScriptLf, $utf8NoBom)
& scp -i $SshKeyPath -o StrictHostKeyChecking=accept-new $tempScript "${sshTarget}:/tmp/install_sat_agent_vibe.sh"
if ($LASTEXITCODE -ne 0) {
    throw "scp remote install script failed"
}
& ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new $sshTarget "bash /tmp/install_sat_agent_vibe.sh"
if ($LASTEXITCODE -ne 0) {
    throw "remote install failed"
}

Write-Step "Cloud frontend ready"
Write-Host "URL: http://$WebPublicIp/"

$packageInfo = Get-Item -LiteralPath $packagePath
$packageHash = Get-FileHash -LiteralPath $packagePath -Algorithm SHA256
$manifest = [ordered]@{
    status = "deployed"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    web_public_ip = $WebPublicIp
    target_url = "http://$WebPublicIp/"
    ssh_user = $SshUser
    remote_dir = $RemoteDir
    app_port = $AppPort
    package_path = $packagePath
    package_bytes = $packageInfo.Length
    package_sha256 = $packageHash.Hash
    packaged_file_count = $files.Count
    runtime_status_file_count = $runtimeStatusCount
    exclude_policy = $excludeRegex
    secret_file_policy = $secretFileRegex
    next_action = ".\cloud_real_bigdata\scripts\13_diagnose_web_ecs.ps1 -WebPublicIp `"$WebPublicIp`" -SshKeyPath `"<path-to-private-key.pem>`""
}
$manifestPath = Join-Path $workDir "web_deploy_manifest.json"
$manifestReportPath = Join-Path $workDir "web_deploy_manifest.md"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
@(
    "# SAT Agentic Web Deploy Manifest",
    "",
    "- status: $($manifest.status)",
    "- generated_at: $($manifest.generated_at)",
    "- target_url: $($manifest.target_url)",
    "- remote_dir: $($manifest.remote_dir)",
    "- app_port: $($manifest.app_port)",
    "- package_bytes: $($manifest.package_bytes)",
    "- packaged_file_count: $($manifest.packaged_file_count)",
    "- values_printed: false",
    "",
    "## Next Action",
    "",
    '```powershell',
    $manifest.next_action,
    '```'
) | Set-Content -LiteralPath $manifestReportPath -Encoding UTF8
Write-Host "Deploy manifest: $manifestPath"
