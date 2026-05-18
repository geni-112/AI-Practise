---
name: chatbi
description: >
  Full-stack ChatBI skill — scaffold, run, and deploy a Natural Language → SQL → ECharts
  visualization system on Huawei Cloud MaaS (glm-5.1). Supports local DuckDB sandbox
  and production GaussDB DWS + ECS + Superset deployment on Huawei Cloud la-south-2.
triggers:
  - /chatbi
  - chatbi sandbox
  - chatbi deploy
  - chatbi setup
---

# /chatbi — ChatBI Full-Stack Skill

Natural Language → SQL → ECharts. Two modes: **sandbox** (local, zero-cloud) and **production** (Huawei Cloud).

## Source Files Location

All source files are bundled in this skill directory:

```
~/.claude/skills/chatbi/
├── SKILL.md                          ← this file
├── RUNBOOK.md                        ← full operations runbook
└── src/
    ├── sandbox/                      ← local DuckDB version
    │   ├── .env.example
    │   ├── start.bat
    │   ├── backend/
    │   │   ├── main.py               FastAPI entry point
    │   │   ├── nl2sql.py             NL→SQL engine (AsyncOpenAI)
    │   │   ├── db.py                 DuckDB connection
    │   │   ├── chart_advisor.py      ECharts type selector
    │   │   ├── session.py            In-memory session store
    │   │   ├── cache.py              MD5 cache (30 min TTL)
    │   │   ├── schema_registry.py    Chinese schema descriptions
    │   │   ├── requirements.txt
    │   │   └── data/seed.py          100k retail demo rows
    │   └── frontend/
    │       ├── package.json
    │       ├── vite.config.ts
    │       ├── index.html
    │       └── src/
    │           ├── App.tsx
    │           ├── api.ts
    │           ├── types.ts
    │           └── components/
    │               ├── ChatWindow.tsx
    │               ├── MessageBubble.tsx
    │               ├── InputBar.tsx
    │               ├── ChartPanel.tsx
    │               └── SqlBlock.tsx
    └── deploy/                       ← Huawei Cloud production
        ├── terraform/
        │   ├── main.tf
        │   ├── variables.tf
        │   ├── vpc.tf
        │   ├── ecs.tf
        │   ├── dws.tf
        │   ├── obs.tf
        │   ├── outputs.tf
        │   ├── terraform.tfvars.example
        │   └── templates/cloud-init.sh
        └── scripts/
            ├── deploy.sh             Linux/Mac lifecycle script
            └── deploy.bat            Windows lifecycle script
```

---

## Trigger Phrases → Actions

| User says | Action |
|-----------|--------|
| `/chatbi setup sandbox` or "scaffold chatbi sandbox" | Scaffold sandbox into target directory |
| `/chatbi start` or "start chatbi" | Start sandbox (run start.bat or equivalent) |
| `/chatbi setup deploy` or "scaffold chatbi deploy" | Scaffold production terraform into target directory |
| `/chatbi configure` or "configure chatbi credentials" | Collect and store Huawei Cloud credentials |
| `/chatbi plan` or "plan chatbi" | Run terraform plan |
| `/chatbi apply` or "deploy chatbi" | Run terraform apply |
| `/chatbi status` or "chatbi status" | Show resource list + health check |
| `/chatbi output` or "chatbi urls" | Show IPs, URLs, SSH command |
| `/chatbi ssh` | SSH into ECS |
| `/chatbi logs` | Tail cloud-init + docker logs |
| `/chatbi destroy` | Destroy all Huawei Cloud resources |

---

## Phase Instructions

### setup sandbox

Goal: scaffold a working sandbox project in `<target_dir>` (default: current working directory under `chatbi-sandbox/`).

1. Ask user: "请输入项目目录路径（默认: ./chatbi-sandbox）"
2. Create the directory structure by copying all files from `~/.claude/skills/chatbi/src/sandbox/` to the target
3. Copy `.env.example` to `.env`
4. Print next steps:
   ```
   cd chatbi-sandbox
   notepad .env        # Fill in LLM_API_KEY
   start.bat           # Start everything
   ```

**File copy map** (from skill src → target project):
```
src/sandbox/backend/          → <target>/backend/
src/sandbox/frontend/         → <target>/frontend/
src/sandbox/start.bat         → <target>/start.bat
src/sandbox/.env.example      → <target>/.env.example
                              → <target>/.env   (copy of .env.example)
```

When scaffolding, use Write tool to create each file at the target path with content read from the skill's src files.

### start

1. Check `.env` exists and `LLM_API_KEY` is not placeholder
2. Run in Windows: `cd <project_dir> && start.bat`
3. Run on Linux/Mac:
   ```bash
   cd <project_dir>/backend
   pip install -r requirements.txt
   pip install "httpx==0.27.2"
   python data/seed.py  # if retail.duckdb missing
   uvicorn main:app --port 8000 &
   cd ../frontend && npm install && npm run dev
   ```
4. Open browser at http://localhost:5173

### setup deploy

Goal: scaffold the production Terraform project.

