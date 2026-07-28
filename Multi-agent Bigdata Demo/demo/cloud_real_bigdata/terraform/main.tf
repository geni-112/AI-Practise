data "huaweicloud_availability_zones" "available" {}

data "huaweicloud_compute_flavors" "web" {
  count = var.enable_web_ecs && var.web_flavor_id == "" ? 1 : 0

  availability_zone = local.availability_zone
  performance_type  = "normal"
  cpu_core_count    = 2
  memory_size       = 4
}

data "huaweicloud_images_image" "ubuntu" {
  count = var.enable_web_ecs && var.web_image_id == "" ? 1 : 0

  name        = var.web_image_name
  most_recent = true
}

locals {
  availability_zone = var.availability_zone != "" ? var.availability_zone : data.huaweicloud_availability_zones.available.names[0]
  resource_prefix   = "${var.name_prefix}-${var.environment}"
  common_tags = merge(var.tags, {
    environment     = var.environment
    managed_by      = "terraform"
    system          = "sat-agentic"
    demo_owner      = var.demo_owner != "" ? var.demo_owner : "unset"
    demo_purpose    = var.demo_purpose != "" ? var.demo_purpose : "sat-agentic-customer-demo"
    demo_expires_at = var.demo_expires_at != "" ? var.demo_expires_at : "unset"
  })
  smoke_job_name               = substr(replace("${local.resource_prefix}-${var.run_id}-sat-smoke", "_", "-"), 0, 64)
  web_flavor_id                = var.web_flavor_id != "" ? var.web_flavor_id : try(data.huaweicloud_compute_flavors.web[0].ids[0], "")
  web_image_id                 = var.web_image_id != "" ? var.web_image_id : try(data.huaweicloud_images_image.ubuntu[0].id, "")
  effective_node_key_pair_name = var.node_public_key != "" ? huaweicloud_compute_keypair.demo[0].name : var.node_key_pair_name
}

resource "huaweicloud_compute_keypair" "demo" {
  count = var.node_public_key != "" ? 1 : 0

  name       = var.node_key_pair_name
  public_key = var.node_public_key
}

resource "huaweicloud_vpc" "this" {
  name        = "${local.resource_prefix}-vpc"
  cidr        = var.vpc_cidr
  description = "SAT Agentic real big data VPC."
  tags        = local.common_tags
}

resource "huaweicloud_vpc_subnet" "private" {
  name              = "${local.resource_prefix}-private-subnet"
  cidr              = var.subnet_cidr
  gateway_ip        = var.subnet_gateway_ip
  vpc_id            = huaweicloud_vpc.this.id
  availability_zone = local.availability_zone
  tags              = local.common_tags
}

resource "huaweicloud_networking_secgroup" "bigdata" {
  name                 = "${local.resource_prefix}-bigdata-sg"
  description          = "SAT Agentic OBS/MRS/DWS/DataArts private security group."
  delete_default_rules = true
  tags                 = local.common_tags
}

resource "huaweicloud_networking_secgroup_rule" "egress_ipv4" {
  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "egress"
  ethertype         = "IPv4"
}

resource "huaweicloud_networking_secgroup_rule" "intra_group" {
  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  remote_group_id   = huaweicloud_networking_secgroup.bigdata.id
}

resource "huaweicloud_networking_secgroup_rule" "mrs_9022" {
  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 9022
  port_range_max    = 9022
  remote_ip_prefix  = var.vpc_cidr
}

resource "huaweicloud_networking_secgroup_rule" "mrs_trusted_private" {
  count = var.enable_mrs && var.mrs_trusted_cidr != "" ? 1 : 0

  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  remote_ip_prefix  = var.mrs_trusted_cidr
}

resource "huaweicloud_networking_secgroup_rule" "ssh_admin" {
  count = var.enable_web_ecs || var.node_key_pair_name != "" ? 1 : 0

  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.admin_cidr
}

resource "huaweicloud_networking_secgroup_rule" "web_http" {
  count = var.enable_web_ecs ? 1 : 0

  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = var.web_cidr
}

