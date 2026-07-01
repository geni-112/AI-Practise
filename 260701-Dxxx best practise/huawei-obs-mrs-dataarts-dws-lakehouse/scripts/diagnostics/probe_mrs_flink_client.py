#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os

import paramiko


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int = 180) -> tuple[int, str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    finally:
        client.close()


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    runner = os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99")
    master = os.environ.get("MRS_FLINK_MASTER_IP", "192.168.12.66")
    runner_password = os.environ["DWS_PASSWORD"]
    mrs_password = os.environ["MRS_PASSWORD"]
    remote_script = r"""
import json
import os
import paramiko

master = os.environ["MRS_MASTER"]
password = os.environ["MRS_PASSWORD"]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(master, username="root", password=password, look_for_keys=False, allow_agent=False, timeout=20, banner_timeout=20, auth_timeout=20)
try:
    cmd = r'''
hostname
find /opt /srv -name sql-client.sh -o -name flink 2>/dev/null | head -n 80
if [ -d /opt/client ]; then ls -ld /opt/client; fi
if [ -d /opt/Bigdata/client ]; then ls -ld /opt/Bigdata/client; fi
find /opt -name bigdata_env 2>/dev/null | head -n 20
echo '--- flink-conf ports ---'
grep -R "port" -n /opt/Bigdata/client/Flink/flink/conf/flink-conf.yaml /opt/Bigdata/FusionInsight_Flink_8.5.0/install/FusionInsight-Flink-1.17.1/flink/conf/flink-conf.yaml 2>/dev/null | head -n 120
echo '--- flink-conf execution/rest/yarn ---'
grep -E "^(execution|rest|jobmanager|yarn|high-availability|security|env\\.|classloader)" -n /opt/Bigdata/client/Flink/flink/conf/flink-conf.yaml 2>/dev/null | head -n 180
echo '--- listening ports 20xxx/28xxx/32xxx ---'
ss -ltnp 2>/dev/null | grep -E ':(20[0-9][0-9][0-9]|28[0-9][0-9][0-9]|32[0-9][0-9][0-9])\\b' | head -n 200 || true
echo '--- all listening ports sample ---'
ss -ltnp 2>/dev/null | head -n 120 || netstat -tlnp 2>/dev/null | head -n 120 || true
echo '--- flink processes ---'
ps -ef | grep -i flink | grep -v grep | head -n 80 || true
echo '--- javac and connector jars ---'
command -v javac || true
find /opt/Bigdata -path '*bin/javac' 2>/dev/null | head -n 20
find /opt/Bigdata/client/Flink/flink -iname '*kafka*.jar' -o -iname '*connector*.jar' 2>/dev/null | head -n 120
'''
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    code = stdout.channel.recv_exit_status()
    print(json.dumps({"code": code, "stdout": stdout.read().decode("utf-8", "replace"), "stderr": stderr.read().decode("utf-8", "replace")}, ensure_ascii=False))
finally:
    c.close()
"""
    encoded = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    command = (
        f"MRS_MASTER={quote(master)} MRS_PASSWORD={quote(mrs_password)} "
        f"python3 -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(runner, "root", runner_password, command, timeout=240)
    print(json.dumps({"exit_code": code, "stdout": stdout, "stderr": stderr}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
