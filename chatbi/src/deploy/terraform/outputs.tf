output "ecs_public_ip" {
  description = "Public IP of ChatBI server"
  value       = huaweicloud_vpc_eip.chatbi.address
}

output "ecs_private_ip" {
  description = "Private IP of ChatBI server"
  value       = huaweicloud_compute_instance.chatbi.network[0].fixed_ip_v4
}

output "dws_private_ip" {
  description = "DWS cluster private IP"
  value       = huaweicloud_dws_cluster.chatbi.private_ip
}

output "dws_port" {
  description = "DWS connection port"
  value       = "8000"
}

output "obs_bucket" {
  description = "OBS bucket name"
  value       = huaweicloud_obs_bucket.chatbi.bucket
}

output "chatbi_url" {
  description = "ChatBI application URL"
  value       = "http://${huaweicloud_vpc_eip.chatbi.address}"
}

output "superset_url" {
  description = "Superset BI URL"
  value       = "http://${huaweicloud_vpc_eip.chatbi.address}/superset"
}

output "ssh_command" {
  description = "SSH command to connect to ECS"
  value       = "ssh -i chatbi-keypair.pem ubuntu@${huaweicloud_vpc_eip.chatbi.address}"
}

output "dws_connection_string" {
  description = "DWS psql connection string (password omitted)"
  value       = "psql -h ${huaweicloud_dws_cluster.chatbi.private_ip} -p 8000 -U ${var.dws_username} -d chatbi"
  sensitive   = false
}

output "keypair_file" {
  description = "SSH private key saved to local file"
  value       = "chatbi-keypair.pem (saved to project root by Terraform)"
}
