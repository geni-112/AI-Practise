output "function_urn" {
  value = huaweicloud_fgs_function.cleanup.urn
}

output "trigger_id" {
  value = huaweicloud_fgs_trigger.cleanup.id
}

output "trigger_status" {
  value = var.trigger_status
}

output "schedule" {
  value = var.cleanup_schedule
}
