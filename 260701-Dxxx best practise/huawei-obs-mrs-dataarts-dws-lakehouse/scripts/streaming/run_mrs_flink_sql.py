#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path

import paramiko


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Flink SQL file on the MRS Flink master via the runner ECS.")
    parser.add_argument("--sql", required=True)
    parser.add_argument("--master-ip", default=os.environ.get("MRS_FLINK_MASTER_IP", "192.168.12.66"))
    parser.add_argument("--runner-ip", default=os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--help-only", action="store_true")
    parser.add_argument("--gateway-endpoint", default=os.environ.get("MRS_FLINK_SQL_GATEWAY_ENDPOINT"))
    return parser.parse_args()


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int) -> tuple[int, str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    finally:
        client.close()


def main() -> None:
    args = parse_args()
    sql_text = Path(args.sql).read_text(encoding="utf-8")
    runner_password = os.environ["DWS_PASSWORD"]
    mrs_password = os.environ["MRS_PASSWORD"]
    remote_script = r"""
import base64
import json
import os
import shlex
import time
import paramiko

master = os.environ["MRS_MASTER"]
password = os.environ["MRS_PASSWORD"]
sql_text = base64.b64decode(os.environ["FLINK_SQL_B64"]).decode("utf-8")
help_only = os.environ.get("HELP_ONLY") == "1"
gateway_endpoint = os.environ.get("GATEWAY_ENDPOINT")
remote_path = f"/tmp/dockone_flink_contracts_{int(time.time())}.sql"
conf_files = [
    "/opt/Bigdata/client/Flink/flink/conf/flink-conf.yaml",
    "/opt/Bigdata/FusionInsight_Flink_8.5.0/install/FusionInsight-Flink-1.17.1/flink/conf/flink-conf.yaml",
]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(master, username="root", password=password, look_for_keys=False, allow_agent=False, timeout=20, banner_timeout=20, auth_timeout=20)
try:
    if not help_only:
        encoded_sql = base64.b64encode(sql_text.encode("utf-8")).decode("ascii")
        w_stdin, w_stdout, w_stderr = c.exec_command(f"base64 -d > {shlex.quote(remote_path)} && chmod 0644 {shlex.quote(remote_path)}", timeout=120)
        w_stdin.write(encoded_sql)
        w_stdin.channel.shutdown_write()
        write_code = w_stdout.channel.recv_exit_status()
        if write_code != 0:
            raise RuntimeError(
                "failed to write SQL file: "
                + w_stdout.read().decode("utf-8", "replace")
                + w_stderr.read().decode("utf-8", "replace")
            )
    fix_owner_cmd = (
        "if id omm >/dev/null 2>&1; then "
        "chown omm:wheel /opt/Bigdata/client/Flink/flink/conf/flink-conf.yaml 2>/dev/null || true; "
        "chmod 640 /opt/Bigdata/client/Flink/flink/conf/flink-conf.yaml 2>/dev/null || true; "
        "fi"
    )
    c.exec_command(fix_owner_cmd, timeout=60)
    patched = False
    if not help_only and not gateway_endpoint:
        patch_parts = []
        for conf in conf_files:
            backup = conf + ".dockonebak"
            patch_parts.append(
                f"if [ -f {shlex.quote(conf)} ]; then "
                f"cp -p {shlex.quote(conf)} {shlex.quote(backup)} && "
                f"sed -i 's/^security.networkwide.listen.restrict:.*/security.networkwide.listen.restrict: false/' {shlex.quote(conf)} && "
                f"grep -q '^security.networkwide.listen.restrict:' {shlex.quote(conf)} || echo 'security.networkwide.listen.restrict: false' >> {shlex.quote(conf)} && "
                f"sed -i 's/^rest.bind-port:.*/rest.bind-port: 20000-20100/' {shlex.quote(conf)} && "
                f"grep -q '^rest.bind-port:' {shlex.quote(conf)} || echo 'rest.bind-port: 20000-20100' >> {shlex.quote(conf)}; "
                "fi"
            )
        p_stdin, p_stdout, p_stderr = c.exec_command("; ".join(patch_parts), timeout=120)
        patch_code = p_stdout.channel.recv_exit_status()
        if patch_code != 0:
            raise RuntimeError(
                "failed to patch Flink conf: "
                + p_stdout.read().decode("utf-8", "replace")
                + p_stderr.read().decode("utf-8", "replace")
            )
        patched = True
    base = (
        "source /opt/Bigdata/client/bigdata_env >/tmp/dockone_flink_env.log 2>&1; "
        "export HADOOP_USER_NAME=omm; "
        "export HADOOP_CONF_DIR=${HADOOP_CONF_DIR:-/opt/Bigdata/client/HDFS/hadoop/etc/hadoop}; "
    )
    if help_only:
        inner = base + "/opt/Bigdata/client/Flink/flink/bin/sql-client.sh --help | head -n 120"
    elif gateway_endpoint:
        inner = base + f"/opt/Bigdata/client/Flink/flink/bin/sql-client.sh gateway -e {shlex.quote(gateway_endpoint)} -f {shlex.quote(remote_path)}"
    else:
        inner = base + f"/opt/Bigdata/client/Flink/flink/bin/sql-client.sh -f {shlex.quote(remote_path)}"
    cmd = "su - omm -s /bin/bash -c " + shlex.quote(inner)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=int(os.environ.get("REMOTE_TIMEOUT", "900")))
    code = stdout.channel.recv_exit_status()
    print(json.dumps({"code": code, "remote_sql": remote_path if not help_only else None, "stdout": stdout.read().decode("utf-8", "replace"), "stderr": stderr.read().decode("utf-8", "replace")}, ensure_ascii=False))
    if patched:
        restore_parts = []
        for conf in conf_files:
            backup = conf + ".dockonebak"
            restore_parts.append(
                f"if [ -f {shlex.quote(backup)} ]; then mv {shlex.quote(backup)} {shlex.quote(conf)}; chown omm:wheel {shlex.quote(conf)} 2>/dev/null || true; fi"
            )
        c.exec_command("; ".join(restore_parts), timeout=120)
finally:
    c.close()
"""
    encoded_script = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    encoded_sql = base64.b64encode(sql_text.encode("utf-8")).decode("ascii")
    command = (
        f"MRS_MASTER={quote(args.master_ip)} "
        f"MRS_PASSWORD={quote(mrs_password)} "
        f"FLINK_SQL_B64={quote(encoded_sql)} "
        f"HELP_ONLY={'1' if args.help_only else '0'} "
        f"GATEWAY_ENDPOINT={quote(args.gateway_endpoint or '')} "
        f"REMOTE_TIMEOUT={args.timeout_seconds} "
        f"python3 -c \"import base64; exec(base64.b64decode('{encoded_script}').decode('utf-8'))\""
    )
    started = time.perf_counter()
    code, stdout, stderr = ssh_exec(args.runner_ip, "root", runner_password, command, timeout=args.timeout_seconds + 120)
    result = {
        "exit_code": code,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "stdout": stdout,
        "stderr": stderr,
    }
    Path("runs").mkdir(exist_ok=True)
    out = Path("runs") / ("mrs-flink-sql-help.json" if args.help_only else "mrs-flink-sql-run.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(out), "exit_code": code, "duration_seconds": result["duration_seconds"], "stdout_bytes": len(stdout), "stderr_bytes": len(stderr)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
