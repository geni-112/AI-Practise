variable "region" {
  description = "Huawei Cloud region id."
  type        = string
  default     = "la-south-2"
}

variable "project_id" {
  description = "Huawei Cloud project id. Prefer HW_PROJECT_ID or HUAWEICLOUD_PROJECT_ID in scripts."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment label."
  type        = string
  default     = "poc"
}

variable "name_prefix" {
  description = "Prefix for created resources."
  type        = string
  default     = "sat-agentic"
}

variable "demo_owner" {
  description = "Human owner or team responsible for cleanup and customer-demo operation."
  type        = string
  default     = ""
}

variable "demo_purpose" {
  description = "Purpose tag for audit and cost review."
  type        = string
  default     = "sat-agentic-customer-demo"
}

variable "demo_expires_at" {
  description = "UTC expiration timestamp for the demo environment, for example 2026-07-10T18:00:00Z."
  type        = string
  default     = ""
}

variable "enterprise_project_id" {
  description = "Enterprise project id. Empty means provider default."
  type        = string
  default     = ""
}

variable "availability_zone" {
  description = "Optional AZ name. Empty selects the first available AZ."
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.42.0.0/16"
}

variable "subnet_cidr" {
  description = "Private subnet CIDR."
  type        = string
  default     = "10.42.10.0/24"
}

variable "subnet_gateway_ip" {
  description = "Private subnet gateway IP."
  type        = string
  default     = "10.42.10.1"
}

variable "admin_cidr" {
  description = "CIDR allowed to reach SSH administration. Keep this restricted to an operator IP or VPN."
  type        = string
  default     = "0.0.0.0/0"
}

variable "web_cidr" {
  description = "CIDR allowed to reach the public HTTP/HTTPS demo entry point."
  type        = string
  default     = "0.0.0.0/0"
}

variable "obs_bucket_name" {
  description = "Globally unique OBS bucket name."
  type        = string
}

variable "node_key_pair_name" {
  description = "Existing Huawei Cloud key pair name for MRS/ECS node access."
  type        = string
  default     = ""
}

variable "node_public_key" {
  description = "Optional SSH public key to import as a Terraform-managed key pair for this demo."
  type        = string
  default     = ""
}

variable "mrs_manager_admin_password" {
  description = "MRS Manager admin password. Supply through TF_VAR_mrs_manager_admin_password."
  type        = string
  sensitive   = true
  default     = null
}

variable "enable_mrs" {
  description = "Whether to create the MRS Spark cluster."
  type        = bool
  default     = true
}

variable "mrs_vpc_id" {
  description = "Optional existing VPC for MRS, used when binding to an existing DataArts instance."
  type        = string
  default     = ""
}

variable "mrs_subnet_id" {
  description = "Optional existing subnet for MRS. Must belong to mrs_vpc_id when set."
  type        = string
  default     = ""
}

variable "mrs_trusted_cidr" {
  description = "Optional trusted private CIDR allowed to reach MRS through the demo security group."
  type        = string
  default     = ""
}

variable "mrs_version" {
  description = "MRS version."
  type        = string
  default     = "MRS 3.5.0-LTS"
}

variable "mrs_ecs_default_agency" {
  description = "ECS agency used by MRS components to access OBS without static AK/SK credentials."
  type        = string
  default     = "MRS_ECS_DEFAULT_AGENCY"
}

variable "mrs_components" {
  description = "MRS components for SAT Spark processing."
  type        = list(string)
  default     = ["Hadoop", "Hive", "Spark", "JobGateway"]
}

variable "mrs_master_flavor" {
  description = "MRS master node flavor. Override for the selected region if needed."
  type        = string
  default     = "m6.2xlarge.8.linux.bigdata"
}

variable "mrs_core_flavor" {
  description = "MRS core node flavor. Override for the selected region if needed."
  type        = string
  default     = "m6.2xlarge.8.linux.bigdata"
}

