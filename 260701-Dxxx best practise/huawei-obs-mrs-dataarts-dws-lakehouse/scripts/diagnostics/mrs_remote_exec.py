#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os

import paramiko


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a shell command on an MRS node through the runner ECS.")
    parser.add_argument("--runner-ip", default=os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="root")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--command", required=True)
    return parser.parse_args()


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int) -> tuple[int, str, str]:
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
    args = parse_args()
    remote_script = r'''
import base64
import json
import os

import paramiko

host = os.environ["MRS_HOST"]
user = os.environ["MRS_USER"]
password = os.environ["MRS_PASSWORD"]
timeout = int(os.environ["REMOTE_TIMEOUT"])
command = base64.b64decode(os.environ["REMOTE_COMMAND_B64"]).decode("utf-8")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username=user, password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
try:
    stdin, stdout, stderr = c.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    print(json.dumps({
        "host": host,
        "code": code,
        "stdout": stdout.read().decode("utf-8", "replace"),
        "stderr": stderr.read().decode("utf-8", "replace"),
    }, ensure_ascii=False))
finally:
    c.close()
'''
    remote_script_b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    remote_command_b64 = base64.b64encode(args.command.encode("utf-8")).decode("ascii")
    command = (
        f"MRS_HOST={quote(args.host)} "
        f"MRS_USER={quote(args.user)} "
        f"MRS_PASSWORD={quote(os.environ['MRS_PASSWORD'])} "
        f"REMOTE_TIMEOUT={args.timeout_seconds} "
        f"REMOTE_COMMAND_B64={quote(remote_command_b64)} "
        f"python3 -c \"import base64; exec(base64.b64decode('{remote_script_b64}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(args.runner_ip, "root", os.environ["DWS_PASSWORD"], command, args.timeout_seconds + 90)
    print(json.dumps({"runner_exit_code": code, "stdout": stdout, "stderr": stderr}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
