param(
    [string]$ExpectedDate = "2026-07-24",

    [string]$ExecutionAgencyId = "0cb9cfc3ac00106c4f2fc007d0d69466",

    [ValidateSet("ACTIVE", "DISABLED")]
    [string]$TriggerStatus = "DISABLED"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
$mainTfDir = Join-Path $root "cloud_real_bigdata\terraform"
$cleanupRoot = Join-Path $root "cloud_real_bigdata\cloud_cleanup"
$cleanupTfDir = Join-Path $cleanupRoot "terraform"
$functionDir = Join-Path $cleanupRoot "function"
$buildDir = Join-Path $cleanupRoot "build\package"
$zipPath = Join-Path $cleanupRoot "build\sat-agentic-cleanup.zip"
$tfvarsPath = Join-Path $cleanupTfDir "cleanup.auto.tfvars.json"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

$resolvedBuild = [System.IO.Path]::GetFullPath($buildDir)
$resolvedCleanupRoot = [System.IO.Path]::GetFullPath($cleanupRoot)
if (-not $resolvedBuild.StartsWith($resolvedCleanupRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to rebuild outside cloud_cleanup: $resolvedBuild"
}
if (Test-Path -LiteralPath $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

& $python -m pip install `
    --disable-pip-version-check `
    --quiet `
    --target $buildDir `
    "esdk-obs-python==3.26.2" `
    "huaweicloudsdkcore==3.1.206"
if ($LASTEXITCODE -ne 0) { throw "Failed to package the Huawei Cloud SDK runtime." }
& $python -m pip install `
    --disable-pip-version-check `
    --quiet `
    --upgrade `
    --force-reinstall `
    --no-deps `
    --target $buildDir `
    --platform manylinux2014_x86_64 `
    --implementation cp `
    --python-version 3.10 `
    --abi cp310 `
    --only-binary=:all: `
    "pycryptodome"
if ($LASTEXITCODE -ne 0) { throw "Failed to package the Linux cryptography runtime." }
$linuxCrypto = Get-ChildItem -LiteralPath (Join-Path $buildDir "Crypto") -Recurse -File -Filter "*.so"
if (-not $linuxCrypto) { throw "The cleanup package does not contain Linux cryptography modules." }
Copy-Item -LiteralPath (Join-Path $functionDir "index.py") -Destination (Join-Path $buildDir "index.py") -Force
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in Get-ChildItem -LiteralPath $buildDir -Recurse -File) {
        $entryName = $file.FullName.Substring($buildDir.Length).TrimStart("\").Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

Push-Location $mainTfDir
try {
    $state = terraform show -json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Unable to read the main Terraform state." }
}
finally {
    Pop-Location
}

$resources = @($state.values.root_module.resources)
function Get-StateResource([string]$Address) {
    $resource = $resources | Where-Object { $_.address -eq $Address } | Select-Object -First 1
    if (-not $resource) { throw "Missing required Terraform state resource: $Address" }
    return $resource.values
}

$mrs = Get-StateResource "huaweicloud_mapreduce_cluster.mrs[0]"
$web = Get-StateResource "huaweicloud_compute_instance.web[0]"
$eip = Get-StateResource "huaweicloud_vpc_eip.web[0]"
$bucket = Get-StateResource "huaweicloud_obs_bucket.lake"
$vpc = Get-StateResource "huaweicloud_vpc.this"
$subnet = Get-StateResource "huaweicloud_vpc_subnet.private"
$securityGroup = Get-StateResource "huaweicloud_networking_secgroup.bigdata"
$dataartsJob = Get-StateResource "huaweicloud_dataarts_factory_job.sat_mrs_orchestration[0]"
$dataartsResource = Get-StateResource "huaweicloud_dataarts_factory_resource.sat_spark_python[0]"
$ruleAddresses = @(
    "huaweicloud_networking_secgroup_rule.egress_ipv4",
    "huaweicloud_networking_secgroup_rule.intra_group",
    "huaweicloud_networking_secgroup_rule.mrs_9022",
    "huaweicloud_networking_secgroup_rule.mrs_trusted_private[0]",
    "huaweicloud_networking_secgroup_rule.ssh_admin[0]",
    "huaweicloud_networking_secgroup_rule.web_http[0]",
    "huaweicloud_networking_secgroup_rule.web_https[0]"
)
$ruleIds = @($ruleAddresses | ForEach-Object { (Get-StateResource $_).id })

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet
$cleanupConfig = [ordered]@{
    expected_date = $ExpectedDate
    region = $env:HUAWEICLOUD_REGION
    project_id = $env:HUAWEICLOUD_PROJECT_ID
    mrs_cluster_id = $mrs.id
    web_server_id = $web.id
    web_eip_id = $eip.id
    obs_bucket = $bucket.bucket
    web_vpc_id = $vpc.id
    web_subnet_id = $subnet.id
    security_group_id = $securityGroup.id
    security_group_rule_ids = $ruleIds
    dataarts_workspace_id = $dataartsJob.workspace_id
    dataarts_job_name = $dataartsJob.name
    dataarts_resource_id = $dataartsResource.id
}
$tfvars = [ordered]@{
    region = $env:HUAWEICLOUD_REGION
    project_id = $env:HUAWEICLOUD_PROJECT_ID
    package_path = $zipPath
    execution_agency_id = $ExecutionAgencyId
    cleanup_config_json = ($cleanupConfig | ConvertTo-Json -Compress -Depth 5)
    trigger_status = $TriggerStatus
}
$tfvarsJson = $tfvars | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText(
    $tfvarsPath,
    $tfvarsJson,
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Cloud cleanup package prepared." -ForegroundColor Green
Write-Host "  package: $zipPath"
Write-Host "  tfvars:  $tfvarsPath"
Write-Host "  trigger: $TriggerStatus"
