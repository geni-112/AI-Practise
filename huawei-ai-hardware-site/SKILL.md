---
name: huawei-ai-hardware-site
description: Build, update, or redeploy the Huawei Cloud AI hardware configuration website for Ascend 910B/950DT model-sizing. Use when the user asks for an AI hardware configurator, public-model deployment estimator, Huawei Cloud LA-Santiago website deployment, Terraform automation with AK/SK dialogs, Nginx static hosting, or updates to the bundled model dataset, quantization options, page design, or cloud resource choices.
---

# Huawei AI Hardware Site

## Purpose

Create and operate a static English AI hardware sizing website for Huawei Cloud LA-Santiago. The site estimates whether open-weight LLMs fit on Ascend 910B or 950DT hardware, recommends quantization, and explains memory calculations and public data sources.

## Start Here

Use the bundled assets as the canonical baseline:

- Website template: `assets/site/public/`
- Dataset: `assets/site/data/ai-hardware-config.json`
- Terraform module: `assets/terraform/ai-hardware-config-site/`
- Helper scripts: `scripts/package-ai-site.ps1`, `scripts/deploy-ai-site-huawei.ps1`, `scripts/publish-ai-site-ssh.ps1`

Read only the reference needed for the current task:

- For cloud resources, Nginx, Terraform, AK/SK dialogs, and deployment: `references/deployment.md`
- For model data, quantization versions, source policy, and calculations: `references/dataset-and-calculation.md`
- For page layout, English copy, fonts, and visual design: `references/page-design.md`
- For the exact current production build snapshot: `references/current-build.md`

## Build Workflow

1. Copy or adapt the site assets into the target repo:
   - `assets/site/public/index.html`
   - `assets/site/public/styles.css`
   - `assets/site/public/dashboard.js`
   - `assets/site/data/ai-hardware-config.json`
2. Keep the UI in English and use `Arial, sans-serif`.
3. Preserve the rule that at least three inputs are required, and require both hardware and model before memory sizing.
4. Use the dataset schema in `references/dataset-and-calculation.md`.
5. Validate:
   - `node --check public/dashboard.js`
   - `node -e "JSON.parse(require('fs').readFileSync('data/ai-hardware-config.json','utf8')); console.log('JSON OK')"`
   - `npm run package:ai-site`

## Deployment Workflow

1. Copy or adapt the Terraform module from `assets/terraform/ai-hardware-config-site/`.
2. Package the static site with `scripts/package-ai-site.ps1`.
3. For first deployment or infrastructure changes, use `scripts/deploy-ai-site-huawei.ps1`.
   - It opens a Windows Forms dialog for Access Key, Secret Key, IAM domain, ECS admin password, SSH CIDR, and project name.
   - It writes temporary tfvars under `.local`, runs Terraform, and should clean credential files after use.
4. For content-only updates, prefer `scripts/publish-ai-site-ssh.ps1` if SSH password login is enabled.
   - It opens a Windows Forms password dialog and uploads the new tarball over SSH.
5. After publishing, verify:
   - `Invoke-WebRequest -UseBasicParsing http://<site-ip>/`
   - `Invoke-WebRequest -UseBasicParsing http://<site-ip>/data/ai-hardware-config.json`
   - Match expected strings such as `AI Hardware Configurator`, `GLM-5.1`, and `DeepSeek-V4-Flash`.

## Safety Rules

- Never hard-code AK/SK or admin passwords into committed files.
- Put temporary tfvars and plans in `.local/`; ensure `.local/` is ignored.
- Delete temporary credential files after Terraform apply.
- Keep RDS disabled unless the user explicitly needs saved scenarios, users, or audit history.
- Before production, restrict SSH security group ingress from `0.0.0.0/0` to an office or VPN CIDR.
- Treat 950DT as roadmap data unless Huawei Cloud confirms a purchasable SKU.
- Treat model specs as public-source estimates; if the user asks for latest model facts, verify via web before updating.

## Current Production Facts

The site built by this skill was last deployed to Huawei Cloud LA-Santiago with:

- Region: `la-south-2`
- AZ: `la-south-2a`
- ECS flavor: `s3.medium.2`
- Image: Ubuntu 22.04 server 64bit, image id `a4605ecc-7558-4d2c-95f7-3a595ec3f876`
- System disk: EVS SSD 40 GB
- EIP bandwidth: 5 Mbit/s, traffic billing
- Nginx: `nginx/1.18.0 (Ubuntu)`
- RDS: not created by default

For full details, read `references/current-build.md`.
