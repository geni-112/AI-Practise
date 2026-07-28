param(
    [Parameter(Mandatory = $false)]
    [string]$RunId = "front-11ed357b8f",

    [Parameter(Mandatory = $false)]
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required file: $Path"
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

$runDir = Join-Path $ProjectRoot (Join-Path "generated" $RunId)
$releaseDir = Join-Path $runDir "release"
$preExecutionDir = Join-Path $runDir "pre_execution"
$outDir = Join-Path $ProjectRoot (Join-Path "cloud_execution_blueprint" (Join-Path "out" $RunId))
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$preExecution = Read-JsonFile (Join-Path $preExecutionDir "pre_execution_readiness.json")
$releaseManifest = Read-JsonFile (Join-Path $releaseDir "release_manifest.json")
$cloudParameterMap = Read-JsonFile (Join-Path $releaseDir "cloud_parameter_map.json")

$bindings = $cloudParameterMap.required_bindings.PSObject.Properties | Sort-Object Name
$releaseFiles = @($releaseManifest.files | ForEach-Object { "- {0}: {1}" -f $_.name, $_.path })
$gates = @($preExecution.gates | ForEach-Object { "- {0}: {1} ({2})" -f $_.id, $_.status, $_.summary })

$lines = @()
$lines += "# Huawei Cloud Operator Handoff"
$lines += ""
$lines += "- run_id: $RunId"
$lines += "- generated_at: $((Get-Date).ToUniversalTime().ToString("o"))"
$lines += "- local_release_status: $($releaseManifest.status)"
$lines += "- pre_execution_status: $($preExecution.status)"
$lines += "- ready_for_execution_layer: $($preExecution.ready_for_execution_layer)"
$lines += "- cloud_execution: blocked"
$lines += ""
$lines += "## Gate Evidence"
$lines += ""
$lines += $gates
$lines += ""
$lines += "## Required Cloud Bindings"
$lines += ""
foreach ($binding in $bindings) {
    $lines += "- $($binding.Name): $($binding.Value)"
}
$lines += ""
$lines += "## Release Files"
$lines += ""
$lines += $releaseFiles
$lines += ""
$lines += "## Operator Sequence"
$lines += ""
$lines += "1. Confirm region, project id, VPC, private subnet, security group, KMS key, MRS cluster, DWS connection, and DataArts workspace in Huawei Cloud console."
$lines += "2. Upload the frozen release bundle to the approved OBS release path."
$lines += "3. Import DataArts package as a disabled draft and verify every placeholder binding."
$lines += "4. Keep schedules disabled until PySpark, SQL, DAG, IAM, KMS, and row-count controls are approved."
$lines += "5. After separate execution approval, run MRS Spark and DWS load steps, then write evidence to OBS audit."
$lines += "6. If validation fails, disable schedules, preserve failed outputs, restore the prior serving pointer, and attach the evidence bundle."
$lines += ""
$lines += "## Secret Boundary"
$lines += ""
$lines += "Do not paste AK/SK, database passwords, private keys, or signing material into this package. Use environment variables, Huawei Cloud secret services, or an approved CI/CD secret store."

$handoffPath = Join-Path $outDir "operator_handoff.md"
$lines | Set-Content -LiteralPath $handoffPath -Encoding UTF8

Write-Host ("Operator handoff written: {0}" -f $handoffPath)
