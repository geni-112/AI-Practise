variable "region" {
  type = string
}

variable "project_id" {
  type = string
}

variable "function_name" {
  type    = string
  default = "sat-agentic-demo-cleanup"
}

variable "trigger_name" {
  type    = string
  default = "sat-agentic-demo-cleanup-timer"
}

variable "package_path" {
  type = string
}

variable "cleanup_config_json" {
  type = string
}

variable "execution_agency_id" {
  type = string
}

variable "execution_agency_name" {
  type    = string
  default = "serverless-trust"
}

variable "configuration_agency_name" {
  type    = string
  default = "fgs_default_agency"
}

variable "trigger_status" {
  type    = string
  default = "DISABLED"

  validation {
    condition     = contains(["ACTIVE", "DISABLED"], var.trigger_status)
    error_message = "trigger_status must be ACTIVE or DISABLED."
  }
}

variable "cleanup_schedule" {
  type    = string
  default = "CRON_TZ=America/Sao_Paulo 0 0/10 15-17 24 7 *"
}
