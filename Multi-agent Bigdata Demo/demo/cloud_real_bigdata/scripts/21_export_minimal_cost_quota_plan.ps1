param(
    [string]$ObsBucketName = "",

    [switch]$EnableWebEcs,

    [switch]$EnableDws,

    [switch]$EnableDataArts,

    [switch]$SubmitSmokeJob,

    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

function Get-ConfiguredValue {
    param(
        [string]$Name,
        [string]$DefaultValue = ""
    )
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "User") }
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine") }
    if (-not $value) { $value = $DefaultValue }
    return $value
}

function Get-ConfiguredInt {
    param(
        [string]$Name,
        [int]$DefaultValue
    )
    $value = Get-ConfiguredValue -Name $Name
    $parsed = 0
    if ($value -and [int]::TryParse($value, [ref]$parsed)) {
        return $parsed
    }
    return $DefaultValue
}

function Add-Check {
    param(
        [string]$Id,
        [string]$Status,
        [string]$Detail
    )
    $script:Checks += [ordered]@{
        id = $Id
        status = $Status
        detail = $Detail
    }
}

function New-ResourceItem {
    param(
        [string]$Layer,
        [string]$Service,
        [string]$TerraformResource,
        [string]$DefaultState,
        [string]$BillingExposure,
        [string]$Sizing,
        [string]$Purpose,
        [string]$CustomerDemoNote
    )
    return [ordered]@{
        layer = $Layer
        service = $Service
        terraform_resource = $TerraformResource
        default_state = $DefaultState
        billing_exposure = $BillingExposure
        sizing = $Sizing
        purpose = $Purpose
        customer_demo_note = $CustomerDemoNote
    }
}

