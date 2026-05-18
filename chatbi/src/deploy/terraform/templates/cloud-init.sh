#!/bin/bash
set -euo pipefail
exec > /var/log/cloud-init-chatbi.log 2>&1

echo "=== ChatBI Cloud-Init Started: $(date) ==="

# ── System Setup ──────────────────────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  docker.io docker-compose-plugin \
  nginx certbot python3-certbot-nginx \
  postgresql-client \
  python3-pip \
  git curl jq

systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

# ── Mount Data Disk ───────────────────────────────────────────────────────
DISK=$(lsblk -nd -o NAME,SIZE | awk '$2=="200G"{print "/dev/"$1}' | head -1)
if [ -n "$DISK" ] && ! blkid "$DISK" >/dev/null 2>&1; then
  mkfs.ext4 "$DISK"
  mkdir -p /data
  echo "$DISK /data ext4 defaults 0 2" >> /etc/fstab
  mount -a
fi
mkdir -p /data/chatbi /data/superset /data/logs

# ── Write Application Config ──────────────────────────────────────────────
cat > /data/chatbi/.env << 'ENVEOF'
LLM_API_KEY=${llm_api_key}
LLM_BASE_URL=${llm_base_url}
LLM_MODEL=${llm_model}
DB_HOST=${dws_host}
DB_PORT=${dws_port}
DB_NAME=${dws_db}
DB_USER=${dws_username}
DB_PASSWORD=${dws_password}
OBS_BUCKET=${obs_bucket}
OBS_REGION=${obs_region}
ENVEOF

# ── Docker Compose ────────────────────────────────────────────────────────
cat > /data/docker-compose.yml << 'COMPOSEEOF'
version: "3.9"

services:
  chatbi-backend:
    image: python:3.12-slim
    container_name: chatbi-backend
    restart: unless-stopped
    working_dir: /app
    volumes:
      - /opt/chatbi/backend:/app
    env_file:
      - /data/chatbi/.env
    ports:
      - "8001:8000"
    command: >
      bash -c "pip install fastapi uvicorn[standard] 'openai==1.57.0' 'httpx==0.27.2'
               psycopg2-binary python-dotenv pydantic &&
               uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  superset:
    image: apache/superset:4.0.2
    container_name: chatbi-superset
    restart: unless-stopped
    environment:
      SUPERSET_SECRET_KEY: "${superset_secret}"
      DATABASE_URL: "postgresql+psycopg2://${dws_username}:${dws_password}@${dws_host}:${dws_port}/${dws_db}"
    ports:
      - "8088:8088"
    volumes:
      - /data/superset:/app/superset_home
    command: >
      bash -c "superset db upgrade &&
               superset fab create-admin --username admin --firstname Admin
                 --lastname Admin --email admin@chatbi.local
                 --password Chatbi2024! &&
               superset init &&
               gunicorn --bind 0.0.0.0:8088 --workers 4
                 --timeout 120 'superset.app:create_app()'"

COMPOSEEOF

# ── Deploy Backend Code ───────────────────────────────────────────────────
mkdir -p /opt/chatbi/backend

cat > /opt/chatbi/backend/main.py << 'PYEOF'
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv("/data/chatbi/.env")

from nl2sql import generate_sql, generate_insight
from db_dws import execute_query
from session import add_turn, clear_session, format_history
from chart_advisor import advise_chart
from cache import get as cache_get, set as cache_set

app = FastAPI(title="ChatBI Production API")
app.add_middleware(CORSMiddleware,
  allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    question: str
    session_id: str

@app.get("/health")
def health():
    return {"status": "ok", "mode": "production-dws"}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "question is empty")
    cached = cache_get(question)
    if cached:
        return {**cached, "cached": True}
    history_text = format_history(req.session_id)
    sql, rows, error_msg = "", [], None
    for attempt in range(3):
        try:
            sql = await generate_sql(question, history_text,
                                     error_msg if attempt > 0 else "")
            rows = execute_query(sql)
            error_msg = None
            break
        except Exception as e:
            error_msg = str(e)
    if error_msg:
        return {"sql": sql, "result": [], "chart": None,
                "insight": f"查询失败，请换一种描述方式。({error_msg[:100]})",
                "cached": False, "error": error_msg}
    chart = advise_chart(sql, rows)
    insight = await generate_insight(question, sql, rows)
    add_turn(req.session_id, "user", question)
    add_turn(req.session_id, "assistant", insight, sql)
    resp = {"sql": sql, "result": rows, "chart": chart,
            "insight": insight, "cached": False, "error": None}
    cache_set(question, resp)
    return resp

@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    clear_session(session_id)
    return {"status": "cleared"}
PYEOF

cat > /opt/chatbi/backend/db_dws.py << 'PYEOF'
import os
import psycopg2
import psycopg2.extras
from typing import Any

_conn = None

def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "8000")),
            dbname=os.getenv("DB_NAME", "chatbi"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            connect_timeout=10,
        )
        _conn.autocommit = True
    return _conn

def execute_query(sql: str) -> list[dict[str, Any]]:
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchmany(1000)
        result = []
        for row in rows:
            d = dict(row)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            result.append(d)
        return result
PYEOF

# Copy shared modules (nl2sql, schema_registry, session, chart_advisor, cache)
# These are identical to the sandbox versions except nl2sql uses DWS-compatible SQL
# They will be mounted from /opt/chatbi/backend — place them there during CI/CD
# or use the deploy script to scp them from the sandbox source tree.

# ── Nginx Config ──────────────────────────────────────────────────────────
cat > /etc/nginx/sites-available/chatbi << 'NGINXEOF'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 50M;
    proxy_read_timeout 120s;

    location / {
        root /opt/chatbi/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /superset/ {
        proxy_pass http://127.0.0.1:8088/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/chatbi /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
mkdir -p /opt/chatbi/frontend/dist
echo '<html><body><h2>ChatBI - Frontend deploying...</h2></body></html>' > /opt/chatbi/frontend/dist/index.html
nginx -t && systemctl reload nginx

# ── Start Services ────────────────────────────────────────────────────────
cd /data && docker compose up -d

echo "=== ChatBI Cloud-Init Completed: $(date) ==="
echo "ChatBI Backend: http://$(curl -s ifconfig.me)"
echo "Superset:       http://$(curl -s ifconfig.me)/superset"
