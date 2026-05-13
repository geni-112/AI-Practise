---
name: litellm-aicoding-gateway-single-ecs
description: Use this skill when deploying a single-ECS AI coding gateway on Huawei Cloud that fronts Huawei Cloud MaaS through LiteLLM and exposes SearXNG as a remote MCP search tool, especially when integrating with Claude Code via claude-code-router (claude-glm) without disturbing the user's regular `claude` setup.
updated: 2026-05-12
---

# LiteLLM + SearXNG AI Coding Gateway on Single Huawei Cloud ECS

This skill supersedes `litellm-huawei-maas-single-ecs`. It reuses every rule from that skill and adds:

- A reproducible end-to-end deployment recipe that survives Prisma, systemd, and SearXNG quirks on Ubuntu 22.04 ECS images.
- A **SearXNG search MCP** (FastMCP HTTP transport, bearer-auth) so AI coding agents can call `web_search` and `fetch_url`.
- An **AI coding agent integration** path: Claude Code via `claude-code-router` (`claude-glm`) routed through LiteLLM at the proxy layer, with `CLAUDE_CONFIG_DIR` isolation so the user's plain `claude` is unaffected.
- A **credential GUI** (`credential_form.py`) that collects AK/SK, MaaS key, and SSH key into a local `credential.skill` JSON file and an **automated Python orchestrator** (`deploy.py`) that drives all 17 steps end-to-end from a Windows/Linux laptop.

Use this skill when the task is to install, configure, validate, or repair the full single-host stack:

```
ECS host
├── LiteLLM Proxy   :4000   (master + virtual keys, FinOps, multi-user)
├── Redis           :6379   (cache, router state)            local only
├── PostgreSQL      :5432   (keys, teams, spend logs)        local only
├── SearXNG         :8080   (meta-search, JSON enabled)      local only
└── SearXNG MCP     :8788   (FastMCP HTTP, bearer-auth)      external

Local laptop
├── claude          → Anthropic (untouched)
└── claude-glm      → ccr :3456 → LiteLLM :4000 → MaaS glm-5.1
                     + remote MCP searxng :8788 (web_search, fetch_url)
                     CLAUDE_CONFIG_DIR=~/.claude-glm-config (isolation)
```

## Required Inputs

Confirm before making changes:

- Huawei Cloud AK/SK with ECS, EVS, EIP, VPC, OBS write scope in the target region.
- Huawei Cloud Region and Project ID. **Do not hardcode the Project ID — derive it from IAM at runtime** (see Step 0).
- Huawei MaaS API base, e.g. `https://api-ap-southeast-1.modelarts-maas.com/openai/v1`.
- Huawei MaaS API key.
- Explicit MaaS model IDs to expose, e.g. `glm-5.1`.
- LiteLLM listen port (default `4000`).
- MCP listen port (default `8788`).
- Allow-list CIDR for the laptop calling LiteLLM/MCP (current public egress IP / 32).
- Whether the user's regular `claude` must remain on the Anthropic endpoint (almost always yes).

If the user only gives one model, prefer explicit routing for that model (`huawei/glm-5.1` -> `openai/glm-5.1`) instead of wildcards.

## Core Rules

Inherit all rules from `litellm-huawei-maas-single-ecs` (explicit model mappings, local-only Redis/PostgreSQL, env-file secrets, systemd everywhere, validate both direct and proxied paths, FinOps pricing, multi-user keys). Additionally:

- **Never write AK/SK, MaaS keys, virtual keys, or bearer tokens into committed files**. They go into env files with `0640 root:litellm` (or equivalent). Generated assets must reference `os.environ/...` or `$VAR_NAME` placeholders.
- **`claude-glm` must point at LiteLLM, not directly at MaaS**, so spend, rate limits, caching, and audit live in one place.
- **`claude-glm` must use `CLAUDE_CONFIG_DIR` isolation** so MCP registration, settings, and history do not pollute the user's regular `claude`.
- **SearXNG must be local-only** on the ECS (`127.0.0.1:8080`). External access only goes through the bearer-auth MCP layer.
- **All exposed ports are CIDR-locked** to the laptop's current outbound IP. When the laptop's IP changes, update the SG, do not widen to `0.0.0.0/0`.
- **Reuse the existing default VPC/subnet** when the project is at the router/VPC quota; do not delete shared infra to make room.

## Huawei Cloud SDK Known Traps (2026-05 实测)

These traps were discovered during an actual end-to-end deployment run and cost hours to debug. Read them before touching the provisioning script.

### Trap 1 — Nova v2.1 APIs are incompatible with AK/SK auth

The Huawei Cloud Python SDK ships two keypair/server paths:

