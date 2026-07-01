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


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int = 300) -> tuple[int, str, str]:
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


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    runner_host = os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99")
    runner_password = required_env("DWS_PASSWORD")
    mrs_password = required_env("MRS_PASSWORD")
    app_id = os.environ.get("MRS_APP_ID", "application_1782103897202_0033")
    node_ips = os.environ.get(
        "MRS_NODE_IPS",
        "192.168.10.203,192.168.14.95,192.168.0.36,192.168.5.19,192.168.10.69",
    )

    remote_script = r"""
import json
import os
import paramiko

app_id = os.environ["MRS_APP_ID"]
mrs_password = os.environ["MRS_PASSWORD"]
node_ips = [h for h in os.environ["MRS_NODE_IPS"].split(",") if h]

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
for host in node_ips:
    find_cmd = (
        "set -o pipefail; "
        "echo HOST=$(hostname); "
        f"find /srv/BigData /var/log /var/log/Bigdata /tmp -xdev "
        f"\\( -path '*{app_id}*' -o -name '*{app_id}*' \\) "
        "-maxdepth 12 2>/dev/null | head -n 200"
    )
    code, out, err = ssh_exec(host, find_cmd, timeout=180)
    paths = [line for line in out.splitlines() if app_id in line]
    tail_outputs = []
    for path in paths[:20]:
        safe = "'" + path.replace("'", "'\"'\"'") + "'"
        tail_cmd = f"if [ -f {safe} ]; then echo '### FILE {path}'; tail -n 220 {safe}; fi"
        tcode, tout, terr = ssh_exec(host, tail_cmd, timeout=120)
        if tout.strip() or terr.strip():
            tail_outputs.append({"path": path, "code": tcode, "stdout": tout[-20000:], "stderr": terr[-4000:]})
    results.append({"host": host, "find_code": code, "find_stdout": out[-20000:], "find_stderr": err[-4000:], "paths": paths, "tails": tail_outputs})
print(json.dumps(results, ensure_ascii=False))
"""
    encoded = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    remote_command = (
        f"MRS_APP_ID={shell_single_quote(app_id)} "
        f"MRS_NODE_IPS={shell_single_quote(node_ips)} "
        f"MRS_PASSWORD={shell_single_quote(mrs_password)} "
        f"python3 -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(runner_host, "root", runner_password, remote_command, timeout=600)
    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{app_id}-node-log-probe.json"
    path.write_text(
        json.dumps(
            {
                "runner_host": runner_host,
                "app_id": app_id,
                "node_ips": node_ips.split(","),
                "exit_code": code,
                "stdout": stdout,
                "stderr": stderr,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"path": str(path), "exit_code": code, "stdout_bytes": len(stdout), "stderr_bytes": len(stderr)}))


if __name__ == "__main__":
    main()
