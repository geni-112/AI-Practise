#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import paramiko


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int = 180) -> tuple[int, str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        username=user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    )
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    finally:
        client.close()


def main() -> None:
    runner_host = os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99")
    runner_password = required_env("DWS_PASSWORD")
    mrs_password = required_env("MRS_PASSWORD")
    app_id = os.environ.get("MRS_APP_ID", "application_1782103897202_0033")
    master_hosts = [h.strip() for h in os.environ.get("MRS_MASTER_IPS", "192.168.10.203,192.168.14.95").split(",") if h.strip()]

    remote_script = r"""
import json
import os
import paramiko
import subprocess
import sys

app_id = os.environ["MRS_APP_ID"]
mrs_password = os.environ["MRS_PASSWORD"]
master_hosts = [h for h in os.environ["MRS_MASTER_IPS"].split(",") if h]

def ssh_exec(host, command, timeout=240):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username="root", password=mrs_password, look_for_keys=False, allow_agent=False, timeout=20, banner_timeout=20, auth_timeout=20)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    finally:
        client.close()

results = []
for host in master_hosts:
    check_code, check_out, check_err = ssh_exec(host, "hostname && command -v yarn || true", timeout=60)
    yarn_cmd = (
        "export HADOOP_USER_NAME=omm; "
        "source /opt/client/bigdata_env 2>/dev/null || true; "
        "source /opt/Bigdata/client/bigdata_env 2>/dev/null || true; "
        "command -v yarn; "
        f"yarn logs -applicationId {app_id} -am ALL 2>&1 | tail -n 1200"
    )
    code, out, err = ssh_exec(host, yarn_cmd, timeout=300)
    results.append({"host": host, "check_code": check_code, "check_out": check_out[-1000:], "check_err": check_err[-1000:], "code": code, "stdout": out, "stderr": err})
    if out and ("Exception" in out or "Traceback" in out or "ERROR" in out):
        break
print(json.dumps(results, ensure_ascii=False))
"""
    encoded = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    command = (
        "python3 - <<'PY'\n"
        "import importlib.util, subprocess, sys\n"
        "sys.exit(0 if importlib.util.find_spec('paramiko') else 1)\n"
        "PY\n"
    )
    code, _, _ = ssh_exec(runner_host, "root", runner_password, command, timeout=60)
    if code != 0:
        ssh_exec(runner_host, "root", runner_password, "python3 -m pip install --quiet paramiko", timeout=300)

    remote_command = (
        f"MRS_APP_ID='{app_id}' MRS_MASTER_IPS='{','.join(master_hosts)}' "
        f"MRS_PASSWORD='{mrs_password.replace(chr(39), chr(39) + chr(34) + chr(39) + chr(34) + chr(39))}' "
        f"python3 -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(runner_host, "root", runner_password, remote_command, timeout=420)
    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    raw_path = out_dir / f"{app_id}-yarn-log-raw.json"
    result = {
        "runner_host": runner_host,
        "app_id": app_id,
        "master_hosts": master_hosts,
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
    }
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(raw_path), "exit_code": code, "stdout_bytes": len(stdout), "stderr_bytes": len(stderr)}))


if __name__ == "__main__":
    main()