- **ECS v1.1 path** (`huaweicloudsdkecs`): uses `BasicCredentials(AK, SK, project_id)` with HMAC-SHA256 signing. This is the correct path.
- **Nova v2.1 path** (`NovaCreateKeypairRequest`, `NovaListKeypairsRequest`): requires OpenStack Keystone token auth. Calling it with `BasicCredentials` returns `401 APIGW.0301: Incorrect IAM authentication information: get token error` with no further detail.

**Fix:** Never use Nova v2.1 APIs in an AK/SK flow. To inject an SSH key into a new ECS, encode a `cloud-init` bash script in base64 and pass it as `user_data` on the `PostPaidServer` constructor:

```python
userdata_script = textwrap.dedent(f"""\
    #!/bin/bash
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    echo '{pub_content}' >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    chown -R root:root /root/.ssh
""")
userdata_b64 = base64.b64encode(userdata_script.encode()).decode()
server_body = PostPaidServer(
    nics=[PostPaidServerNic(subnet_id=state["SUBNET_ID"])],
    vpcid=state["VPC_ID"],
    user_data=userdata_b64,
    ...
)
```

Avoid heredoc-heavy `cloud-init`. `user_data` bash scripts are reliable; YAML heredocs under nested quoting in Python strings break silently.

### Trap 2 — `PostPaidServer` field names differ from the API JSON

The SDK model does not mirror the JSON key names from the API docs:

| API docs field | SDK param name |
|---|---|
| `networks` | `nics` (list of `PostPaidServerNic`) |
| `vpcid` | `vpcid` (top-level, NOT in `nics`) |
| `user_data` | `user_data` (top-level, NOT inside `metadata`) |

Getting any of these wrong yields `Ecs.0015` or a 400 with a misleading body.

### Trap 3 — Project ID must come from IAM, not from the console

The Project ID shown in the Huawei Cloud console "My Credentials" page is the **global** IAM project, not the per-region project. SDK calls to regional endpoints (ECS, VPC, IMS, EIP) require the **regional** Project ID, which is different.

**Fix:** Always detect the correct regional Project ID at runtime using the IAM service (which does not require a project ID on the credential):

```python
from huaweicloudsdkiam.v3 import IamClient, KeystoneListProjectsRequest
from huaweicloudsdkcore.auth.credentials import GlobalCredentials

iam_client = IamClient.new_builder() \
    .with_credentials(GlobalCredentials(AK, SK)) \
    .with_region(IamRegion.value_of("cn-north-4")) \
    .build()
resp = iam_client.keystone_list_projects(
    KeystoneListProjectsRequest(name=REGION)
)
project_id = resp.projects[0].id
```

Auto-update the credential store with the detected ID so subsequent runs skip the lookup.

### Trap 4 — `ListImagesRequest` parameter name

The IMS SDK parameter to filter by image type is `imagetype` (no leading underscores). Older SDK versions and many code examples use `__imagetype` (the API JSON key). Passing `__imagetype` as a Python keyword argument raises `TypeError: unexpected keyword argument '__imagetype'`.

```python
# Wrong:
req = ListImagesRequest(__imagetype="gold", name="Ubuntu 22.04")
# Correct:
req = ListImagesRequest(imagetype="gold", name="Ubuntu 22.04")
```

### Trap 5 — GPU images match generic "Ubuntu 22.04" name filter

Huawei Cloud hosts GPU-driver images with names like `"Ubuntu 22.04 server 64bit with Tesla Driver 535.183.01 and CUDA 12.2"`. A filter `name="Ubuntu 22.04"` is a substring match and will return the GPU image first (lexicographically or by creation date). Attempting to boot a GPU image on a general-compute flavor (`s6.xlarge.2`) fails with `Ecs.0005: The flavor does not match the image`.

**Fix:** Filter with the exact vanilla name and add a fallback exclusion:

```python
images = [
    img for img in resp.images
    if img.name == "Ubuntu 22.04 server 64bit"
    and "cuda" not in img.name.lower()
    and "tesla" not in img.name.lower()
]
```

### Trap 6 — `ServerAddress` object fields have renamed attributes

After ECS provisioning, `server.addresses` values are SDK model objects (`ServerAddress`), not plain dicts. The `OS-EXT-IPS:type` JSON field maps to the attribute `os_ext_ip_stype` (not `os_ext_ips_type`). Accessing it as a dict key raises `AttributeError`.

```python
# Wrong:
if addr.get("OS-EXT-IPS:type") == "floating":
# Correct:
if getattr(addr, "os_ext_ip_stype", None) == "floating":
    eip = getattr(addr, "addr", None)
```

### Trap 7 — Windows subprocess defaults to GBK encoding

