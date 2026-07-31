variable "run_id" {
  description = "Local SAT Agentic run id to hand off."
  type        = string
}

variable "project_root" {
  description = "Absolute or relative path to the frontend-min project root."
  type        = string
  default     = "../.."
}

variable "region" {
  description = "Huawei Cloud region id."
  type        = string
  default     = "la-south-2"
}

variable "project_id" {
  description = "Huawei Cloud project id. This is not a secret, but should still be handled carefully."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Target environment label."
  type        = string
  default     = "poc"
}

variable "name_prefix" {
  description = "Naming prefix for future cloud resources."
  type        = string
  default     = "sat-agentic"
}

variable "obs_bucket_name" {
  description = "Approved OBS bucket name for raw, silver, gold, release, and audit layers."
  type        = string
}

variable "vpc_id" {
  description = "Approved VPC id."
  type        = string
  default     = ""
}

variable "private_subnet_id" {
  description = "Approved private subnet id."
  type        = string
  default     = ""
}

variable "security_group_ids" {
  description = "Approved restrictive security group ids."
  type        = list(string)
  default     = []
}

variable "kms_key_id" {
  description = "Approved KMS/DEW key id for OBS and data services."
  type        = string
  default     = ""
}

variable "mrs_cluster_id" {
  description = "Approved MRS Spark cluster id."
  type        = string
  default     = ""
}

variable "dataarts_workspace_id" {
  description = "Approved DataArts workspace id."
  type        = string
  default     = ""
}

variable "dws_connection_name" {
  description = "Approved DataArts or DWS connection name."
  type        = string
  default     = ""
}
