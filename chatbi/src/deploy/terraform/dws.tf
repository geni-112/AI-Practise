resource "huaweicloud_dws_cluster" "chatbi" {
  name              = "${var.project_name}-dws"
  node_type         = var.dws_flavor
  number_of_node    = var.dws_node_count
  vpc_id            = huaweicloud_vpc.chatbi.id
  network_id        = huaweicloud_vpc_subnet.private.id
  security_group_id = huaweicloud_networking_secgroup.dws.id
  availability_zone = data.huaweicloud_availability_zones.az.names[0]
  user_name         = var.dws_username
  user_pwd          = random_password.dws_password.result

  volume {
    type     = "SSD"
    capacity = var.dws_volume_size
  }

  tags = {
    Project = var.project_name
    Role    = "datawarehouse"
  }

  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}
