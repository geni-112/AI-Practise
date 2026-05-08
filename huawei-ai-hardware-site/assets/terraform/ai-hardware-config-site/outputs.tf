output "site_public_ip" {
  description = "Public EIP of the website ECS."
  value       = huaweicloud_compute_instance.site.public_ip
}

output "site_url" {
  description = "HTTP URL for the deployed website."
  value       = "http://${huaweicloud_compute_instance.site.public_ip}"
}

output "selected_availability_zone" {
  description = "Availability zone selected for the deployment."
  value       = local.selected_az
}

output "selected_ecs_flavor" {
  description = "ECS flavor selected for the website."
  value       = local.selected_ecs_flavor
}

output "selected_image_id" {
  description = "Image ID selected for the ECS."
  value       = local.selected_image_id
}

output "vpc_id" {
  description = "VPC ID."
  value       = huaweicloud_vpc.this.id
}

output "subnet_id" {
  description = "Subnet ID."
  value       = huaweicloud_vpc_subnet.this.id
}

output "security_group_id" {
  description = "Security group ID."
  value       = huaweicloud_networking_secgroup.this.id
}

output "rds_instance_id" {
  description = "Optional RDS instance ID."
  value       = var.create_rds ? huaweicloud_rds_instance.mysql[0].id : null
}