function Render-ResourceTable {
    param([array]$Rows)
    $lines = @(
        "| layer | service | default | billing | sizing | purpose |",
        "| --- | --- | --- | --- | --- | --- |"
    )
    foreach ($row in $Rows) {
        $layer = ([string]$row.layer).Replace("|", "\|")
        $service = ([string]$row.service).Replace("|", "\|")
        $default = ([string]$row.default_state).Replace("|", "\|")
        $billing = ([string]$row.billing_exposure).Replace("|", "\|")
        $sizing = ([string]$row.sizing).Replace("|", "\|")
        $purpose = ([string]$row.purpose).Replace("|", "\|")
        $lines += "| $layer | $service | $default | $billing | $sizing | $purpose |"
    }
    return $lines
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..\..")
& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ".cloud_real_bigdata_work\minimal_cost_quota_plan"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$regionDefault = Get-ConfiguredValue -Name "HUAWEICLOUD_REGION" -DefaultValue "la-south-2"
$region = Get-ConfiguredValue -Name "TF_VAR_region" -DefaultValue $regionDefault
$projectConfigured = [bool](Get-ConfiguredValue -Name "HUAWEICLOUD_PROJECT_ID")
if (-not $projectConfigured) { $projectConfigured = [bool](Get-ConfiguredValue -Name "HW_PROJECT_ID") }
if (-not $projectConfigured) { $projectConfigured = [bool](Get-ConfiguredValue -Name "TF_VAR_project_id") }

if (-not $ObsBucketName) {
    $ObsBucketName = Get-ConfiguredValue -Name "TF_VAR_obs_bucket_name"
}
if (-not $ObsBucketName) {
    $ObsBucketName = "<globally-unique-obs-bucket-required-before-apply>"
}

$namePrefix = Get-ConfiguredValue -Name "TF_VAR_name_prefix" -DefaultValue "sat-agentic"
$environment = Get-ConfiguredValue -Name "TF_VAR_environment" -DefaultValue "poc"
$availabilityZone = Get-ConfiguredValue -Name "TF_VAR_availability_zone" -DefaultValue "<first-available-az-from-provider>"
$adminCidr = Get-ConfiguredValue -Name "TF_VAR_admin_cidr" -DefaultValue "0.0.0.0/0"
$vpcCidr = Get-ConfiguredValue -Name "TF_VAR_vpc_cidr" -DefaultValue "10.42.0.0/16"
$subnetCidr = Get-ConfiguredValue -Name "TF_VAR_subnet_cidr" -DefaultValue "10.42.10.0/24"
$mrsVersion = Get-ConfiguredValue -Name "TF_VAR_mrs_version" -DefaultValue "MRS 3.5.0-LTS"
$mrsMasterFlavor = Get-ConfiguredValue -Name "TF_VAR_mrs_master_flavor" -DefaultValue "m6.2xlarge.8.linux.bigdata"
$mrsCoreFlavor = Get-ConfiguredValue -Name "TF_VAR_mrs_core_flavor" -DefaultValue "m6.2xlarge.8.linux.bigdata"
$mrsMasterCount = Get-ConfiguredInt -Name "TF_VAR_mrs_master_node_count" -DefaultValue 2
$mrsCoreCount = Get-ConfiguredInt -Name "TF_VAR_mrs_core_node_count" -DefaultValue 3
$mrsRootVolumeSize = Get-ConfiguredInt -Name "TF_VAR_mrs_root_volume_size" -DefaultValue 480
$mrsDataVolumeSize = Get-ConfiguredInt -Name "TF_VAR_mrs_data_volume_size" -DefaultValue 600
$mrsVolumeType = Get-ConfiguredValue -Name "TF_VAR_mrs_volume_type" -DefaultValue "SAS"
$webFlavorId = Get-ConfiguredValue -Name "TF_VAR_web_flavor_id" -DefaultValue "<auto-discover-2vCPU-4GB-normal>"
$webImageName = Get-ConfiguredValue -Name "TF_VAR_web_image_name" -DefaultValue "Ubuntu 22.04 server 64bit"
$webBandwidthSize = Get-ConfiguredInt -Name "TF_VAR_web_bandwidth_size" -DefaultValue 1
$dwsNodeType = Get-ConfiguredValue -Name "TF_VAR_dws_node_type" -DefaultValue "dws.m3.xlarge"
$dwsNodeCount = Get-ConfiguredInt -Name "TF_VAR_dws_node_count" -DefaultValue 3
$dwsCnCount = Get-ConfiguredInt -Name "TF_VAR_dws_cn_count" -DefaultValue 2
$dwsVolumeCapacity = Get-ConfiguredInt -Name "TF_VAR_dws_volume_capacity" -DefaultValue 300
$dataartsVersion = Get-ConfiguredValue -Name "TF_VAR_dataarts_version" -DefaultValue "dayu.starter"
$dataartsPeriodUnit = Get-ConfiguredValue -Name "TF_VAR_dataarts_period_unit" -DefaultValue "month"
$dataartsPeriod = Get-ConfiguredInt -Name "TF_VAR_dataarts_period" -DefaultValue 1

$script:Checks = @()
Add-Check -Id "NO-CREATE-001" -Status "passed" -Detail "This exporter performs no cloud API calls, no Terraform apply, no OBS upload, and no MRS job submit."

if ($adminCidr -in @("0.0.0.0/0", "::/0")) {
    Add-Check -Id "SECURITY-INGRESS-001" -Status "warning" -Detail "TF_VAR_admin_cidr is $adminCidr. Customer or commercial demos must restrict it to office/VPN/operator CIDR before apply."
}
else {
    Add-Check -Id "SECURITY-INGRESS-001" -Status "passed" -Detail "Admin ingress is restricted to $adminCidr."
}

if ($ObsBucketName -like "<globally-unique-*") {
    Add-Check -Id "OBS-NAME-001" -Status "warning" -Detail "OBS bucket name is still a placeholder; choose a globally unique bucket before preflight/apply."
}
else {
    Add-Check -Id "OBS-NAME-001" -Status "passed" -Detail "OBS bucket name is selected."
}

if (-not $projectConfigured) {
    Add-Check -Id "ACCOUNT-001" -Status "warning" -Detail "Huawei Cloud project is not configured, so live quota and availability cannot be confirmed yet."
}
else {
    Add-Check -Id "ACCOUNT-001" -Status "passed" -Detail "Huawei Cloud project id is configured; value is not printed."
}

if ($EnableDws -and -not (Get-ConfiguredValue -Name "TF_VAR_dws_admin_password")) {
    Add-Check -Id "DWS-SECRET-001" -Status "warning" -Detail "DWS is enabled, but TF_VAR_dws_admin_password is not configured."
}

if ($EnableDataArts) {
    Add-Check -Id "DATAARTS-BILLING-001" -Status "warning" -Detail "DataArts Studio is enabled and Terraform models it as prepaid period=$dataartsPeriod $dataartsPeriodUnit. Confirm quota and price before apply."
}

$resources = @()
$resources += New-ResourceItem -Layer "network" -Service "VPC" -TerraformResource "huaweicloud_vpc.this" -DefaultState "created" -BillingExposure "usually no direct compute charge" -Sizing "$vpcCidr" -Purpose "Private boundary for MRS, ECS, DWS, and DataArts." -CustomerDemoNote "Required for real E2E."
$resources += New-ResourceItem -Layer "network" -Service "VPC subnet" -TerraformResource "huaweicloud_vpc_subnet.private" -DefaultState "created" -BillingExposure "usually no direct compute charge" -Sizing "$subnetCidr in $availabilityZone" -Purpose "Private data subnet." -CustomerDemoNote "Required for real E2E."
$resources += New-ResourceItem -Layer "security" -Service "Security group" -TerraformResource "huaweicloud_networking_secgroup.bigdata" -DefaultState "created" -BillingExposure "usually no direct compute charge" -Sizing "egress + intra-group + MRS 9022 + optional SSH/HTTP/HTTPS" -Purpose "Restrict data-plane access." -CustomerDemoNote "Admin CIDR must be restricted for customer/commercial use."
$resources += New-ResourceItem -Layer "lake" -Service "OBS bucket" -TerraformResource "huaweicloud_obs_bucket.lake" -DefaultState "created" -BillingExposure "paid storage, request, and traffic usage" -Sizing "private, versioning enabled, bucket=$ObsBucketName" -Purpose "raw/silver/gold/release/audit evidence lake." -CustomerDemoNote "Required for prompt package, raw sample, Spark script, and gold result."
$resources += New-ResourceItem -Layer "compute" -Service "MRS Spark" -TerraformResource "huaweicloud_mapreduce_cluster.mrs" -DefaultState "enabled" -BillingExposure "postPaid compute and disk charges while cluster exists" -Sizing "$mrsVersion; master $mrsMasterCount x $mrsMasterFlavor; core $mrsCoreCount x $mrsCoreFlavor; root ${mrsRootVolumeSize}GB; data ${mrsDataVolumeSize}GB $mrsVolumeType" -Purpose "Run reviewed PySpark on Huawei Cloud, not local DuckDB." -CustomerDemoNote "Required for real processing evidence."
$resources += New-ResourceItem -Layer "execution" -Service "MRS Spark job" -TerraformResource "huaweicloud_mapreduce_job.sat_smoke" -DefaultState "$(if ($SubmitSmokeJob) { 'submitted during apply' } else { 'submitted by E2E wrapper after upload' })" -BillingExposure "uses the running MRS cluster" -Sizing "SparkSubmit sat_taxpayer_etl.py" -Purpose "Transform raw SAT-like CSV into gold output and audit JSON." -CustomerDemoNote "Required for E2E proof."

if ($EnableWebEcs) {
    $resources += New-ResourceItem -Layer "frontend" -Service "ECS web host" -TerraformResource "huaweicloud_compute_instance.web" -DefaultState "enabled" -BillingExposure "postPaid ECS + 40GB GPSSD system disk" -Sizing "$webFlavorId; image=$webImageName" -Purpose "Host FastAPI/Nginx demo site on cloud resources." -CustomerDemoNote "Recommended for customer demo URL."
    $resources += New-ResourceItem -Layer "frontend" -Service "EIP" -TerraformResource "huaweicloud_vpc_eip.web" -DefaultState "enabled" -BillingExposure "traffic charge; bandwidth size ${webBandwidthSize}Mbit/s" -Sizing "5_bgp, PER bandwidth, traffic charging" -Purpose "Expose demo website to approved admin/customer CIDR." -CustomerDemoNote "Keep CIDR restricted; add HTTPS/domain for commercial."
}
else {
    $resources += New-ResourceItem -Layer "frontend" -Service "ECS web host + EIP" -TerraformResource "huaweicloud_compute_instance.web, huaweicloud_vpc_eip.web" -DefaultState "disabled by default" -BillingExposure "none until -EnableWebEcs" -Sizing "optional smallest web host" -Purpose "Cloud-hosted website/API." -CustomerDemoNote "Enable for a customer-visible cloud URL."
}

if ($EnableDws) {
    $resources += New-ResourceItem -Layer "serving" -Service "GaussDB(DWS)" -TerraformResource "huaweicloud_dws_cluster.serving" -DefaultState "enabled" -BillingExposure "paid DWS cluster and storage" -Sizing "$dwsNodeCount x $dwsNodeType; CN=$dwsCnCount; volume=${dwsVolumeCapacity}GB" -Purpose "SQL/BI serving layer for curated gold data." -CustomerDemoNote "POC sizing only; do not claim production sizing until performance test."
}
else {
    $resources += New-ResourceItem -Layer "serving" -Service "GaussDB(DWS)" -TerraformResource "huaweicloud_dws_cluster.serving" -DefaultState "disabled by default" -BillingExposure "none until -EnableDws" -Sizing "$dwsNodeCount x $dwsNodeType if enabled" -Purpose "Optional SQL/BI serving layer." -CustomerDemoNote "Keep off for minimal E2E unless SQL serving is required."
}

if ($EnableDataArts) {
    $resources += New-ResourceItem -Layer "workflow" -Service "DataArts Studio" -TerraformResource "huaweicloud_dataarts_studio_instance.factory" -DefaultState "enabled" -BillingExposure "prepaid in Terraform provider" -Sizing "$dataartsVersion for $dataartsPeriod $dataartsPeriodUnit" -Purpose "Managed workflow/orchestration." -CustomerDemoNote "Confirm single-instance quota and price before enabling."
}
else {
    $resources += New-ResourceItem -Layer "workflow" -Service "DataArts Studio" -TerraformResource "huaweicloud_dataarts_studio_instance.factory" -DefaultState "disabled by default" -BillingExposure "none until -EnableDataArts" -Sizing "$dataartsVersion if enabled" -Purpose "Optional managed orchestration after MRS path is proven." -CustomerDemoNote "Keep off for minimum paid footprint."
}

$warningCount = @($script:Checks | Where-Object { $_.status -eq "warning" }).Count
$failedCount = @($script:Checks | Where-Object { $_.status -eq "failed" }).Count
$status = if ($failedCount -gt 0) {
    "failed"
}
elseif ($warningCount -gt 0) {
    "review_required"
}
else {
    "ready_for_operator_review"
}

$quotaChecks = @(
    [ordered]@{ service = "OBS"; item = "bucket name availability and storage/request budget"; confirmed = $false },
    [ordered]@{ service = "MRS"; item = "version, AZ, master/core flavors, node quota, EVS disk quota"; confirmed = $false },
    [ordered]@{ service = "ECS/EIP"; item = "2vCPU/4GB flavor, Ubuntu image, EIP quota, outbound package policy"; confirmed = $false },
    [ordered]@{ service = "DWS"; item = "DWS node type/count/CN quota, only if -EnableDws"; confirmed = $false },
    [ordered]@{ service = "DataArts"; item = "Starter instance availability and one-instance-per-project behavior, only if -EnableDataArts"; confirmed = $false }
)

$commercialHardening = @(
    "Use IAM least-privilege roles and separate read-only/provisioner/operator identities.",
    "Keep TF_VAR_admin_cidr restricted; add HTTPS domain, certificate, and WAF/ELB before public commercial access.",
    "Use KMS/DEW-managed keys for production data encryption and rotate secrets outside generated artifacts.",
    "Add Cloud Eye/AOM alerts for MRS job failure, OBS growth, ECS health, and error-count spikes.",
    "Replace POC DWS sizing with benchmarked production sizing before commercial SLA claims.",
    "Keep destroy/cleanup ownership and expiration tags enforced for every customer demo."
)

$report = [ordered]@{
    status = $status
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    values_printed = $false
    creates_resources = $false
    uploads_obs_objects = $false
    submits_mrs_job = $false
    network_calls = 0
    write_calls = 0
    minimum_mode = if ($EnableWebEcs) { "obs_mrs_web_ecs" } else { "obs_mrs_local_or_existing_web" }
    account_context = [ordered]@{
        region = $region
        project_id_configured = $projectConfigured
        availability_zone = $availabilityZone
        name_prefix = $namePrefix
        environment = $environment
    }
    secret_presence = [ordered]@{
        huawei_ak_configured = [bool](Get-ConfiguredValue -Name "HUAWEICLOUD_ACCESS_KEY")
        huawei_sk_configured = [bool](Get-ConfiguredValue -Name "HUAWEICLOUD_SECRET_KEY")
        mrs_manager_password_configured = [bool](Get-ConfiguredValue -Name "TF_VAR_mrs_manager_admin_password")
        dws_admin_password_configured = [bool](Get-ConfiguredValue -Name "TF_VAR_dws_admin_password")
        node_key_pair_configured = [bool](Get-ConfiguredValue -Name "TF_VAR_node_key_pair_name")
    }
    options = [ordered]@{
        obs_bucket_name = $ObsBucketName
        admin_cidr = $adminCidr
        enable_web_ecs = [bool]$EnableWebEcs
        enable_dws = [bool]$EnableDws
        enable_dataarts = [bool]$EnableDataArts
        submit_smoke_job = [bool]$SubmitSmokeJob
    }
    resource_plan = $resources
    quota_checks_required = $quotaChecks
    pricing_checks_required = @(
        "Confirm current pay-per-use price for OBS storage/requests/traffic in $region.",
        "Confirm current MRS postPaid cluster price for $mrsMasterFlavor and $mrsCoreFlavor in $region/$availabilityZone.",
        "Confirm ECS/EIP traffic price when -EnableWebEcs is used.",
        "Confirm DWS price when -EnableDws is used.",
        "Confirm DataArts prepaid price before -EnableDataArts because provider uses period billing."
    )
    customer_demo_boundary = [ordered]@{
        can_demo_after_this_report = $false
        reason = "This is only a no-create planning artifact. Customer demo requires real MRS success, gold evidence, web diagnostics, strict final audit, and handoff export."
        minimal_customer_demo_target = "Prompt package and raw sample in OBS, MRS Spark gold output, FastAPI evidence page on ECS/EIP."
    }
    commercial_hardening_required = $commercialHardening
    checks = $script:Checks
    next_action = if ($status -eq "failed") {
        "Fix failed plan checks, then rerun 21_export_minimal_cost_quota_plan.ps1."
    }
    elseif (-not $projectConfigured) {
        ".\cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1 -ConfigureCredentials -PersistUserEnv -SetGuardDefaults -DetectAdminCidr -EnableWebEcs -RunTerraformPreflight"
    }
    else {
        ".\cloud_real_bigdata\scripts\15_pre_apply_readiness.ps1 -EnableWebEcs -RunReadonlyCloudProbe -RunTerraformPreflight"
    }
}

$jsonPath = Join-Path $OutputDir "minimal_cost_quota_plan_latest.json"
$mdPath = Join-Path $OutputDir "minimal_cost_quota_plan.md"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = @(
    "# SAT Agentic Minimal Cost And Quota Plan",
    "",
    "- status: $($report.status)",
    "- generated_at: $($report.generated_at)",
    "- creates_resources: false",
    "- uploads_obs_objects: false",
    "- submits_mrs_job: false",
    "- network_calls: 0",
    "- write_calls: 0",
    "- minimum_mode: $($report.minimum_mode)",
    "- region: $($report.account_context.region)",
    "- project_id_configured: $($report.account_context.project_id_configured)",
    "- obs_bucket_name: $($report.options.obs_bucket_name)",
    "- admin_cidr: $($report.options.admin_cidr)",
    "",
    "## Resource Plan",
    ""
)
$lines += Render-ResourceTable $resources
$lines += @(
    "",
    "## Checks",
    "",
    "| status | id | detail |",
    "| --- | --- | --- |"
)
foreach ($check in $script:Checks) {
    $detail = ([string]$check.detail).Replace("|", "\|")
    $lines += "| $($check.status) | $($check.id) | $detail |"
}
$lines += @(
    "",
    "## Quota And Price Confirmation Required",
    "",
    "This report does not call live Huawei Cloud quota or pricing APIs. Confirm exact service availability, quota, flavors, and current price in the target account/region before paid apply.",
    "",
    "## Commercial Hardening",
    ""
)
foreach ($item in $commercialHardening) {
    $lines += "- $item"
}
$lines += @(
    "",
    "## Next Action",
    "",
    '```powershell',
    $report.next_action,
    '```'
)
$lines | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host "Minimal cost/quota plan status: $($report.status)" -ForegroundColor ($(if ($report.status -eq "failed") { "Red" } elseif ($report.status -eq "review_required") { "Yellow" } else { "Green" }))
Write-Host "Plan JSON: $jsonPath"
Write-Host "Plan report: $mdPath"
Write-Host "No cloud APIs were called, no resources were created, no OBS objects were uploaded, and no MRS jobs were submitted."

if ($status -eq "failed") {
    throw "Minimal cost/quota plan failed. $($report.next_action)"
}
