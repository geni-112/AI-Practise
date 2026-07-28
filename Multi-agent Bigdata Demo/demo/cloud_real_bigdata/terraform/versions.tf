terraform {
  required_version = ">= 1.5.0"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.94.0"
    }
  }
}

provider "huaweicloud" {
  region     = var.region
  project_id = var.project_id != "" ? var.project_id : null
}