resource "huaweicloud_networking_secgroup_rule" "web_https" {
  count = var.enable_web_ecs ? 1 : 0

  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = var.web_cidr
}

resource "huaweicloud_obs_bucket" "lake" {
  bucket        = var.obs_bucket_name
  acl           = "private"
  versioning    = true
  force_destroy = true
  tags          = local.common_tags
}

resource "huaweicloud_mapreduce_cluster" "mrs" {
  count = var.enable_mrs ? 1 : 0

  availability_zone      = local.availability_zone
  name                   = "${local.resource_prefix}-mrs"
  version                = var.mrs_version
  type                   = "ANALYSIS"
  component_list         = var.mrs_components
  manager_admin_pass     = var.mrs_manager_admin_password
  node_key_pair          = local.effective_node_key_pair_name != "" ? local.effective_node_key_pair_name : null
  safe_mode              = false
  charging_mode          = "postPaid"
  vpc_id                 = var.mrs_vpc_id != "" ? var.mrs_vpc_id : huaweicloud_vpc.this.id
  subnet_id              = var.mrs_subnet_id != "" ? var.mrs_subnet_id : huaweicloud_vpc_subnet.private.id
  security_group_ids     = [huaweicloud_networking_secgroup.bigdata.id]
  mrs_ecs_default_agency = var.mrs_ecs_default_agency
  tags                   = local.common_tags

  master_nodes {
    flavor            = var.mrs_master_flavor
    node_number       = var.mrs_master_node_count
    root_volume_type  = var.mrs_volume_type
    root_volume_size  = var.mrs_root_volume_size
    data_volume_type  = var.mrs_volume_type
    data_volume_size  = var.mrs_data_volume_size
    data_volume_count = 1
  }

  analysis_core_nodes {
    flavor            = var.mrs_core_flavor
    node_number       = var.mrs_core_node_count
    root_volume_type  = var.mrs_volume_type
    root_volume_size  = var.mrs_root_volume_size
    data_volume_type  = var.mrs_volume_type
    data_volume_size  = var.mrs_data_volume_size
    data_volume_count = 1
  }

  lifecycle {
    ignore_changes = [
      component_list,
      master_nodes,
      analysis_core_nodes,
    ]
  }
}

resource "huaweicloud_mapreduce_job" "sat_smoke" {
  count = var.enable_mrs && var.submit_smoke_job ? 1 : 0

  cluster_id   = huaweicloud_mapreduce_cluster.mrs[0].id
  type         = "SparkSubmit"
  name         = local.smoke_job_name
  program_path = "obs://${var.obs_bucket_name}/scripts/sat_taxpayer_etl.py"
  parameters   = "--raw-path obs://${var.obs_bucket_name}/raw/sat/${var.run_id}/taxpayer_registry.csv --gold-path obs://${var.obs_bucket_name}/gold/sat/${var.run_id}/taxpayer_gold_csv --audit-path obs://${var.obs_bucket_name}/audit/${var.run_id}/mrs_audit.json --iceberg-warehouse obs://${var.obs_bucket_name}/lakehouse/iceberg/sat --iceberg-table tax_gold.taxpayer_regime_year --year 2025"

  depends_on = [huaweicloud_obs_bucket.lake]

  lifecycle {
    ignore_changes = [
      program_parameters,
      service_parameters,
    ]
  }
}

resource "huaweicloud_dws_cluster" "serving" {
  count = var.enable_dws ? 1 : 0

  name              = replace("${local.resource_prefix}-dws", "-", "_")
  version           = var.dws_version
  node_type         = var.dws_node_type
  number_of_node    = var.dws_node_count
  number_of_cn      = var.dws_cn_count
  availability_zone = local.availability_zone
  user_name         = var.dws_admin_user
  user_pwd          = var.dws_admin_password
  vpc_id            = huaweicloud_vpc.this.id
  network_id        = huaweicloud_vpc_subnet.private.id
  security_group_id = huaweicloud_networking_secgroup.bigdata.id
  tags              = local.common_tags

  volume {
    type     = var.dws_volume_type
    capacity = var.dws_volume_capacity
  }
}

