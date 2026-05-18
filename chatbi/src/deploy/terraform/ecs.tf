resource "huaweicloud_vpc_eip" "chatbi" {
  publicip {
    type = "5_bgp"
  }
  bandwidth {
    name        = "${var.project_name}-bandwidth"
    size        = var.eip_bandwidth
    share_type  = "PER"
    charge_mode = "traffic"
  }
}

resource "huaweicloud_compute_eip_associate" "chatbi" {
  public_ip   = huaweicloud_vpc_eip.chatbi.address
  instance_id = huaweicloud_compute_instance.chatbi.id
}

resource "huaweicloud_compute_keypair" "chatbi" {
  name     = "${var.project_name}-keypair"
  key_file = "${path.module}/../chatbi-keypair.pem"
}

resource "huaweicloud_compute_instance" "chatbi" {
  name               = "${var.project_name}-server"
  image_id           = data.huaweicloud_images_image.ubuntu.id
  flavor_id          = var.ecs_flavor
  security_group_ids = [huaweicloud_networking_secgroup.ecs.id]
  availability_zone  = data.huaweicloud_availability_zones.az.names[0]
  key_pair           = huaweicloud_compute_keypair.chatbi.name

  network {
    uuid = huaweicloud_vpc_subnet.public.id
  }

  system_disk_type = "SSD"
  system_disk_size = 100

  data_disks {
    type = "SSD"
    size = 200
  }

  user_data = base64encode(templatefile("${path.module}/templates/cloud-init.sh", {
    dws_host        = huaweicloud_dws_cluster.chatbi.private_ip
    dws_port        = "8000"
    dws_db          = "chatbi"
    dws_username    = var.dws_username
    dws_password    = random_password.dws_password.result
    llm_api_key     = var.maas_api_key
    llm_base_url    = var.maas_base_url
    llm_model       = var.maas_model
    obs_bucket      = huaweicloud_obs_bucket.chatbi.bucket
    obs_region      = var.region
    superset_secret = random_password.superset_secret.result
    project_name    = var.project_name
  }))

  tags = {
    Project = var.project_name
    Role    = "app-server"
  }
}
