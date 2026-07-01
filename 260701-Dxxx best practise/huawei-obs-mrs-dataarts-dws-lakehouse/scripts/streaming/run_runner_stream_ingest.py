#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import posixpath
import shlex
import time
from pathlib import Path

import paramiko


RUNNER_HOST = os.environ.get("RUNNER_HOST", "119.8.147.99")
RUNNER_USER = os.environ.get("RUNNER_USER", "root")
REMOTE_ROOT = os.environ.get("RUNNER_REMOTE_ROOT", "/opt/dockone-stream")
SKILL_ROOT = Path(__file__).resolve().parents[2]
WORK_ROOT = Path.cwd()


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        RUNNER_HOST,
        username=RUNNER_USER,
        password=os.environ["DWS_PASSWORD"],
        timeout=15,
        auth_timeout=15,
        banner_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run(client, command: str, env: dict[str, str] | None = None, timeout: int = 600):
    exports = ""
    if env:
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " "
    full = exports + command
    stdin, stdout, stderr = client.exec_command(full, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return {"code": code, "stdout": out, "stderr": err, "command": command}


def mkdirs(sftp, remote_dir: str):
    parts = [p for p in remote_dir.split("/") if p]
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def upload_file(sftp, local: Path, remote: str):
    mkdirs(sftp, posixpath.dirname(remote))
    sftp.put(str(local), remote)


def main():
    files = [
        (SKILL_ROOT / "scripts" / "streaming" / "load_contracts_to_postgres.py", f"{REMOTE_ROOT}/scripts/load_contracts_to_postgres.py"),
        (SKILL_ROOT / "scripts" / "streaming" / "publish_contracts_to_dms_kafka.py", f"{REMOTE_ROOT}/scripts/publish_contracts_to_dms_kafka.py"),
        (SKILL_ROOT / "assets" / "sql" / "billing_contracts_schema.sql", f"{REMOTE_ROOT}/assets/sql/billing_contracts_schema.sql"),
        (WORK_ROOT / "dockone-stream-run" / "data" / "contracts.csv", f"{REMOTE_ROOT}/data/contracts.csv"),
    ]
    client = connect()
    summary = {"runner": RUNNER_HOST, "uploaded": [], "steps": []}
    try:
        sftp = client.open_sftp()
        try:
            for local, remote in files:
                upload_file(sftp, local, remote)
                summary["uploaded"].append({"remote": remote, "bytes": local.stat().st_size})
        finally:
            sftp.close()

        commands = [
            "python3 -m pip install --break-system-packages -q psycopg2-binary kafka-python",
            f"python3 {REMOTE_ROOT}/scripts/load_contracts_to_postgres.py --csv {REMOTE_ROOT}/data/contracts.csv --replace --summary {REMOTE_ROOT}/contracts-rds-load-summary.json",
            f"python3 {REMOTE_ROOT}/scripts/publish_contracts_to_dms_kafka.py --source db --topic {shlex.quote(os.environ.get('DMS_KAFKA_TOPIC','dockone.billing.contracts'))} --bootstrap-servers 192.168.11.202:9093 --summary {REMOTE_ROOT}/contracts-kafka-publish-summary.json",
        ]
        env = {
            "RDS_PGHOST": os.environ.get("RDS_PGHOST", "192.168.6.172"),
            "RDS_PGPORT": "5432",
            "RDS_PGDATABASE": os.environ.get("RDS_PGDATABASE", "postgres"),
            "RDS_PGUSER": os.environ.get("RDS_PGUSER", "root"),
            "RDS_PGPASSWORD": os.environ["RDS_PGPASSWORD"],
            "DMS_KAFKA_TOPIC": os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts"),
        }
        for command in commands:
            started = time.time()
            result = run(client, command, env=env, timeout=1200)
            result["duration_seconds"] = round(time.time() - started, 2)
            summary["steps"].append({k: v for k, v in result.items() if k != "command"})
            if result["code"] != 0:
                raise SystemExit(json.dumps(summary, indent=2, ensure_ascii=False))

        # Pull summaries back for local evidence.
        sftp = client.open_sftp()
        try:
            for name in ["contracts-rds-load-summary.json", "contracts-kafka-publish-summary.json"]:
                remote = f"{REMOTE_ROOT}/{name}"
                local = WORK_ROOT / "runs" / name
                local.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote, str(local))
        finally:
            sftp.close()
    finally:
        client.close()

    (WORK_ROOT / "runs").mkdir(parents=True, exist_ok=True)
    path = WORK_ROOT / "runs" / "runner-stream-ingest-summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"path": str(path), "steps": [{"code": s["code"], "duration_seconds": s["duration_seconds"]} for s in summary["steps"]]}, indent=2))


if __name__ == "__main__":
    main()