On Windows, `subprocess.run()` without an explicit encoding uses the system code page (GBK / CP936). SSH output from a UTF-8 Linux host raises `UnicodeDecodeError: 'gbk' codec can't decode`. Always specify:

```python
result = subprocess.run(
    cmd, capture_output=True, timeout=timeout,
    encoding="utf-8", errors="replace",
)
```

## Deployment Workflow

### 0. Preflight on the laptop

- Get current outbound IP: `curl -s https://ifconfig.me`. Lock SG rules to this `/32`.
- Confirm Huawei Cloud Python SDK is available: `pip install -q huaweicloudsdkecs huaweicloudsdkvpc huaweicloudsdkims huaweicloudsdkeip huaweicloudsdkiam`.
- Confirm `ssh`, `curl`, `jq`, `openssl` exist.
- Decide whether `claude` (Claude Code CLI) is already installed locally. If yes, take note of `which claude` so you can confirm it does not move.
- **Auto-detect regional Project ID** from IAM before any SDK call (see Trap 3 above). Never trust the Project ID from the console "My Credentials" page for regional operations.
- Use `credential_form.py` to collect AK/SK, MaaS key, SSH key, and optional ECS IP into `credential.skill` (JSON, mode 600). The `deploy.py` orchestrator reads this file and generates fresh secrets for Redis, PostgreSQL, and LiteLLM master key on first run, persisting them in `deploy_state.json`.

### 1. Provision ECS (and optionally OBS / CSS)

Use the skill's `deploy.py` orchestrator which handles the well-known traps:

- Router/VPC quota exhausted → reuse an existing VPC and subnet.
- CSS `COMMON` disk type sold out → fall back to `HIGH`.
- Ubuntu cloud images often log in as **`root`**, not `ubuntu`. Track which user the image actually allows.
- Avoid heredoc-heavy `cloud-init`. Bring the host up bare, then push install scripts over SSH; `cloud-init` YAML parsing breaks in surprising ways under nested heredocs.
- **Pass the SSH public key via `user_data` base64 bash script** (see Trap 1) — do not use Nova v2.1 keypair API.
- **Filter GPU images out** when selecting Ubuntu 22.04 (see Trap 5).

Recommended ECS shape for an AI coding gateway with one operator:

- Flavor: `s6.xlarge.2` (4 vCPU / 8 GB) or `s6.2xlarge.2` (8 vCPU / 16 GB) general-compute.
- EVS: 100–200 GB general-purpose v2.
- EIP: traffic mode, 100–300 Mbit/s.
- OS: Ubuntu 22.04. Do **not** assume LTS image already has `python3-venv` or `pip`; install both.
- Generate a fresh SSH keypair locally. Embed the public key via `user_data` cloud-init. Save the private key as `~/.ssh/<prefix>` with mode 600.

Open the SG only to your current `/32` and only on the ports you actually need now: `22, 4000, 8788`. Add more later when needed.

### 2. Inspect the host

Before installing anything:

```
uname -a
cat /etc/os-release | grep -E 'PRETTY|VERSION_ID'
nproc; free -h | head -2; df -h /
which python3 redis-server psql docker
ss -tlnp
```

If `sudo -n true` does not work, fall back to passwordless paths or run as root. The Huawei Ubuntu 22.04 image typically logs in as `root`, which makes the install simpler.

### 3. Install runtime packages

```
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3-venv python3-pip redis-server postgresql postgresql-contrib \
  build-essential libpq-dev curl openssl docker.io docker-compose-v2
systemctl enable --now redis-server postgresql docker
```

Notes:

- Use the distro `redis-server` and `postgresql` packages. Building from source is unnecessary for a single-tenant gateway.
- Install Docker now even if the LiteLLM portion does not need it; SearXNG does.

### 4. Configure Redis (local-only, password)

Generate `REDIS_PWD=$(openssl rand -hex 16)` and:

```
sed -i 's/^# *requirepass .*/requirepass '"$REDIS_PWD"'/' /etc/redis/redis.conf
grep -q '^requirepass' /etc/redis/redis.conf || echo "requirepass $REDIS_PWD" >> /etc/redis/redis.conf
sed -i 's/^bind .*/bind 127.0.0.1 ::1/' /etc/redis/redis.conf
systemctl restart redis-server
redis-cli -a "$REDIS_PWD" ping     # expect PONG
```

### 5. Configure PostgreSQL (local-only)

Generate `PG_PWD=$(openssl rand -hex 16)`. Use `peer` for local admin and `md5` for the LiteLLM role over `127.0.0.1`:

