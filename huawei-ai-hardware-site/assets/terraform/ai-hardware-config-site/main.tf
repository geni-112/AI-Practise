terraform {
  required_version = ">= 1.3.0"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.80.0"
    }
  }
}

provider "huaweicloud" {
  region      = var.region
  access_key  = var.access_key
  secret_key  = var.secret_key
  domain_name = var.domain_name
  auth_url    = var.auth_url
}

data "huaweicloud_availability_zones" "this" {}

data "huaweicloud_compute_flavors" "site" {
  count             = var.ecs_flavor_id == "" ? 1 : 0
  availability_zone = local.selected_az
  performance_type  = var.ecs_performance_type
  cpu_core_count    = var.ecs_cpu_core_count
  memory_size       = var.ecs_memory_size
}

data "huaweicloud_images_image" "site" {
  count       = var.image_id == "" ? 1 : 0
  name        = var.image_name
  most_recent = true
  visibility  = "public"
}

locals {
  selected_az         = var.availability_zone != "" ? var.availability_zone : data.huaweicloud_availability_zones.this.names[0]
  selected_ecs_flavor = var.ecs_flavor_id != "" ? var.ecs_flavor_id : data.huaweicloud_compute_flavors.site[0].ids[0]
  selected_image_id   = var.image_id != "" ? var.image_id : data.huaweicloud_images_image.site[0].id
  site_archive_b64    = filebase64(var.site_archive_path)
  common_tags = merge(
    {
      Project = var.project_name
      Managed = "terraform"
      App     = "ai-hardware-config-site"
    },
    var.tags
  )
}

resource "huaweicloud_vpc" "this" {
  name        = "${var.project_name}-vpc"
  cidr        = var.vpc_cidr
  description = "VPC for AI hardware configuration website."
  tags        = local.common_tags
}

resource "huaweicloud_vpc_subnet" "this" {
  name              = "${var.project_name}-subnet"
  cidr              = var.subnet_cidr
  gateway_ip        = cidrhost(var.subnet_cidr, 1)
  vpc_id            = huaweicloud_vpc.this.id
  availability_zone = local.selected_az
  primary_dns       = var.dns_servers[0]
  secondary_dns     = length(var.dns_servers) > 1 ? var.dns_servers[1] : null
  description       = "Subnet for the public website ECS."
  tags              = local.common_tags
}

resource "huaweicloud_networking_secgroup" "this" {
  name        = "${var.project_name}-sg"
  description = "Security group for AI hardware configuration website."
}

resource "huaweicloud_networking_secgroup_rule" "http" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = huaweicloud_networking_secgroup.this.id
  description       = "Public HTTP access."
}

resource "huaweicloud_networking_secgroup_rule" "https" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = huaweicloud_networking_secgroup.this.id
  description       = "Public HTTPS access, reserved for certificate setup."
}

resource "huaweicloud_networking_secgroup_rule" "ssh" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.admin_cidr
  security_group_id = huaweicloud_networking_secgroup.this.id
  description       = "Restricted SSH administration."
}

resource "huaweicloud_networking_secgroup_rule" "egress_all" {
  direction         = "egress"
  ethertype         = "IPv4"
  security_group_id = huaweicloud_networking_secgroup.this.id
  remote_ip_prefix  = "0.0.0.0/0"
}

resource "huaweicloud_compute_instance" "site" {
  name                        = "${var.project_name}-web"
  image_id                    = local.selected_image_id
  flavor_id                   = local.selected_ecs_flavor
  availability_zone           = local.selected_az
  admin_pass                  = var.admin_password
  security_group_ids          = [huaweicloud_networking_secgroup.this.id]
  system_disk_type            = var.system_disk_type
  system_disk_size            = var.system_disk_size_gb
  eip_type                    = var.eip_type
  delete_eip_on_termination   = true
  delete_disks_on_termination = true
  user_data = templatefile("${path.module}/templates/cloud-init.yaml.tftpl", {
    site_archive_b64 = local.site_archive_b64
  })
  tags = local.common_tags

  network {
    uuid = huaweicloud_vpc_subnet.this.id
  }

  bandwidth {
    share_type  = "PER"
    size        = var.bandwidth_size_mbit
    charge_mode = "traffic"
  }
}

resource "huaweicloud_rds_instance" "mysql" {
  count             = var.create_rds ? 1 : 0
  name              = "${var.project_name}-mysql"
  flavor            = var.rds_flavor
  vpc_id            = huaweicloud_vpc.this.id
  subnet_id         = huaweicloud_vpc_subnet.this.id
  security_group_id = huaweicloud_networking_secgroup.this.id
  availability_zone = [local.selected_az]
  tags              = local.common_tags

  db {
    type     = "MySQL"
    version  = "8.0"
    password = var.rds_admin_password
    port     = 3306
  }

  volume {
    type = var.rds_volume_type
    size = var.rds_volume_size_gb
  }

  backup_strategy {
    start_time = "08:00-09:00"
    keep_days  = 1
  }
}
