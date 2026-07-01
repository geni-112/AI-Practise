#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import posixpath
import shlex
import time
from datetime import datetime
from pathlib import Path

import paramiko
from obs import ObsClient


RUNNER_HOST = os.environ.get("RUNNER_HOST", "119.8.147.99")
REMOTE_ROOT = "/opt/dockone-stream"
TOPIC = os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts")
BOOTSTRAP = os.environ.get("DMS_KAFKA_BOOTSTRAP_SERVERS", "192.168.11.202:9093")
BUCKET = os.environ.get("DEPLOYMENT_OBS_BUCKET")
REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
LOCAL_OUT = Path("runs") / "streamed_contracts_from_kafka.jsonl"


CONSUMER = r'''
import json
import sys
import time
from kafka import KafkaConsumer

topic = sys.argv[1]
bootstrap = sys.argv[2]
target = int(sys.argv[3])
out = sys.argv[4]

consumer = KafkaConsumer(
    topic,
    bootstrap_servers=bootstrap.split(","),
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    group_id="dockone-runner-obs-" + str(int(time.time())),
    consumer_timeout_ms=20000,
)
count = 0
bytes_out = 0
with open(out, "wb") as handle:
    for msg in consumer:
        handle.write(msg.value.rstrip(b"\n") + b"\n")
        count += 1
        bytes_out += len(msg.value) + 1
        if count >= target:
            break
consumer.close()
print(json.dumps({"messages": count, "bytes": bytes_out, "out": out}))
if count < target:
    sys.exit(2)
'''


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        RUNNER_HOST,
        username="root",
        password=os.environ["DWS_PASSWORD"],
        timeout=15,
        auth_timeout=15,
        banner_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run(client, command: str, timeout: int = 900):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def upload_obs(local_path: Path):
    if not BUCKET:
        raise SystemExit("DEPLOYMENT_OBS_BUCKET is required")
    key = (
        "raw/dockone_exampleapp/"
        "kfk.prd.cdc.dockone_exampleapp.billing.contracts/"
        f"part-kafka-runner-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    )
    client = ObsClient(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY"],
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_KEY"],
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None,
        server=f"https://obs.{REGION}.myhuaweicloud.com",
    )
    try:
        resp = client.putFile(BUCKET, key, str(local_path))
        if getattr(resp, "status", 500) >= 300:
            raise RuntimeError(f"OBS upload failed status={resp.status}")
    finally:
        client.close()
    return f"obs://{BUCKET}/{key}"


def main():
    Path("runs").mkdir(exist_ok=True)
    remote_script = f"{REMOTE_ROOT}/scripts/consume_kafka_to_jsonl.py"
    remote_out = f"{REMOTE_ROOT}/streamed/part-00001.json"
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            try:
                sftp.mkdir(f"{REMOTE_ROOT}/streamed")
            except OSError:
                pass
            with sftp.open(remote_script, "w") as handle:
                handle.write(CONSUMER)
        finally:
            sftp.close()
        cmd = (
            f"python3 {remote_script} {shlex.quote(TOPIC)} "
            f"{shlex.quote(BOOTSTRAP)} 9900 {shlex.quote(remote_out)}"
        )
        started = time.time()
        code, out, err = run(client, cmd)
        if code != 0:
            raise SystemExit(json.dumps({"code": code, "stdout": out, "stderr": err}, indent=2))
        sftp = client.open_sftp()
        try:
            sftp.get(remote_out, str(LOCAL_OUT))
        finally:
            sftp.close()
    finally:
        client.close()

    obs_uri = upload_obs(LOCAL_OUT)
    summary = {
        "source": "DMS Kafka",
        "consumer": "runner ECS interim consumer",
        "stdout": out,
        "stderr": err,
        "duration_seconds": round(time.time() - started, 2),
        "local_jsonl": str(LOCAL_OUT),
        "local_bytes": LOCAL_OUT.stat().st_size,
        "obs_uri": obs_uri,
    }
    path = Path("runs") / "runner-kafka-to-obs-summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"path": str(path), "obs_uri": obs_uri, "bytes": summary["local_bytes"]}, indent=2))


if __name__ == "__main__":
    main()
