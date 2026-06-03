from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Auth-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def response_to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return {}


def dli_client():
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkdli.v1 import DliClient
        from huaweicloudsdkdli.v1.region.dli_region import DliRegion
    except ImportError as exc:
        raise SystemExit("Install Huawei Cloud SDK first: pip install huaweicloudsdkcore huaweicloudsdkdli") from exc

    region = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        os.environ["HUAWEICLOUD_PROJECT_ID"],
    )
    return (
        DliClient.new_builder()
        .with_credentials(credentials)
        .with_region(DliRegion.value_of(region))
        .build()
    )


def submit_with_sdk(client: Any, payload: dict) -> dict:
    from huaweicloudsdkdli.v1 import CreateSparkJobRequest, CreateSparkJobRequestBody

    body = CreateSparkJobRequestBody(
        file=payload.get("file"),
        class_name=payload.get("className") or "",
        args=payload.get("args"),
        sc_type=payload.get("sc_type"),
        conf=payload.get("conf"),
        name=payload.get("name"),
        feature=payload.get("feature"),
        spark_version=payload.get("spark_version"),
        queue=payload.get("queue"),
        auto_recovery=payload.get("auto_recovery"),
        max_retry_times=payload.get("max_retry_times"),
        execution_agency_urn=payload.get("execution_agency_urn") or None,
    )
    return response_to_json(client.create_spark_job(CreateSparkJobRequest(body=body)))


def main():
    parser = argparse.ArgumentParser(description="Submit DLI bronze/silver jobs")
    parser.add_argument("--execute", action="store_true", help="Actually submit. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=0, help="Limit tables for smoke tests. 0 means all.")
    parser.add_argument("--auth", choices=["sdk", "token"], default="sdk", help="DLI auth mode. SDK uses AK/SK.")
    args = parser.parse_args()
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID", "<project-id>")
    endpoint = os.environ.get("DLI_ENDPOINT", "https://dli.<region>.myhuaweicloud.com").rstrip("/")
    token = os.environ.get("HUAWEICLOUD_X_AUTH_TOKEN", "")
    url = f"{endpoint}/v2.0/{project_id}/batches"
    workflow = json.loads((ROOT / "runtime" / "workflow-plan.json").read_text(encoding="utf-8"))
    if args.limit:
        workflow = workflow[: args.limit]

    submitted = []
    client = dli_client() if args.execute and args.auth == "sdk" else None
    for table in workflow:
        for stage in ["bronze_payload", "silver_payload"]:
            payload_path = ROOT / table[stage]
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            if not args.execute:
                print(f"DRY RUN submit {payload['name']} -> {url}")
                continue
            if args.auth == "sdk":
                response = submit_with_sdk(client, payload)
            elif not token:
                raise SystemExit("HUAWEICLOUD_X_AUTH_TOKEN is required for --execute")
            else:
                response = post_json(url, token, payload)
            submitted.append({"name": payload["name"], "response": response})
            print(json.dumps(submitted[-1], indent=2))
            if stage == "bronze_payload":
                print("NOTE: In production, poll bronze to Success before submitting silver.")
                time.sleep(1)
    (ROOT / "runtime" / "submitted-dli-jobs.json").write_text(json.dumps(submitted, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
