#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest
from huaweicloudsdkcore.signer.signer import Signer


def parse_args():
    parser = argparse.ArgumentParser(description="Trigger and poll a DataArts Factory job.")
    parser.add_argument("--job-name", required=True, help="DataArts job name, for example dockone_golden_to_dws.")
    parser.add_argument("--workspace-id", default=os.environ.get("DATAARTS_WORKSPACE_ID"))
    parser.add_argument("--project-id", default=os.environ.get("HUAWEICLOUD_PROJECT_ID"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--summary", default=str(Path.cwd() / "dataarts-job-summary.json"))
    return parser.parse_args()


def signed_request(credentials, host, workspace_id, method, path, body=None):
    payload = None if body is None else json.dumps(body, separators=(",", ":"))
    req = SdkRequest(
        method=method,
        schema="https",
        host=host,
        resource_path=path,
        query_params=[],
        header_params={"Content-Type": "application/json", "workspace": workspace_id},
        body=payload,
    )
    signed = Signer(credentials).sign(req)
    response = requests.request(
        method,
        f"https://{host}{signed.uri}",
        headers=signed.header_params,
        data=None if payload is None else payload.encode("utf-8"),
        timeout=90,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"{method} {path} HTTP {response.status_code}: {response.text[:1000]}")
    return response.json() if response.content else {}


def main():
    args = parse_args()
    missing = [name for name, value in {"workspace-id": args.workspace_id, "project-id": args.project_id}.items() if not value]
    if missing:
        raise SystemExit(f"Missing required values: {', '.join(missing)}")
    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        args.project_id,
    )
    host = f"dayu-dlf.{args.region}.myhuaweicloud.com"
    started = time.perf_counter()
    run = signed_request(
        credentials,
        host,
        args.workspace_id,
        "POST",
        f"/v1/{args.project_id}/jobs/{args.job_name}/run-immediate",
        {"jobParams": []},
    )
    instance_id = str(run.get("instanceId") or run.get("instance_id") or run.get("id") or "")
    if not instance_id:
        raise RuntimeError(f"No DataArts instance ID: {run}")

    detail = {}
    status = ""
    for poll in range(1, args.max_polls + 1):
        detail = signed_request(
            credentials,
            host,
            args.workspace_id,
            "GET",
            f"/v1/{args.project_id}/jobs/{args.job_name}/instances/{instance_id}",
        )
        status = str(detail.get("status") or detail.get("instance_status") or "").lower()
        print(json.dumps({"poll": poll, "job": args.job_name, "instance_id": instance_id, "status": status}))
        if status in {"success", "failed", "cancelled", "terminated"}:
            break
        time.sleep(args.poll_seconds)

    summary = {
        "job_name": args.job_name,
        "instance_id": instance_id,
        "status": status,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "detail": detail,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if status != "success":
        raise RuntimeError(f"DataArts job failed: {status}")
    print(json.dumps({k: v for k, v in summary.items() if k != "detail"}, indent=2))


if __name__ == "__main__":
    main()