1. Ask user: "请输入部署项目目录（默认: ./chatbi-huawei-deploy）"
2. Copy all files from `~/.claude/skills/chatbi/src/deploy/` to target
3. Copy `terraform.tfvars.example` → inform user to fill it in or run `/chatbi configure`
4. Print next steps:
   ```
   cd chatbi-huawei-deploy/terraform
   cp terraform.tfvars.example terraform.tfvars
   # Fill in terraform.tfvars OR run /chatbi configure
   deploy.bat plan
   ```

**File copy map**:
```
src/deploy/terraform/         → <target>/terraform/
src/deploy/scripts/           → <target>/scripts/
```

### configure

Collect credentials and store at `~/.claude/huawei-chatbi/credentials.env`:

1. Check if `~/.claude/huawei-chatbi/credentials.env` exists
2. If missing or user requests reconfigure, collect:
   - HW_ACCESS_KEY (华为云 Access Key)
   - HW_SECRET_KEY (华为云 Secret Key)
   - HW_REGION (default: la-south-2)
   - MAAS_API_KEY (MaaS API Key)
   - MAAS_BASE_URL (default: https://api-ap-southeast-1.modelarts-maas.com/openai/v1)
   - MAAS_MODEL (default: glm-5.1)
   - ECS_FLAVOR (default: c7.xlarge.4)
   - DWS_FLAVOR (default: dws.d2.xlarge.8)
   - EIP_BANDWIDTH (default: 5)
3. Write file — confirm saved by field names only, NEVER echo values

### plan

1. Load `~/.claude/huawei-chatbi/credentials.env`
2. Write `terraform/terraform.tfvars` from credentials
3. Run:
   ```
   set CHECKPOINT_DISABLE=1
   terraform -chdir=<deploy_dir>/terraform init -upgrade
   terraform -chdir=<deploy_dir>/terraform plan -out=tfplan
   ```
4. Show resource count summary. Expected: 19 resources to add.

### apply

1. Confirm plan has been reviewed (or run plan first)
2. Run:
   ```
   set CHECKPOINT_DISABLE=1
   terraform -chdir=<deploy_dir>/terraform apply tfplan
   ```
3. After completion, show all outputs (IPs, URLs, SSH command)
4. Note: DWS creation takes ~45 minutes, full stack ~60 minutes

### status

1. `terraform state list` — list all resources
2. `terraform output` — show IPs and URLs
3. HTTP check: `curl http://<ecs_public_ip>/api/health`

### ssh

1. Get ECS IP from `terraform output -raw ecs_public_ip`
2. `ssh -i <deploy_dir>/chatbi-keypair.pem ubuntu@<IP>`

### logs

SSH into ECS and run:
```bash
tail -200 /var/log/cloud-init-chatbi.log
docker logs chatbi-backend --tail 100
docker logs chatbi-superset --tail 50
```

### destroy

1. Warn: "将永久删除所有资源，包括 DWS 数据，不可恢复"
2. Require explicit confirmation
3. `terraform -chdir=<deploy_dir>/terraform destroy -auto-approve`

---

## Architecture Reference

```
[Browser] → [Nginx :80]
              ├── /          → /opt/chatbi/frontend/dist  (React + ECharts)
              ├── /api/      → chatbi-backend :8001       (FastAPI)
              └── /superset/ → chatbi-superset :8088      (Apache Superset)

chatbi-backend → GaussDB DWS :8000 (private subnet, psycopg2)
chatbi-backend → Huawei MaaS API  (NL→SQL via glm-5.1)
```

**Sandbox mode**: DuckDB replaces DWS. Everything runs on localhost.  
**Production mode**: DWS on private subnet, ECS on public subnet with EIP.

---

## Key Technical Notes

### NL2SQL pipeline
- 3-attempt retry loop with error context fed back to LLM
- `temperature=0.1` for deterministic SQL
- SQL extraction strips markdown fences with regex
- Schema injected into every system prompt

### Terraform provider compatibility
- Must use `>= 1.63.0` (NOT `~> 1.63.0`) — resolves to v1.91.0
- Set `CHECKPOINT_DISABLE=1` to avoid checksum fetch issues
- DWS uses `network_id` (not `subnet_id`)
- ECS private IP: `network[0].fixed_ip_v4`
- Keypair uses `key_file` input (no `private_key` output attribute)

### Python dependency pins
- `openai==1.57.0` + `httpx==0.27.2` — must pin both, openai 1.51 is incompatible with httpx 0.28+

### DWS initialization (post-deploy)
After `terraform apply`, connect via SSH tunnel and run:
```sql
CREATE DATABASE chatbi;
-- Then create tables (same schema as DuckDB seed.py)
```

---

## Cost Estimate (la-south-2, ~monthly)

| Resource | Spec | Est. Cost |
|----------|------|-----------|
| ECS c7.xlarge.4 | 4C/16G | ~$120 |
| DWS dws.d2.xlarge.8 | 1 node, 1TB | ~$300 |
| EIP 5 Mbps | Traffic billing | ~$10 |
| OBS | Standard | ~$1 |
| **Total** | | **~$430/mo** |

---

## Security Checklist

- `terraform.tfvars` is gitignored — never commit
- `chatbi-keypair.pem` is gitignored — chmod 600 on Linux/Mac
- DWS security group: only allows port 8000 from ECS security group
- SSH: restrict `allowed_ssh_cidr` to your IP range in production
- Superset: change default password `Chatbi2024!` after first login