```
sudo -u postgres psql <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='litellm') THEN
    CREATE ROLE litellm LOGIN PASSWORD '$PG_PWD';
  ELSE
    ALTER ROLE litellm WITH LOGIN PASSWORD '$PG_PWD';
  END IF;
END \$\$;
SQL
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='litellm'" | grep -q 1 \
  || sudo -u postgres createdb -O litellm litellm
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE litellm TO litellm;"

PG_HBA=$(sudo -u postgres psql -tAc 'SHOW hba_file;')
grep -q "host litellm litellm 127.0.0.1/32 md5" "$PG_HBA" \
  || echo "host litellm litellm 127.0.0.1/32 md5" >> "$PG_HBA"
systemctl reload postgresql
PGPASSWORD="$PG_PWD" psql -h 127.0.0.1 -U litellm -d litellm -c "SELECT version();" | head -3
```

### 6. Install LiteLLM into a dedicated venv

```
useradd --system --home /opt/litellm --shell /usr/sbin/nologin litellm
mkdir -p /opt/litellm /etc/litellm
chown -R litellm:litellm /opt/litellm /etc/litellm
python3 -m venv /opt/litellm-venv
/opt/litellm-venv/bin/pip install -q --upgrade pip wheel
/opt/litellm-venv/bin/pip install -q "litellm[proxy]" prisma psycopg redis
/opt/litellm-venv/bin/litellm --version
chown -R litellm:litellm /opt/litellm-venv
```

### 7. Write LiteLLM config and env

`/etc/litellm/litellm.env` (mode `0640 root:litellm`):

See [assets/config/litellm.env.example](assets/config/litellm.env.example). Critical fields beyond the skeleton in `litellm-huawei-maas-single-ecs`:

- `PRISMA_QUERY_ENGINE_BINARY=` absolute path to the engine binary that Prisma fetched (see Step 8).
- `HOME=/opt/litellm` so Prisma's config loader does not try to read the invoking user's `pyproject.toml`. Without this, Python 3.10's `pathlib.Path.exists()` raises `PermissionError` (not `False`) when the CWD is root-owned — it bubbles up and crashes startup.
- `PATH=/opt/litellm-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` so LiteLLM's startup `subprocess.run(["prisma"])` finds the CLI under systemd.

`/etc/litellm/config.yaml`:

See [assets/config/litellm.config.yaml.example](assets/config/litellm.config.yaml.example). Keep explicit Huawei MaaS mappings only; no wildcards. Use the validated GLM-5.1 prices unless the user supplies different ones:

- `input_cost_per_token: 1.078e-06`
- `output_cost_per_token: 3.774e-06`

### 8. Bootstrap Prisma BEFORE first start — the most fragile step

This is the single most fragile step on enterprise Linux. Do it explicitly; do **not** trust `--use_prisma_db_push` to bootstrap from nothing.

The install script (`scripts/install_litellm.sh`) handles this in full. The key insight is:

**The Prisma Python client (`client.py`) bakes absolute paths to the query engine binary into `BINARY_PATHS` at `prisma generate` time, based on the `HOME` environment variable of whoever ran `generate`.**

If you run `prisma generate` as root (`HOME=/root`), `BINARY_PATHS` will contain `/root/.cache/prisma-python/...`. The `litellm` system user (shell=`/usr/sbin/nologin`) cannot traverse `/root/` (mode 700), so even with `PRISMA_QUERY_ENGINE_BINARY` correctly set in the env file, the Python client still fails with `Not connected to the query engine` — because it tries the baked-in path first.

**Correct sequence:**

```bash
SCHEMA=$(find /opt/litellm-venv -name schema.prisma | head -1)
export PATH=/opt/litellm-venv/bin:$PATH
export DATABASE_URL=$(grep ^DATABASE_URL /etc/litellm/litellm.env | cut -d= -f2-)

# Step 1: generate + db push (runs as root, OK for bootstrap)
/opt/litellm-venv/bin/prisma generate --schema "$SCHEMA"
/opt/litellm-venv/bin/prisma db push --schema "$SCHEMA" --accept-data-loss --skip-generate

# Step 2: find the engine binary
ENGINE=$(find / -name 'query-engine-debian-openssl-3.0.x' \
                 -path '*node_modules/prisma/*' 2>/dev/null | head -1)

# Step 3: make it readable by the litellm user
chmod -R o+rX "$(dirname "$(dirname "$(dirname "$ENGINE")")")"
echo "PRISMA_QUERY_ENGINE_BINARY=$ENGINE" >> /etc/litellm/litellm.env

# Step 4 (CRITICAL): regenerate with HOME=/opt/litellm so BINARY_PATHS in
# client.py contains /opt/litellm/.cache/... not /root/.cache/...
HOME=/opt/litellm PRISMA_QUERY_ENGINE_BINARY="$ENGINE" \
  /opt/litellm-venv/bin/prisma generate --schema "$SCHEMA"
```

