locals {
  release_root       = "${var.project_root}/generated/${var.run_id}/release"
  pre_execution_root = "${var.project_root}/generated/${var.run_id}/pre_execution"

  required_release_files = [
    "release_manifest.json",
    "dataarts_import_package.json",
    "resolved_dataarts_import_package.json",
    "deployment_preflight.json",
    "cloud_parameter_map.json",
    "final_import_manifest.json",
  ]

  required_pre_execution_files = [
    "pre_execution_readiness.json",
    "pre_execution_report.md",
  ]

  obs_uris = {
    raw     = "obs://${var.obs_bucket_name}/raw/sat/"
    silver  = "obs://${var.obs_bucket_name}/silver/sat/"
    gold    = "obs://${var.obs_bucket_name}/gold/sat/"
    release = "obs://${var.obs_bucket_name}/release/${var.run_id}/"
    audit   = "obs://${var.obs_bucket_name}/audit/${var.run_id}/"
  }

  cloud_bindings = {
    region                = var.region
    project_id            = var.project_id
    environment           = var.environment
    name_prefix           = var.name_prefix
    vpc_id                = var.vpc_id
    private_subnet_id     = var.private_subnet_id
    security_group_ids    = var.security_group_ids
    kms_key_id            = var.kms_key_id
    mrs_cluster_id        = var.mrs_cluster_id
    dataarts_workspace_id = var.dataarts_workspace_id
    dws_connection_name   = var.dws_connection_name
    cloud_execution       = "blocked_until_operator_approval"
  }
}