resource "huaweicloud_dataarts_studio_instance" "factory" {
  count = var.enable_dataarts ? 1 : 0

  name                  = "${local.resource_prefix}-dataarts"
  version               = var.dataarts_version
  vpc_id                = huaweicloud_vpc.this.id
  subnet_id             = huaweicloud_vpc_subnet.private.id
  security_group_id     = huaweicloud_networking_secgroup.bigdata.id
  availability_zone     = local.availability_zone
  period_unit           = var.dataarts_period_unit
  period                = var.dataarts_period
  auto_renew            = "false"
  enterprise_project_id = var.enterprise_project_id != "" ? var.enterprise_project_id : "0"
  tags                  = local.common_tags
}

resource "huaweicloud_dataarts_factory_resource" "sat_spark_python" {
  count = var.enable_dataarts_factory_assets ? 1 : 0

  workspace_id = var.existing_dataarts_workspace_id
  name         = "sat_taxpayer_etl_py"
  type         = "pyFile"
  location     = "obs://${var.obs_bucket_name}/scripts/sat_taxpayer_etl.py"
  directory    = "/"
  description  = "Agent-generated SAT taxpayer PySpark ETL registered for the public demo."

  depends_on = [huaweicloud_obs_bucket.lake]
}

resource "huaweicloud_dataarts_factory_job" "sat_mrs_orchestration" {
  count = var.enable_dataarts_factory_assets ? 1 : 0

  workspace_id = var.existing_dataarts_workspace_id
  name         = "sat_agentic_mrs_pipeline"
  process_type = "BATCH"
  directory    = "/"
  log_path     = "obs://${var.obs_bucket_name}/logs/dataarts/"

  nodes {
    name               = "record_sat_mrs_execution"
    type               = "OBSManager"
    polling_interval   = 10
    max_execution_time = 30
    retry_times        = 1
    retry_interval     = 60
    fail_policy        = "FAIL"

    location {
      x = 120
      y = 80
    }

    properties {
      name  = "action"
      value = "CREATE_PATH"
    }

    properties {
      name  = "path"
      value = "obs://${var.obs_bucket_name}/audit/${var.run_id}/dataarts_orchestration/"
    }
  }

  schedule {
    type = "CRON"

    cron {
      expression           = "0 0 23 * * ?"
      expression_time_zone = "GMT-3"
      start_time           = "2026-07-21T23:00:00-03:00"
      depend_pre_period    = false
    }
  }

  depends_on = [
    huaweicloud_dataarts_factory_resource.sat_spark_python,
    huaweicloud_mapreduce_cluster.mrs,
  ]

  lifecycle {
    ignore_changes = [
      directory,
      schedule[0].cron[0].start_time,
    ]
  }
}

resource "huaweicloud_compute_instance" "web" {
  count = var.enable_web_ecs ? 1 : 0

  name                        = "${local.resource_prefix}-web"
  image_id                    = local.web_image_id
  flavor_id                   = local.web_flavor_id
  key_pair                    = local.effective_node_key_pair_name != "" ? local.effective_node_key_pair_name : null
  security_group_ids          = [huaweicloud_networking_secgroup.bigdata.id]
  availability_zone           = local.availability_zone
  system_disk_type            = "GPSSD"
  system_disk_size            = 40
  charging_mode               = "postPaid"
  delete_disks_on_termination = true
  user_data                   = file("${path.module}/web-cloud-init.yaml")
  tags                        = local.common_tags

  network {
    uuid = huaweicloud_vpc_subnet.private.id
  }
}

resource "huaweicloud_vpc_eip" "web" {
  count = var.enable_web_ecs ? 1 : 0

  publicip {
    type = "5_bgp"
  }

  bandwidth {
    name        = "${local.resource_prefix}-web-eip"
    size        = var.web_bandwidth_size
    share_type  = "PER"
    charge_mode = "traffic"
  }
}

resource "huaweicloud_compute_eip_associate" "web" {
  count = var.enable_web_ecs ? 1 : 0

  public_ip   = huaweicloud_vpc_eip.web[0].address
  instance_id = huaweicloud_compute_instance.web[0].id
}