variable "mrs_master_node_count" {
  description = "MRS master node count. la-south-2 currently requires at least two master nodes."
  type        = number
  default     = 2
}

variable "mrs_core_node_count" {
  description = "MRS analysis core node count. la-south-2 currently requires at least three core nodes."
  type        = number
  default     = 3
}

variable "mrs_root_volume_size" {
  description = "MRS root disk size in GB. The tested la-south-2 MRS 3.5.0-LTS baseline uses 480 GB."
  type        = number
  default     = 480
}

variable "mrs_data_volume_size" {
  description = "MRS data disk size in GB. The tested la-south-2 MRS 3.5.0-LTS baseline uses 600 GB."
  type        = number
  default     = 600
}

variable "mrs_volume_type" {
  description = "MRS disk type."
  type        = string
  default     = "SAS"
}

variable "submit_smoke_job" {
  description = "Submit a one-time MRS Spark job after sample artifacts have been uploaded to OBS."
  type        = bool
  default     = false
}

variable "run_id" {
  description = "Run id used for OBS raw/gold/audit paths and smoke job naming."
  type        = string
  default     = "manual"
}

variable "enable_dws" {
  description = "Whether to create GaussDB(DWS) for SQL serving."
  type        = bool
  default     = false
}

variable "dws_admin_user" {
  description = "DWS administrator username."
  type        = string
  default     = "dbadmin"
}

variable "dws_admin_password" {
  description = "DWS admin password. Supply through TF_VAR_dws_admin_password."
  type        = string
  sensitive   = true
  default     = null
}

variable "dws_version" {
  description = "GaussDB(DWS) version."
  type        = string
  default     = "8.2.1"
}

variable "dws_node_type" {
  description = "DWS node type. Override if unavailable in the selected region."
  type        = string
  default     = "dws.m3.xlarge"
}

variable "dws_node_count" {
  description = "DWS node count."
  type        = number
  default     = 3
}

variable "dws_cn_count" {
  description = "DWS coordinator node count."
  type        = number
  default     = 2
}

variable "dws_volume_type" {
  description = "DWS volume type."
  type        = string
  default     = "SSD"
}

variable "dws_volume_capacity" {
  description = "DWS volume capacity in GB."
  type        = number
  default     = 300
}

variable "enable_dataarts" {
  description = "Whether to create a DataArts Studio instance. This is prepaid in the provider."
  type        = bool
  default     = false
}

variable "existing_dataarts_instance_id" {
  description = "Existing DataArts Studio instance to bind without importing or managing its lifecycle."
  type        = string
  default     = ""
}

variable "enable_dataarts_factory_assets" {
  description = "Whether to register the SAT PySpark resource and stopped orchestration job in an existing DataArts workspace."
  type        = bool
  default     = false
}

variable "existing_dataarts_workspace_id" {
  description = "Existing DataArts Studio workspace used for managed Factory assets."
  type        = string
  default     = ""
}

variable "dataarts_version" {
  description = "DataArts Studio version."
  type        = string
  default     = "dayu.starter"
}

variable "dataarts_period_unit" {
  description = "DataArts prepaid period unit."
  type        = string
  default     = "month"
}

variable "dataarts_period" {
  description = "DataArts prepaid period."
  type        = number
  default     = 1
}

variable "enable_web_ecs" {
  description = "Whether to create a small ECS + EIP for the demo web/API host."
  type        = bool
  default     = false
}

variable "web_flavor_id" {
  description = "Optional ECS flavor id. Empty discovers a 2 vCPU / 4 GB normal flavor."
  type        = string
  default     = ""
}

variable "web_image_id" {
  description = "Optional ECS image id."
  type        = string
  default     = ""
}

variable "web_image_name" {
  description = "ECS image name used when web_image_id is empty."
  type        = string
  default     = "Ubuntu 22.04 server 64bit"
}

variable "web_bandwidth_size" {
  description = "Demo EIP bandwidth size in Mbit/s."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default = {
    project = "sat-agentic-real-bigdata"
  }
}
