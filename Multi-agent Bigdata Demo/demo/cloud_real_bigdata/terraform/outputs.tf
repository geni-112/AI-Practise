output "resource_summary" {
  description = "Created or planned real Huawei Cloud resource summary."
  value = {
    region            = var.region
    availability_zone = local.availability_zone
    vpc_id            = huaweicloud_vpc.this.id
    subnet_id         = huaweicloud_vpc_subnet.private.id
    security_group_id = huaweicloud_networking_secgroup.bigdata.id
    obs_bucket        = huaweicloud_obs_bucket.lake.bucket
    mrs_cluster_id    = var.enable_mrs ? huaweicloud_mapreduce_cluster.mrs[0].id : null
    dws_cluster_id    = var.enable_dws ? huaweicloud_dws_cluster.serving[0].id : null
    dataarts_id       = var.enable_dataarts ? huaweicloud_dataarts_studio_instance.factory[0].id : (var.existing_dataarts_instance_id != "" ? var.existing_dataarts_instance_id : null)
    web_public_ip     = var.enable_web_ecs ? huaweicloud_vpc_eip.web[0].address : null
  }
}

output "obs_paths" {
  description = "OBS paths used by the SAT Agentic E2E flow."
  value = {
    raw     = "obs://${var.obs_bucket_name}/raw/sat/${var.run_id}/"
    gold    = "obs://${var.obs_bucket_name}/gold/sat/${var.run_id}/"
    release = "obs://${var.obs_bucket_name}/release/${var.run_id}/"
    audit   = "obs://${var.obs_bucket_name}/audit/${var.run_id}/"
    scripts = "obs://${var.obs_bucket_name}/scripts/"
  }
}

output "mrs_smoke_job_id" {
  description = "One-time MRS Spark smoke job id when submitted."
  value       = var.enable_mrs && var.submit_smoke_job ? huaweicloud_mapreduce_job.sat_smoke[0].id : null
}

output "mrs_smoke_job_name" {
  description = "One-time MRS Spark smoke job name when submitted."
  value       = var.enable_mrs && var.submit_smoke_job ? local.smoke_job_name : null
}

output "dataarts_factory_assets" {
  description = "Managed DataArts Factory resource and stopped orchestration job."
  value = var.enable_dataarts_factory_assets ? {
    workspace_id = var.existing_dataarts_workspace_id
    resource_id  = huaweicloud_dataarts_factory_resource.sat_spark_python[0].id
    job_id       = huaweicloud_dataarts_factory_job.sat_mrs_orchestration[0].id
    job_name     = huaweicloud_dataarts_factory_job.sat_mrs_orchestration[0].name
  } : null
}

output "dws_private_endpoint" {
  description = "Private DWS endpoint information when DWS is enabled."
  value       = var.enable_dws ? huaweicloud_dws_cluster.serving[0].endpoints : null
  sensitive   = true
}
