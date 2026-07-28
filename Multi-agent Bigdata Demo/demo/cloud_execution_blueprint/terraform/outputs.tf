output "cloud_execution_status" {
  description = "This scaffold does not execute cloud workloads."
  value       = "blocked_until_operator_approval"
}

output "release_root" {
  description = "Local release package root."
  value       = local.release_root
}

output "pre_execution_root" {
  description = "Local pre-execution evidence root."
  value       = local.pre_execution_root
}

output "required_release_files" {
  description = "Release files expected before cloud handoff."
  value       = local.required_release_files
}

output "required_pre_execution_files" {
  description = "Pre-execution files expected before cloud handoff."
  value       = local.required_pre_execution_files
}

output "obs_uris" {
  description = "Approved OBS layer URIs to bind in the real execution layer."
  value       = local.obs_uris
}

output "cloud_bindings" {
  description = "Operator-reviewed cloud bindings. This contains no secrets."
  value       = local.cloud_bindings
}
