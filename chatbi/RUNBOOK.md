# ChatBI on Huawei Cloud — Operations Runbook

> Region: **la-south-2 (Santiago)**  
> Last validated: 2026-05-17 (Terraform plan: 19 resources, 0 errors)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Sandbox Environment (Local)](#3-sandbox-environment-local)
4. [Credential Management](#4-credential-management)
5. [Production Deployment](#5-production-deployment)
6. [Post-Deployment Verification](#6-post-deployment-verification)
7. [Application URLs & Access](#7-application-urls--access)
8. [Day-2 Operations](#8-day-2-operations)
9. [Teardown](#9-teardown)
10. [Troubleshooting](#10-troubleshooting)
11. [Security Reference](#11-security-reference)

---

## 1. Architecture Overview

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  EIP (public IP, 5 Mbps)                                │
│  Huawei Cloud la-south-2                                │
│                                                         │
│  VPC 10.0.0.0/16                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Public Subnet 10.0.1.0/24                       │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  ECS c7.xlarge.4 (4 vCPU / 16 GB RAM)     │  │   │
│  │  │  Ubuntu 22.04  100 GB sys + 200 GB data    │  │   │
│  │  │                                            │  │   │
│  │  │  Nginx :80  ──► /        → frontend dist  │  │   │
│  │  │               ──► /api/  → backend :8001  │  │   │
│  │  │               ──► /superset/ → Superset :8088 │  │
│  │  │                                            │  │   │
│  │  │  Docker Compose:                           │  │   │
│  │  │    chatbi-backend  (FastAPI / Python 3.12) │  │   │
│  │  │    chatbi-superset (Apache Superset 4.0.2) │  │   │
│  │  └─────────────────┬──────────────────────────┘  │   │
│  └────────────────────│─────────────────────────────┘   │
│                       │ psycopg2 port 8000               │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │  Private Subnet 10.0.2.0/24                      │   │
│  │  GaussDB DWS dws.d2.xlarge.8 (1 node, 1 TB SSD) │   │
│  │  Port 8000 — accessible from ECS SG only         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  OBS Bucket: chatbi-* (model artifacts, exports)        │
└─────────────────────────────────────────────────────────┘

LLM: Huawei Cloud MaaS (ap-southeast-1)
     model: glm-5.1  endpoint: modelarts-maas.com/openai/v1
```

### Component Summary

| Component | Spec | Purpose |
|-----------|------|---------|
| ECS | c7.xlarge.4 (4C/16G) | App server: Nginx + Docker |
| DWS | dws.d2.xlarge.8 (1 node) | GaussDB data warehouse (PostgreSQL-compatible) |
| EIP | 5 Mbps | Public internet access |
| OBS | Standard | Artifact storage, exports |
| MaaS | glm-5.1 | NL→SQL LLM (OpenAI-compatible API) |

---

## 2. Prerequisites

### Local Machine

| Tool | Version | Check |
|------|---------|-------|
| Terraform | ≥ 1.5.0 | `terraform -version` |
| Python | ≥ 3.10 | `python --version` |
| Node.js | ≥ 18 | `node --version` |
| Git | any | `git --version` |
| SSH client | any | `ssh -V` |

### Accounts & Keys

- Huawei Cloud account with IAM permissions for ECS, VPC, DWS, OBS, EIP
- AK/SK (Access Key / Secret Key) — IAM → Security Credentials → Access Keys
- MaaS API key — MaaS Console → API Keys

---

## 3. Sandbox Environment (Local)

The sandbox runs entirely on your laptop using DuckDB (no cloud required).

### Start

```bat
cd C:\Users\Matebook\Projects\chatbi-sandbox
start.bat
```

This will:
1. Verify `.env` is configured (prompts you to fill in `LLM_API_KEY` if placeholder)
2. Install Python dependencies
3. Generate `backend/data/retail.duckdb` (100k orders) if not present
4. Start backend on `http://localhost:8000`
5. Start frontend on `http://localhost:5173`
6. Open browser automatically

### Stop

Close the two CMD windows opened by `start.bat`.

### Configuration

File: `C:\Users\Matebook\Projects\chatbi-sandbox\.env`

```env
LLM_API_KEY=<your MaaS API key>
LLM_BASE_URL=https://api-ap-southeast-1.modelarts-maas.com/openai/v1
LLM_MODEL=glm-5.1
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

### Example Questions (Retail Demo Data)

- 按品类统计2024年的销售总额
- 最近6个月每月的订单量趋势
- 哪些省份的客户贡献了最多GMV？
- A类客户的平均客单价是多少？

---

## 4. Credential Management

Credentials are stored locally (never committed to git):

**File:** `C:\Users\Matebook\.claude\huawei-chatbi\credentials.env`

```bash
HW_CONSOLE_ACCOUNT=<console login account>
HW_CONSOLE_PASSWORD=<console password>
HW_ACCESS_KEY=<AK>
HW_SECRET_KEY=<SK>
HW_REGION=la-south-2
MAAS_API_KEY=<MaaS API key>
MAAS_BASE_URL=https://api-ap-southeast-1.modelarts-maas.com/openai/v1
MAAS_MODEL=glm-5.1
ECS_FLAVOR=c7.xlarge.4
DWS_FLAVOR=dws.d2.xlarge.8
EIP_BANDWIDTH=5
```

### Reconfigure credentials

```
/huawei-chatbi configure
```

This triggers an interactive credential collection flow and rewrites the file.

### How credentials flow into Terraform

The `/huawei-chatbi plan` and `apply` commands read `credentials.env` and write `terraform/terraform.tfvars` (gitignored). The Terraform provider uses `access_key` and `secret_key` directly — no environment variables needed.

---

## 5. Production Deployment

### Step 1 — Configure credentials

```
/huawei-chatbi configure
```

Provide AK, SK, MaaS API key when prompted. Region defaults to `la-south-2`.

### Step 2 — Plan (dry run)

```
/huawei-chatbi plan
```

Or manually:

```bash
cd C:\Users\Matebook\Projects\chatbi-huawei-deploy

# Windows CMD
set CHECKPOINT_DISABLE=1
terraform -chdir=terraform init -upgrade
terraform -chdir=terraform plan -out=tfplan
```

Expected output: **19 resources to add, 0 to change, 0 to destroy**

Resources created:
- `huaweicloud_vpc.chatbi`
- `huaweicloud_vpc_subnet.public` / `.private`
- `huaweicloud_networking_secgroup.ecs` / `.dws` + 4 rules
- `huaweicloud_vpc_eip.chatbi`
- `huaweicloud_compute_keypair.chatbi` → writes `chatbi-keypair.pem`
- `huaweicloud_compute_instance.chatbi` (cloud-init runs on first boot)
- `huaweicloud_dws_cluster.chatbi` (takes ~45 minutes)
- `huaweicloud_obs_bucket.chatbi`
- `random_password.dws_password` / `superset_secret`

### Step 3 — Apply

```
/huawei-chatbi apply
```

Or manually:

```bash
set CHECKPOINT_DISABLE=1
terraform -chdir=terraform apply tfplan
```

**Expected duration:** 50–70 minutes (DWS cluster creation dominates).

After completion, Terraform prints all outputs including public IP and URLs.

### Step 4 — Retrieve SSH Key

The SSH private key is automatically written to the project root during `terraform apply`:

```
C:\Users\Matebook\Projects\chatbi-huawei-deploy\chatbi-keypair.pem
```

On Linux/Mac, set permissions:
```bash
chmod 600 chatbi-keypair.pem
```

On Windows, restrict file permissions via Properties → Security → only your user account.

### Step 5 — Wait for cloud-init

The ECS instance runs a cloud-init script on first boot. Full setup takes 10–15 minutes after ECS is `ACTIVE`.

Track progress:
```bash
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP> "tail -f /var/log/cloud-init-chatbi.log"
```

Success indicator at end of log:
```
=== ChatBI Cloud-Init Completed: <timestamp> ===
```

### Step 6 — Initialize DWS Database

After DWS is up, connect from your local machine via the ECS as a jump host, or SSH into ECS and run:

```bash
# SSH into ECS first
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>

# From ECS, connect to DWS (get DWS_HOST from terraform output)
psql -h <DWS_PRIVATE_IP> -p 8000 -U dbadmin -d gaussdb

# Create database
CREATE DATABASE chatbi;
\c chatbi

# Create schema (copy from sandbox)
-- orders, products, customers, regions tables
-- See: C:\Users\Matebook\Projects\chatbi-sandbox\backend\data\seed.py for schema
```

For demo purposes, you can export the sandbox DuckDB data to CSV and import to DWS:

```bash
# On local machine — export from DuckDB
python -c "
import duckdb
conn = duckdb.connect('backend/data/retail.duckdb')
for t in ['orders','products','customers','regions']:
    conn.execute(f'COPY {t} TO \"{t}.csv\" (HEADER, DELIMITER \",\")')
print('Exported 4 tables')
"

# Upload to OBS
# Then on ECS: download from OBS and psql COPY INTO DWS
```

### Step 7 — Deploy Frontend

The cloud-init creates `/opt/chatbi/frontend/dist` as a placeholder. Build and push the production frontend:

```bash
# On local machine
cd C:\Users\Matebook\Projects\chatbi-sandbox\frontend
npm run build     # outputs to dist/

# SCP to ECS
scp -i chatbi-keypair.pem -r dist/ ubuntu@<ECS_PUBLIC_IP>:/opt/chatbi/frontend/dist/
```

After upload, Nginx serves the static files immediately (no restart needed).

---

## 6. Post-Deployment Verification

### Health checks

```bash
# Backend API
curl http://<ECS_PUBLIC_IP>/api/health
# Expected: {"status":"ok","mode":"production-dws"}

# Superset
curl -I http://<ECS_PUBLIC_IP>/superset/
# Expected: HTTP 200 or 302 redirect to login

# Docker container status (from ECS)
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>
docker ps
# chatbi-backend and chatbi-superset should show "Up" and "(healthy)"
```

### Terraform outputs

```bash
terraform -chdir=terraform output
```

| Output | Description |
|--------|-------------|
| `ecs_public_ip` | ECS floating IP |
| `ecs_private_ip` | ECS internal IP (10.0.1.x) |
| `dws_private_ip` | DWS cluster IP (10.0.2.x) |
| `chatbi_url` | `http://<public_ip>` |
| `superset_url` | `http://<public_ip>/superset` |
| `ssh_command` | Ready-to-use SSH command |
| `dws_connection_string` | psql command (password omitted) |

### Get DWS password

```bash
terraform -chdir=terraform output -json | python -c "import json,sys; d=json.load(sys.stdin); print('DWS password in state — do not log')"
# The password is in terraform.tfstate — store it securely
```

---

## 7. Application URLs & Access

| Service | URL | Credentials |
|---------|-----|-------------|
| ChatBI Frontend | `http://<ECS_PUBLIC_IP>` | None (public) |
| ChatBI API Docs | `http://<ECS_PUBLIC_IP>/api/docs` | None |
| Superset BI | `http://<ECS_PUBLIC_IP>/superset` | admin / Chatbi2024! |
| SSH to ECS | `ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>` | SSH key |

**Change Superset password after first login:**
Admin → Security → List Users → Edit admin user

---

## 8. Day-2 Operations

### View logs

```bash
# Via skill
/huawei-chatbi logs

# Manually
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>
tail -200 /var/log/cloud-init-chatbi.log          # Bootstrap log
docker logs chatbi-backend --tail 100 -f           # App logs
docker logs chatbi-superset --tail 50              # Superset logs
journalctl -u nginx -n 50                          # Nginx logs
```

### Restart application

```bash
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>
cd /data
docker compose restart chatbi-backend              # Restart only backend
docker compose down && docker compose up -d        # Full restart
```

### Update backend code

```bash
# Copy updated files to ECS
scp -i chatbi-keypair.pem backend/nl2sql.py ubuntu@<ECS_PUBLIC_IP>:/opt/chatbi/backend/
scp -i chatbi-keypair.pem backend/schema_registry.py ubuntu@<ECS_PUBLIC_IP>:/opt/chatbi/backend/

# Restart container to pick up changes
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP> "cd /data && docker compose restart chatbi-backend"
```

### Update frontend

```bash
cd C:\Users\Matebook\Projects\chatbi-sandbox\frontend
npm run build
scp -i chatbi-keypair.pem -r dist/ ubuntu@<ECS_PUBLIC_IP>:/opt/chatbi/frontend/dist/
# No restart needed — Nginx reads static files directly
```

### Scale DWS (add nodes)

Edit `terraform/terraform.tfvars`:
```hcl
dws_node_count = 3   # scale from 1 to 3 nodes
```
Then run:
```bash
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```

### Restrict SSH access (recommended for production)

Edit `terraform/terraform.tfvars`:
```hcl
allowed_ssh_cidr = "203.0.113.10/32"   # replace with your IP
```
Apply to update the security group rule.

---

## 9. Teardown

> **Warning:** This permanently deletes ALL resources including DWS data. There is no undo.

```bash
# Via skill (with confirmation prompt)
/huawei-chatbi destroy

# Manually
terraform -chdir=terraform destroy
# Type "yes" when prompted
```

What gets deleted:
- All ECS instances and attached disks (100 GB + 200 GB)
- DWS cluster and all data (1 TB)
- VPC, subnets, security groups
- EIP (released back to pool)
- OBS bucket (will fail if not empty — empty it first)
- SSH keypair record

**Before destroying:** backup any DWS data you want to keep:
```bash
# On ECS
pg_dump -h <DWS_PRIVATE_IP> -p 8000 -U dbadmin chatbi > /data/chatbi_backup.sql
# Then download via scp or upload to OBS
```

---

## 10. Troubleshooting

### Terraform provider version mismatch

**Symptom:** `checksum list has unexpected SHA-256 hash` during `terraform init`

**Fix:**
```bash
# Windows CMD
set CHECKPOINT_DISABLE=1
del /s /q terraform\.terraform terraform\.terraform.lock.hcl
# Change version in main.tf from "~> 1.63.0" to ">= 1.63.0"
terraform -chdir=terraform init -upgrade
```

### DWS resource attribute errors (provider v1.91+)

| Old attribute | New attribute | Resource |
|---------------|---------------|----------|
| `subnet_id` | `network_id` | `huaweicloud_dws_cluster` |
| `private_ip` | `network[0].fixed_ip_v4` | `huaweicloud_compute_instance` |
| `private_key` output | `key_file` input | `huaweicloud_compute_keypair` |

### Backend container won't start

```bash
ssh into ECS
docker logs chatbi-backend --tail 50
```

Common causes:
- DWS not yet reachable (check DWS cluster status in console)
- Missing environment variable in `/data/chatbi/.env`
- Python package install failed (check if `pip install` in docker CMD succeeded)

### openai / httpx compatibility error

**Symptom:** `AsyncClient.__init__() got an unexpected keyword argument 'proxies'`

**Fix (sandbox only):**
```bash
pip install "openai==1.57.0" "httpx==0.27.2"
```

The production Docker container uses the same version pins.

### Frontend shows blank page after SCP

```bash
# Check dist files were copied correctly
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP> "ls /opt/chatbi/frontend/dist/"
# Should show index.html, assets/, etc.

# Check Nginx config
nginx -t
systemctl status nginx
```

### Superset login fails

Default credentials: `admin` / `Chatbi2024!`

If first-boot admin creation failed:
```bash
docker exec -it chatbi-superset bash
superset fab create-admin \
  --username admin --firstname Admin --lastname Admin \
  --email admin@chatbi.local --password Chatbi2024!
```

### cloud-init did not complete

```bash
ssh -i chatbi-keypair.pem ubuntu@<ECS_PUBLIC_IP>
cat /var/log/cloud-init-chatbi.log
# Look for error lines; the script runs set -euo pipefail so it stops on first error
# Manually re-run the failed section
```

---

## 11. Security Reference

### What is committed to git

- All Terraform `.tf` files (no secrets)
- `cloud-init.sh` template (uses Terraform variables, no literal secrets)
- `scripts/deploy.sh` / `deploy.bat`
- `docker/nginx.conf`

### What is NOT committed to git

| File | Contains | Location |
|------|----------|----------|
| `terraform.tfvars` | AK/SK, API keys | `.gitignore`d in `terraform/` |
| `chatbi-keypair.pem` | SSH private key | `.gitignore`d in project root |
| `terraform.tfstate` | DWS password, all IDs | `.gitignore`d (use remote state for teams) |
| `credentials.env` | All credentials | `~/.claude/huawei-chatbi/` (outside repo) |

### DWS network isolation

DWS is in private subnet `10.0.2.0/24`. The DWS security group only allows port 8000 from the ECS security group — no direct internet access.

To query DWS from your laptop, you must SSH tunnel through ECS:
```bash
ssh -i chatbi-keypair.pem -L 15432:<DWS_PRIVATE_IP>:8000 ubuntu@<ECS_PUBLIC_IP> -N
psql -h localhost -p 15432 -U dbadmin -d chatbi
```

### ECS Security Group rules

| Port | Source | Purpose |
|------|--------|---------|
| 80 | 0.0.0.0/0 | HTTP (ChatBI + Superset) |
| 443 | 0.0.0.0/0 | HTTPS (when cert is added) |
| 22 | `allowed_ssh_cidr` (default: 0.0.0.0/0) | SSH — **restrict in production** |

### Recommended hardening for production

1. Set `allowed_ssh_cidr` to your office/VPN IP range
2. Enable HTTPS: `certbot --nginx -d yourdomain.com`
3. Change Superset admin password from `Chatbi2024!`
4. Store `terraform.tfstate` in OBS backend with encryption
5. Rotate AK/SK after initial deployment, update `credentials.env` and `terraform.tfvars`

---

## Quick Reference — Skill Commands

```
/huawei-chatbi configure   # Set/update credentials
/huawei-chatbi plan        # terraform plan (dry run)
/huawei-chatbi apply       # terraform apply (provision)
/huawei-chatbi status      # List resources + health check
/huawei-chatbi output      # Show IPs, URLs, SSH command
/huawei-chatbi ssh         # SSH into ECS
/huawei-chatbi logs        # Tail cloud-init + docker logs
/huawei-chatbi destroy     # Destroy all resources (with confirm)
```

---

*Runbook generated 2026-05-17. Terraform plan validated: 19 resources, provider huaweicloud v1.91.0.*
