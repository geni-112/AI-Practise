param(
    [string]$EnvFile = "",

    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$allowedNames = @(
    "HUAWEICLOUD_ACCOUNT_NAME",
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_SECURITY_TOKEN",
    "HUAWEICLOUD_CREDENTIAL_EXPIRES_AT",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "HW_ACCESS_KEY",
    "HW_SECRET_KEY",
    "HW_SECURITY_TOKEN",
    "HW_REGION_NAME",
    "HW_PROJECT_ID",
    "TF_VAR_mrs_manager_admin_password",
    "TF_VAR_node_key_pair_name",
    "TF_VAR_dws_admin_password",
    "TF_VAR_admin_cidr",
    "TF_VAR_web_cidr",
    "TF_VAR_name_prefix",
    "TF_VAR_environment",
    "TF_VAR_demo_owner",
    "TF_VAR_demo_purpose",
    "TF_VAR_demo_domain",
    "TF_VAR_demo_expires_at",
    "TF_VAR_availability_zone",
    "TF_VAR_obs_bucket_name",
    "TF_VAR_mrs_master_flavor",
    "TF_VAR_mrs_core_flavor",
    "TF_VAR_web_flavor_id",
    "TF_VAR_web_image_id",
    "TF_VAR_web_image_name",
    "TF_VAR_region",
    "TF_VAR_project_id",
    "TF_VAR_vpc_cidr",
    "TF_VAR_subnet_cidr",
    "TF_VAR_subnet_gateway_ip",
    "TF_VAR_mrs_version",
    "TF_VAR_mrs_vpc_id",
    "TF_VAR_mrs_subnet_id",
    "TF_VAR_mrs_trusted_cidr",
    "TF_VAR_enable_mrs",
    "TF_VAR_enable_dws",
    "TF_VAR_enable_dataarts",
    "TF_VAR_enable_web_ecs",
    "TF_VAR_submit_smoke_job",
    "TF_VAR_run_id",
    "TF_VAR_mrs_master_node_count",
    "TF_VAR_mrs_core_node_count",
    "TF_VAR_mrs_root_volume_size",
    "TF_VAR_mrs_data_volume_size",
    "TF_VAR_mrs_volume_type",
    "TF_VAR_web_bandwidth_size",
    "TF_VAR_dws_node_type",
    "TF_VAR_dws_node_count",
    "TF_VAR_dws_cn_count",
    "TF_VAR_dws_volume_capacity",
    "TF_VAR_dataarts_version",
    "TF_VAR_dataarts_period_unit",
    "TF_VAR_dataarts_period",
    "TF_VAR_existing_dataarts_instance_id",
    "TF_VAR_enable_dataarts_factory_assets",
    "TF_VAR_existing_dataarts_workspace_id"
)

function Write-EnvStatus {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )
    if (-not $Quiet) {
        Write-Host $Message -ForegroundColor $Color
    }
}

function Unquote-EnvValue {
    param([string]$Value)
    $trimmed = $Value.Trim()
    if (($trimmed.StartsWith('"') -and $trimmed.EndsWith('"')) -or ($trimmed.StartsWith("'") -and $trimmed.EndsWith("'"))) {
        return $trimmed.Substring(1, $trimmed.Length - 2)
    }
    return $trimmed
}

function Set-EnvIfAllowed {
    param(
        [string]$Name,
        [string]$Value
    )
    if ($allowedNames -notcontains $Name) {
        Write-EnvStatus "  skipped: $Name is not in the allowlist" Yellow
        return
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    Write-EnvStatus "  loaded: $Name=<set>"
}

function Mirror-HuaweiEnv {
    if ($env:HUAWEICLOUD_ACCESS_KEY -and -not $env:HW_ACCESS_KEY) { $env:HW_ACCESS_KEY = $env:HUAWEICLOUD_ACCESS_KEY }
    if ($env:HUAWEICLOUD_SECRET_KEY -and -not $env:HW_SECRET_KEY) { $env:HW_SECRET_KEY = $env:HUAWEICLOUD_SECRET_KEY }
    if ($env:HUAWEICLOUD_SECURITY_TOKEN -and -not $env:HW_SECURITY_TOKEN) { $env:HW_SECURITY_TOKEN = $env:HUAWEICLOUD_SECURITY_TOKEN }
    if ($env:HUAWEICLOUD_REGION -and -not $env:HW_REGION_NAME) { $env:HW_REGION_NAME = $env:HUAWEICLOUD_REGION }
    if ($env:HUAWEICLOUD_PROJECT_ID -and -not $env:HW_PROJECT_ID) { $env:HW_PROJECT_ID = $env:HUAWEICLOUD_PROJECT_ID }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
if (-not $EnvFile) {
    $EnvFile = Join-Path $root ".env.local"
}

if (Test-Path -LiteralPath $EnvFile) {
    Write-EnvStatus "Loading local environment from $EnvFile" Cyan
    $lines = Get-Content -LiteralPath $EnvFile
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $match = [regex]::Match($trimmed, "^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
        if (-not $match.Success) {
            Write-EnvStatus "  skipped: malformed line" Yellow
            continue
        }
        $name = $match.Groups[1].Value
        $value = Unquote-EnvValue $match.Groups[2].Value
        Set-EnvIfAllowed -Name $name -Value $value
    }
}
else {
    Write-EnvStatus "No .env.local found; using current process/user/machine environment." DarkGray
}

Mirror-HuaweiEnv
