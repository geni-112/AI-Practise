# Deployment Reference

## Cloud Resource Choices

Target cloud: Huawei Cloud LA-Santiago.

Default Terraform values:

- `region`: `la-south-2`
- `availability_zone`: empty by default; Terraform selected `la-south-2a`
- `ecs_flavor_id`: empty by default; Terraform queries the smallest available on-demand flavor
- Actual selected ECS flavor in the current deployment: `s3.medium.2`
- Image: Ubuntu 22.04 server 64bit
- Actual image id: `a4605ecc-7558-4d2c-95f7-3a595ec3f876`
- System disk: SSD, 40 GB
- EIP: `5_bgp`, 5 Mbit/s, `charge_mode = traffic`
- VPC CIDR: `10.88.0.0/16`
- Subnet CIDR: `10.88.10.0/24`
- Security group: HTTP 80 open, HTTPS 443 reserved/open, SSH 22 controlled by `admin_cidr`
- RDS: disabled with `create_rds = false`

Why this is minimal:

- The website is static HTML/CSS/JS plus JSON data, hosted by Nginx.
- No database is needed until users need saved scenarios, login, audit history, or multi-user persistence.
- The inference cluster is not hosted on this ECS; the site only estimates AI hardware sizing.

## Nginx

Current public server header:

```text
nginx/1.18.0 (Ubuntu)
```

Cloud-init installs Nginx via Ubuntu apt:

```yaml
package_update: true
packages:
  - nginx
```

Nginx serves:

- Root: `/var/www/ai-hardware-config-site`
- Index: `index.html`
- SPA fallback: `try_files $uri $uri/ /index.html`
- Dataset route: `/data/`

## Terraform Module

Use `assets/terraform/ai-hardware-config-site/`.

Important files:

- `main.tf`: VPC, subnet, security group, ECS, optional RDS
- `variables.tf`: region, AK/SK, image, flavor, disk, EIP, RDS options
- `templates/cloud-init.yaml.tftpl`: Nginx setup and static-site unpacking
- `outputs.tf`: `site_url`, `site_public_ip`, selected AZ/flavor/image, IDs

Terraform queries:

- `huaweicloud_availability_zones`
- `huaweicloud_compute_flavors`
- `huaweicloud_images_image`

The static site is injected into cloud-init with:

```hcl
site_archive_b64 = filebase64(var.site_archive_path)
```

## Dialog-Based Scripts

### `deploy-ai-site-huawei.ps1`

Use for first deployment or infrastructure changes.

It opens a Windows Forms dialog with:

- Access Key
- Secret Key
- IAM Domain Name
- ECS Admin Password
- SSH Admin CIDR
- Project Name

It then:

1. Runs `package-ai-site.ps1`
2. Writes ignored temporary tfvars to `.local/ai-site-deploy.tfvars`
3. Runs `terraform init`
4. Tries 1 vCPU / 2 GB by flavor query
5. Falls back to 2 vCPU / 4 GB by flavor query
6. Falls back to explicit `c6.large.2` and image id when needed
7. Runs `terraform plan` and `terraform apply`
8. Shows the final site URL

Always remove temporary tfvars and plan files after use.

### `publish-ai-site-ssh.ps1`

Use for content-only updates when SSH password login works.

It opens a Windows Forms password dialog, then uses Paramiko to:

1. Upload `deploy/ai-hardware-config-site.tar.gz` to `/tmp/ai-hardware-config-site.tar.gz`
2. Extract to `/var/www/ai-hardware-config-site`
3. Run `nginx -t`
4. Restart Nginx

### `package-ai-site.ps1`

Creates:

```text
deploy/ai-hardware-config-site.tar.gz
```

It includes:

- `public/index.html`
- `public/styles.css`
- `public/dashboard.js`
- `data/ai-hardware-config.json`

## Verification Commands

```powershell
node --check public\dashboard.js
node -e "JSON.parse(require('fs').readFileSync('data/ai-hardware-config.json','utf8')); console.log('JSON OK')"
npm run package:ai-site
terraform -chdir=terraform\ai-hardware-config-site validate
Invoke-WebRequest -UseBasicParsing http://<site-ip>/ -TimeoutSec 30
Invoke-WebRequest -UseBasicParsing http://<site-ip>/data/ai-hardware-config.json -TimeoutSec 30
```
