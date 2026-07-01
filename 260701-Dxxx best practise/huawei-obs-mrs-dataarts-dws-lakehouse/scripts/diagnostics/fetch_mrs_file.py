#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

import paramiko


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch a small file from an MRS private node through the runner ECS.")
    parser.add_argument("--runner-ip", default=os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--remote-path", required=True)
    parser.add_argument("--out", "--output", dest="out", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
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
import shlex

import paramiko

host = os.environ["MRS_HOST"]
password = os.environ["MRS_PASSWORD"]
remote_path = os.environ["REMOTE_PATH"]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username="root", password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
try:
    try:
        sftp = c.open_sftp()
        try:
            with sftp.open(remote_path, "rb") as handle:
                payload = base64.b64encode(handle.read()).decode("ascii")
            size = sftp.stat(remote_path).st_size
        finally:
            sftp.close()
    except Exception:
        py = (
            "import base64, pathlib, sys; "
            f"p=pathlib.Path({remote_path!r}); "
            "sys.stdout.write(str(p.stat().st_size)+'\\n'); "
            "sys.stdout.write(base64.b64encode(p.read_bytes()).decode('ascii'))"
        )
        stdin, stdout, stderr = c.exec_command("python3 -c " + shlex.quote(py), timeout=120)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if code != 0:
            raise RuntimeError(err or out)
        first, payload = out.split("\n", 1)
        size = int(first)
    print(json.dumps({"remote_path": remote_path, "size": size, "payload_b64": payload}, ensure_ascii=False))
finally:
    c.close()
'''
    remote_script_b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    command = (
        f"MRS_HOST={quote(args.host)} "
        f"MRS_PASSWORD={quote(os.environ['MRS_PASSWORD'])} "
        f"REMOTE_PATH={quote(args.remote_path)} "
        f"python3 -c \"import base64; exec(base64.b64decode('{remote_script_b64}').decode('utf-8'))\""
    )
    code, stdout, stderr = ssh_exec(args.runner_ip, "root", os.environ["DWS_PASSWORD"], command, args.timeout_seconds + 60)
    if code != 0:
        raise SystemExit(json.dumps({"exit_code": code, "stderr": stderr, "stdout": stdout[-2000:]}, ensure_ascii=False))
    data = json.loads(stdout)
    target = Path(args.out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(data["payload_b64"]))
    print(json.dumps({"remote_path": args.remote_path, "out": str(target), "bytes": target.stat().st_size}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