Step 4 is what the original install script was missing. After Step 4, verify:

```bash
grep -A5 'BINARY_PATHS' \
  "$(find /opt/litellm-venv -name 'client.py' -path '*/prisma/client.py' | head -1)"
# Should show paths starting with /opt/litellm/... not /root/...
```

### 9. Create systemd units

Use the example unit at [assets/config/litellm.service.example](assets/config/litellm.service.example). Beyond the previous skill, ensure:

- `EnvironmentFile=/etc/litellm/litellm.env` so `PATH`, `HOME`, and `PRISMA_QUERY_ENGINE_BINARY` reach the process.
- **Do NOT add `--use_prisma_db_push` to `ExecStart`** once the schema has been bootstrapped. The flag spawns a Node.js `prisma` subprocess that tries to interpret the Python engine binary path as a Node binary — it fails on every startup, filling the log with noise and adding 10+ seconds to startup time. The flag is only safe if a Node.js `prisma` CLI is installed in `PATH`. Since we use `prisma-client-py`, it is not.

```
systemctl daemon-reload
systemctl enable --now litellm.service
journalctl -u litellm.service -n 80 --no-pager
ss -tlnp | grep :4000
```

LiteLLM is healthy when:

```
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://127.0.0.1:4000/health | jq '.healthy_count, .unhealthy_count'
# expect: 2  0     (one row per explicit model mapping)
```

If `unhealthy_count > 0`, the upstream MaaS key or model id is wrong; do not patch around it with wildcards.

### 10. Validate end-to-end before adding clients

Validate in this order; do not skip steps:

1. Direct MaaS request from the ECS using the MaaS key — confirms outbound and credentials.
2. LiteLLM `/health/liveliness` (no auth) — process up.
3. LiteLLM `/health` with master key — upstream reachable per model.
4. LiteLLM `/v1/chat/completions` with master key on `huawei/glm-5.1` — sync path.
5. LiteLLM `/v1/chat/completions` with `stream:true` — SSE path.
6. LiteLLM `/key/generate` — mints a virtual key.
7. LiteLLM `/v1/chat/completions` with the virtual key — proves multi-user path and budget hooks.
8. LiteLLM `/model/info` — confirms non-zero `input_cost_per_token` and `output_cost_per_token` (otherwise budgets do not bite).

### 11. Deploy SearXNG (Docker, local-only)

```
mkdir -p /opt/searxng/searxng
SECRET=$(openssl rand -hex 32)
```

Drop in [assets/config/searxng-docker-compose.yml](assets/config/searxng-docker-compose.yml) and [assets/config/searxng-settings.yml](assets/config/searxng-settings.yml). Two non-obvious points:

- `ports: "127.0.0.1:8080:8080"` — bind to loopback only; the MCP layer is the public face.
- `search.formats` must include `json`. Without it, the MCP gets HTML and the tool call returns an opaque parse error.

Bring it up:

```
cd /opt/searxng && docker compose pull && docker compose up -d
sleep 8
curl -s -G 'http://127.0.0.1:8080/search' \
  --data-urlencode 'q=hello' --data-urlencode 'format=json' \
  -H 'Accept: application/json' | jq '.results | length'
# expect: a number > 0
```

### 12. Build the SearXNG MCP HTTP server

Use FastMCP 2.x with HTTP (streamable) transport and a static bearer token. See:

- [assets/config/searxng_mcp_server.py](assets/config/searxng_mcp_server.py) — the server.
- [assets/config/searxng-mcp.service.example](assets/config/searxng-mcp.service.example) — systemd unit.

Install:

```
useradd --system --home /opt/searxng-mcp --shell /usr/sbin/nologin searxmcp
mkdir -p /opt/searxng-mcp
python3 -m venv /opt/searxng-mcp/venv
/opt/searxng-mcp/venv/bin/pip install -q --upgrade pip
/opt/searxng-mcp/venv/bin/pip install -q "fastmcp>=2,<3" httpx
cp searxng_mcp_server.py /opt/searxng-mcp/server.py
chown -R searxmcp:searxmcp /opt/searxng-mcp

MCP_TOKEN=$(openssl rand -hex 16)
sed "s|@@TOKEN@@|$MCP_TOKEN|" searxng-mcp.service.example \
    > /etc/systemd/system/searxng-mcp.service
systemctl daemon-reload
systemctl enable --now searxng-mcp.service
ss -tlnp | grep :8788
```

Two FastMCP-specific gotchas that have wasted time before:

