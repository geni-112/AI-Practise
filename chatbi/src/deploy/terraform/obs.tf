resource "huaweicloud_obs_bucket" "chatbi" {
  bucket        = "${var.project_name}-${var.region}-${substr(md5(var.access_key), 0, 6)}"
  acl           = "private"
  force_destroy = true

  tags = {
    Project = var.project_name
  }
}
