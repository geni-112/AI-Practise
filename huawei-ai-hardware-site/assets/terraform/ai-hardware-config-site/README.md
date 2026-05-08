# AI Hardware Configuration Site on Huawei Cloud

This Terraform module deploys the static AI hardware configuration website to Huawei Cloud LA-Santiago (`la-south-2`) using on-demand resources.

## Minimum Resource Assessment

| Layer | Minimum recommendation | Billing | Notes |
| --- | --- | --- | --- |
| ECS | Query 1 vCPU / 2 GB first; fallback to 2 vCPU / 4 GB | On-demand | Enough for static Nginx hosting. The deployment script verifies LA-Santiago availability before apply. |
| EVS | 40 GB SSD system disk | On-demand | Stores OS, Nginx, static files, and logs. |
| EIP | 5 Mbit/s, traffic billing | On-demand | Public website access. |
| VPC/Subnet/Security Group | One small VPC and subnet | On-demand where applicable | Opens HTTP/HTTPS publicly and SSH via `admin_cidr`. |
| RDS | Disabled by default; optional MySQL 8.0 `rds.mysql.n1.large.2` candidate | On-demand | Only needed when saved scenarios, accounts, or audit history are added. |

## Deploy

From the repository root:

```powershell
npm run deploy:ai-site:huawei
```

The script opens a local Windows dialog for `access_key`, `secret_key`, `domain_name`, and `admin_password`, writes a temporary ignored tfvars file under `.local`, packages the website, then runs Terraform.

Manual mode is still supported:

```powershell
npm run package:ai-site
cd terraform\ai-hardware-config-site
terraform init
terraform apply -var-file="..\..\.local\ai-site-deploy.tfvars"
```

The output `site_url` is the public URL.

## Production Hardening

- Replace `admin_cidr = "0.0.0.0/0"` with an office/VPN CIDR.
- Add HTTPS through ELB, CDN, or Nginx certificate automation.
- Enable `create_rds = true` only after the application needs persistent multi-user data.
- Reconfirm `image_id`, `ecs_flavor_id`, `rds_flavor`, and AZ availability in LA-Santiago before `apply`.