- In FastMCP 2.14+, `StaticTokenVerifier` is exported from `fastmcp.server.auth`, **not** from `fastmcp.server.auth.providers.bearer`. Older code paths in tutorials still reference the old path.
- Set `mcp.auth = StaticTokenVerifier(tokens={TOKEN: {"client_id": "..."}})` **before** `mcp.run(transport="http", ...)`.

### 13. Open SG for MCP from the laptop only

```python
# Pseudo-code; use the Huawei Cloud SDK form your provisioning script already uses.
add_sg_rule(security_group_id, ingress_tcp=8788, cidr=f"{laptop_public_ip}/32",
            description="searxng-mcp from operator laptop")
```

Probe from the laptop:

```
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://<ECS_PUBLIC_IP>:8788/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json,text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
# expect 401   (because the token header is missing)
```

Then with `Authorization: Bearer $MCP_TOKEN` you should get HTTP 200, `mcp-session-id`, and a JSON-RPC `initialize` result. See [references/searxng-mcp.md](references/searxng-mcp.md) for the full HTTP transport handshake.

### 14. Wire AI coding agent (`claude-glm`) into the gateway

This is the part the previous skill did not cover end-to-end.

`claude-code-router` (`ccr`) takes Anthropic-format requests on `127.0.0.1:3456` and rewrites them to OpenAI-format upstream. We point that upstream at LiteLLM, not directly at MaaS, so spend and policy live in LiteLLM:

- [assets/config/claude-code-router.config.json.example](assets/config/claude-code-router.config.json.example) — Provider points at `http://<ECS_PUBLIC_IP>:4000/v1/chat/completions` with the LiteLLM virtual key.
- [assets/config/claude-glm-wrapper.sh.example](assets/config/claude-glm-wrapper.sh.example) — wrapper that:
  - Sources `~/.config/claude-glm/env` for `LITELLM_VIRTUAL_KEY` and `CLAUDE_GLM_ROUTER_KEY`.
  - Sets `ANTHROPIC_BASE_URL=http://127.0.0.1:3456`.
  - Sets `CLAUDE_CONFIG_DIR="$HOME/.claude-glm-config"` so MCP, settings, history are isolated from the user's plain `claude`.
  - Auto-starts `ccr` if not running.
  - Defaults `--model huawei-glm-5.1` (use the LiteLLM **alias without slash** — see below).

Two non-obvious decisions that bit us before:

- LiteLLM exposes both `huawei/glm-5.1` and `huawei-glm-5.1`. ccr's Router uses a `provider,model` notation parsed by comma. Slashes in model names are tolerated but make scripts harder to grep. Use the no-slash alias `huawei-glm-5.1` for ccr.
- The router config supports `$VAR_NAME` substitution. Putting raw keys in `config.json` works but loses rotation safety; always use env-var indirection.

Restart ccr:

```
ccr stop ; sleep 1 ; ccr start
ss -tlnp | grep :3456
```

Smoke test:

```
claude-glm -p '只回复两个字：你好'
# expect: 你好
```

Then check the router log shows `model: "huawei-glm-5.1"` chunks — proves LiteLLM is in the path, not direct MaaS.

### 15. Register the SearXNG MCP into `claude-glm` only

```
mkdir -p ~/.claude-glm-config
CLAUDE_CONFIG_DIR=~/.claude-glm-config claude mcp add \
  --transport http --scope user searxng \
  http://<ECS_PUBLIC_IP>:8788/mcp \
  --header "Authorization: Bearer $MCP_TOKEN"

CLAUDE_CONFIG_DIR=~/.claude-glm-config claude mcp list   # should show searxng ✓
claude mcp list                                           # should NOT show searxng
```

The first `claude-glm` invocation that calls `mcp__searxng__web_search` triggers the permission prompt. Approve once. For non-interactive runs:

```
claude-glm --permission-mode bypassPermissions -p '<prompt that requires search>'
```

### 16. End-to-end coding agent test

```
claude-glm --permission-mode bypassPermissions -p \
  '用 mcp__searxng__web_search 查 Huawei Cloud MaaS GLM 价格，列出前 3 条 title+url。'
```

Expect three real results from SearXNG, formatted by GLM-5.1, returned through LiteLLM through ccr to Claude Code. If you see `tool_use_id` errors, ccr did not receive the tool result; fall back to non-streaming, then re-enable.

### 17. Onboarding additional client laptops

Steps 14–16 wire the laptop you deployed *from*. When a teammate or a second laptop needs to plug into the same gateway, do **not** redeploy LiteLLM/SearXNG/Prisma — they are already up. Hand off three values to the new client out-of-band (1Password, encrypted message, internal vault) and add their `/32` to the SG.

