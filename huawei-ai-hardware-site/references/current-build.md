# Current Build Snapshot

This snapshot records the production state from the original build.

## Public Site

```text
http://119.8.152.171
```

Verification performed:

- Homepage returned HTTP 200.
- Homepage contained `AI Hardware Configurator`.
- Dataset endpoint returned HTTP 200.
- Dataset contained `GLM-5.1`.
- Dataset contained `DeepSeek-V4-Flash`.

## Huawei Cloud

- Region: `la-south-2`
- Availability zone: `la-south-2a`
- ECS flavor: `s3.medium.2`
- Image: Ubuntu 22.04 server 64bit
- Image id: `a4605ecc-7558-4d2c-95f7-3a595ec3f876`
- System disk: EVS SSD 40 GB
- EIP bandwidth: 5 Mbit/s, traffic billing
- VPC id: `d8faeb60-36c1-4160-b31d-d2dd8882d6ce`
- Subnet id: `a4f6a6e0-a9e7-4295-a8b3-d99917626218`
- Security group id: `d5c4d0e6-0faa-457f-9afb-a7bbb4efc950`
- RDS: not created

## Nginx

Public server header:

```text
nginx/1.18.0 (Ubuntu)
```

## Files Captured in the Skill

- `assets/site/public/index.html`
- `assets/site/public/styles.css`
- `assets/site/public/dashboard.js`
- `assets/site/data/ai-hardware-config.json`
- `assets/terraform/ai-hardware-config-site/`
- `scripts/package-ai-site.ps1`
- `scripts/deploy-ai-site-huawei.ps1`
- `scripts/publish-ai-site-ssh.ps1`

## Notes

- Temporary AK/SK tfvars and Terraform plan files were deleted after deployment.
- The original SSH CIDR was broad for demo convenience. Restrict it before production.
- The ECS was replaced once to force updated cloud-init content to apply; the public IP remained unchanged.
