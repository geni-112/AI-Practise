variable "region" {
  description = "Huawei Cloud region"
  default     = "la-south-2"
}

variable "access_key" {
  description = "Huawei Cloud AK"
  sensitive   = true
}

variable "secret_key" {
  description = "Huawei Cloud SK"
  sensitive   = true
}

variable "project_name" {
  description = "Resource name prefix"
  default     = "chatbi"
}

variable "ecs_flavor" {
  description = "ECS flavor for ChatBI + Superset server"
  default     = "c7.xlarge.4"
}

variable "dws_flavor" {
  description = "DWS node flavor"
  default     = "dws.d2.xlarge.8"
}

variable "dws_node_count" {
  description = "DWS node count (minimum 1 for dev)"
  default     = 1
}

variable "dws_volume_size" {
  description = "DWS storage per node in GB"
  default     = 1024
}

variable "dws_username" {
  description = "DWS admin username"
  default     = "dbadmin"
}

variable "eip_bandwidth" {
  description = "EIP bandwidth in Mbps"
  default     = 5
}

variable "maas_api_key" {
  description = "Huawei Cloud MaaS API Key"
  sensitive   = true
}

variable "maas_base_url" {
  description = "MaaS API base URL"
  default     = "https://api-ap-southeast-1.modelarts-maas.com/openai/v1"
}

variable "maas_model" {
  description = "LLM model name on MaaS"
  default     = "glm-5.1"
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed for SSH access (tighten in production)"
  default     = "0.0.0.0/0"
}