Operator hand-off checklist:

- [ ] Mint a new LiteLLM virtual key for the new client (one key per laptop is best for spend attribution and clean revocation; see `references/aicoding-agent-integration.md`).
- [ ] Share `<ECS_PUBLIC_IP>`, `<LITELLM_VIRTUAL_KEY>`, and the SearXNG `<MCP_BEARER_TOKEN>` over a confidential channel.
- [ ] Add the new laptop's `curl ifconfig.me` value as an ingress `/32` rule on the existing SG for `tcp/22`, `tcp/4000`, `tcp/8788`. Do not widen to `0.0.0.0/0`.
- [ ] If the SG hits its rule quota, retire `/32`s for laptops that off-boarded.

The client then runs the bundled installer:

```
ECS_PUBLIC_IP='<ECS_PUBLIC_IP>' \
LITELLM_VIRTUAL_KEY='<LITELLM_VIRTUAL_KEY>' \
MCP_TOKEN='<MCP_BEARER_TOKEN>' \
bash scripts/install_claude_glm_client.sh
```

Full client recipe (manual install, day-2 ops, off-boarding) is in [references/laptop-client-onboarding.md](references/laptop-client-onboarding.md).

## FinOps: Token Cost Management

LiteLLM ships a full admin UI at:

```
http://<ECS_PUBLIC_IP>:4000/ui
```

Log in with:

- **Username:** `admin`
- **Password:** your `LITELLM_MASTER_KEY` value (the `sk-...` string from `litellm.env`)

From the UI you can:

- View per-key, per-team, per-model spend aggregated by day/week/month.
- Set monthly spend budgets on virtual keys and teams — requests exceeding the budget return `429`.
- Mint, rotate, and revoke virtual keys.
- View per-request latency, token counts, and model routing decisions in the request log.

All spend data is persisted in PostgreSQL. The `proxy_batch_write_at: 5` config setting batches writes in groups of 5 requests (tune down to 1 for higher-fidelity accounting at the cost of more DB writes).

## Health Check Interpretation

Inherits everything from `litellm-huawei-maas-single-ecs`. New cases:

- LiteLLM service `active` but no `:4000` listener → still in startup; check `journalctl -u litellm.service` for `Application startup complete.` Most "active but no listener" cases are Prisma engine startup, not LiteLLM itself.
- `Not connected to the query engine` with no other detail → engine binary unreadable or absent, **or** `client.py` BINARY_PATHS still points to `/root/.cache/...` — re-run the full Prisma bootstrap sequence in Step 8, including the HOME=/opt/litellm regeneration (Step 4 of that sequence).
- MCP `/mcp` returns 401 with token → check the token actually loaded into the systemd unit; `systemctl show searxng-mcp.service -p Environment` will tell you.
- MCP returns 200 but `tools/list` empty → FastMCP server started without registering tools; usually means import failure that did not crash the process. Check `journalctl -u searxng-mcp.service`.
- ccr returns 401/403 → LiteLLM virtual key in `config.json` (`$LITELLM_VIRTUAL_KEY`) is empty in the ccr process environment. Restart `ccr` after sourcing `claude-glm` env.
- claude-glm replies but the model id in chunks is `glm-5.1` (no `huawei-` prefix) → ccr is bypassing LiteLLM and going straight to MaaS; provider URL is wrong.
- All SDK calls return `401 APIGW.0301` → most likely wrong regional Project ID (see Trap 3). Re-run IAM project detection and update credential store.

## Repair Playbook

Inherits everything from `litellm-huawei-maas-single-ecs`. Add:

- If you hit Prisma `Not connected to the query engine` after a LiteLLM upgrade, re-run `prisma generate` and `prisma db push` **with `HOME=/opt/litellm`** (see Step 8). The cached engine path changes on every minor version bump.
- If `client.py` BINARY_PATHS shows `/root/.cache/...`, run Step 4 of the Prisma bootstrap (`HOME=/opt/litellm prisma generate`). You do not need to redo db push.
- If ccr config file changes are not picked up, `ccr stop` then `ccr start`. There is no SIGHUP path; restart is mandatory.
- If `claude-glm` shows the **interactive Anthropic model picker** after a wrapper edit, the wrapper failed to set `ANTHROPIC_MODEL` before `claude` started. Use `claude --model "$ANTHROPIC_MODEL"`, not `--model=$ANTHROPIC_MODEL` — Claude Code's CLI parser is tolerant of both, but quoting the value avoids surprises with model names containing slashes.
- If `mcp list` reports `searxng: ! Failed` but `curl` to `:8788/mcp` works, check that the `--header` you registered exactly matches `Authorization: Bearer <token>`. Quotes and trailing spaces are silent killers.
- If the laptop's outbound IP changed, **do not** widen SG to `0.0.0.0/0`. Add a new `/32` rule for the new IP and remove the stale rule.
- If ECS provisioning fails with `Ecs.0005`, check that the Ubuntu image is the plain server edition, not a CUDA/Tesla GPU image (see Trap 5).
- If SDK calls fail with `TypeError: unexpected keyword argument '__imagetype'`, remove the double underscores (see Trap 4).

