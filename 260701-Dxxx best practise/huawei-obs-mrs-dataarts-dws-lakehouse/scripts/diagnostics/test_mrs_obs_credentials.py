#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os

import paramiko


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test explicit OBS credentials on an MRS node without printing secrets.")
    parser.add_argument("--runner-ip", default=os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99"))
    parser.add_argument("--host", default=os.environ.get("MRS_FLINK_MASTER_IP", "192.168.12.66"))
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET", "hwstaff-retail-lakehouse-09d63c-20260622"))
    parser.add_argument("--prefix", default="jobs/")
    parser.add_argument("--timeout-seconds", type=int, default=180)
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
    remote_script = r'''
import json
import os
import shlex

import paramiko

host = os.environ["MRS_HOST"]
password = os.environ["MRS_PASSWORD"]
bucket = os.environ["OBS_BUCKET"]
prefix = os.environ["OBS_PREFIX"]
ak = os.environ["OBS_AK"]
sk = os.environ["OBS_SK"]
token = os.environ.get("OBS_TOKEN", "")

inner = (
    "set +x; "
    "source /opt/Bigdata/client/bigdata_env >/tmp/dockone_obs_test_env.log 2>&1; "
    "export HADOOP_USER_NAME=omm; "
    "hadoop fs "
    "-Dfs.obs.security.provider= "
    f"-Dfs.obs.access.key={shlex.quote(ak)} "
    f"-Dfs.obs.secret.key={shlex.quote(sk)} "
    + (f"-Dfs.obs.session.token={shlex.quote(token)} " if token else "")
    + f"-ls {shlex.quote('obs://' + bucket + '/' + prefix.strip('/') + '/')} 2>&1 | head -n 30"
)
cmd = "su - omm -s /bin/bash -c " + shlex.quote(inner)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username="root", password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
try:
    stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    print(json.dumps({"code": code, "stdout": out, "stderr": err}, ensure_ascii=False))
finally:
    c.close()
'''
    remote_script_b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    command = (
        f"MRS_HOST={quote(args.host)} "
        f"MRS_PASSWORD={quote(os.environ['MRS_PASSWORD'])} "
        f"OBS_BUCKET={quote(args.bucket)} "
        f"OBS_PREFIX={quote(args.prefix)} "
        f"OBS_AK={quote(os.environ['HUAWEICLOUD_ACCESS_KEY'])} "
        f"OBS_SK={quote(os.environ['HUAWEICLOUD_SECRET_KEY'])} "
        f"OBS_TOKEN={quote(os.environ.get('HUAWEICLOUD_SECURITY_TOKEN') or '')} "
        f"python3 -c \"import base64; exec(base64.b64decode('{remote_script_b64}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(args.runner_ip, "root", os.environ["DWS_PASSWORD"], command, args.timeout_seconds + 90)
    print(json.dumps({"runner_exit_code": code, "stdout": stdout, "stderr": stderr}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
