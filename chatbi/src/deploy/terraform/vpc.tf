resource "huaweicloud_vpc" "chatbi" {
  name = "${var.project_name}-vpc"
  cidr = "10.0.0.0/16"

  tags = {
    Project = var.project_name
    Env     = "production"
  }
}

resource "huaweicloud_vpc_subnet" "public" {
  name       = "${var.project_name}-subnet-public"
  vpc_id     = huaweicloud_vpc.chatbi.id
  cidr       = "10.0.1.0/24"
  gateway_ip = "10.0.1.1"
  dns_list   = ["100.125.1.250", "8.8.8.8"]
}

resource "huaweicloud_vpc_subnet" "private" {
  name       = "${var.project_name}-subnet-private"
  vpc_id     = huaweicloud_vpc.chatbi.id
  cidr       = "10.0.2.0/24"
  gateway_ip = "10.0.2.1"
  dns_list   = ["100.125.1.250"]
}

resource "huaweicloud_networking_secgroup" "ecs" {
  name        = "${var.project_name}-sg-ecs"
  description = "ChatBI ECS: HTTP/HTTPS/SSH from internet"
}

resource "huaweicloud_networking_secgroup_rule" "ecs_http" {
  security_group_id = huaweicloud_networking_secgroup.ecs.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = "0.0.0.0/0"
  description       = "HTTP public"
}

resource "huaweicloud_networking_secgroup_rule" "ecs_https" {
  security_group_id = huaweicloud_networking_secgroup.ecs.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = "0.0.0.0/0"
  description       = "HTTPS public"
}

resource "huaweicloud_networking_secgroup_rule" "ecs_ssh" {
  security_group_id = huaweicloud_networking_secgroup.ecs.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.allowed_ssh_cidr
  description       = "SSH management"
}

resource "huaweicloud_networking_secgroup" "dws" {
  name        = "${var.project_name}-sg-dws"
  description = "DWS: only accessible from ECS"
}

resource "huaweicloud_networking_secgroup_rule" "dws_from_ecs" {
  security_group_id = huaweicloud_networking_secgroup.dws.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 8000
  port_range_max    = 8000
  remote_group_id   = huaweicloud_networking_secgroup.ecs.id
  description       = "DWS port from ECS only"
}