## Output Expectations

When completing the task, leave behind:

- A working `litellm.service`, `redis-server`, `postgresql`, `searxng-mcp.service`, and a SearXNG Docker container, all `enabled` and `active`.
- `/etc/litellm/litellm.env` containing all secrets, `0640 root:litellm`, no secrets duplicated in `config.yaml`. `HOME=/opt/litellm` and `PRISMA_QUERY_ENGINE_BINARY` present.
- Prisma `client.py` `BINARY_PATHS` showing `/opt/litellm/...` paths (not `/root/...`).
- `/etc/systemd/system/searxng-mcp.service` with the bearer token in `Environment=`, mode `0644`.
- Validated direct MaaS request, validated proxied LiteLLM request, validated MCP `web_search` call.
- An `~/.claude-glm-config/.claude.json` containing the searxng MCP and **only** that.
- A confirmation that the user's plain `claude` still uses Anthropic and does not see the searxng MCP.
- A short operator note listing endpoints, file paths, service names, virtual key, MCP token, and SG-allowed CIDRs.
- A reminder to rotate the AK/SK and MaaS API key if they were ever pasted into chat.

## Bundled Resources

### Local automation (added 2026-05)

- `credential_form.py` — Tkinter GUI for credential input (dark theme, password masking, SSH key browser). Saves to `credential.skill` (JSON, mode 600). Run once per operator or when credentials rotate.
- `deploy.py` — Python orchestrator for all 17 deployment steps. Reads `credential.skill`, generates secrets on first run, persists all state in `deploy_state.json`. Idempotent — safe to re-run after partial failure.
- `deploy_state.json` — auto-generated; stores `REDIS_PWD`, `PG_PWD`, `LITELLM_MASTER_KEY`, `MCP_TOKEN`, ECS IDs, and SSH key path.

### Remote scripts

- [references/deployment-walkthrough.md](references/deployment-walkthrough.md) — full chronological recipe, copy-paste ready.
- [references/aicoding-agent-integration.md](references/aicoding-agent-integration.md) — Claude Code + ccr + LiteLLM + isolation.
- [references/searxng-mcp.md](references/searxng-mcp.md) — FastMCP HTTP transport details.
- [references/laptop-client-onboarding.md](references/laptop-client-onboarding.md) — onboarding additional client laptops onto an already-running gateway.
- [references/troubleshooting.md](references/troubleshooting.md) — every issue we hit, with the actual fix.
- [assets/config/litellm.config.yaml.example](assets/config/litellm.config.yaml.example)
- [assets/config/litellm.env.example](assets/config/litellm.env.example)
- [assets/config/litellm.service.example](assets/config/litellm.service.example)
- [assets/config/searxng-docker-compose.yml](assets/config/searxng-docker-compose.yml)
- [assets/config/searxng-settings.yml](assets/config/searxng-settings.yml)
- [assets/config/searxng_mcp_server.py](assets/config/searxng_mcp_server.py)
- [assets/config/searxng-mcp.service.example](assets/config/searxng-mcp.service.example)
- [assets/config/claude-code-router.config.json.example](assets/config/claude-code-router.config.json.example)
- [assets/config/claude-glm-wrapper.sh.example](assets/config/claude-glm-wrapper.sh.example)
- [scripts/install_litellm.sh](scripts/install_litellm.sh) — idempotent installer for LiteLLM + Redis + PostgreSQL on a fresh ECS. **Note:** ensure Step 4 (HOME=/opt/litellm prisma regenerate) is present in the Prisma section.
- [scripts/install_searxng_and_mcp.sh](scripts/install_searxng_and_mcp.sh) — idempotent installer for SearXNG + MCP server.
- [scripts/wire_claude_glm.sh](scripts/wire_claude_glm.sh) — operator-side: mints a virtual key, then wires ccr + CLAUDE_CONFIG_DIR + MCP on the laptop the operator deployed from.
- [scripts/install_claude_glm_client.sh](scripts/install_claude_glm_client.sh) — client-side: takes a pre-issued virtual key + bearer token + ECS IP and wires a teammate's laptop onto an already-running gateway.
- [scripts/validate_e2e.sh](scripts/validate_e2e.sh) — runs all health checks in order.
