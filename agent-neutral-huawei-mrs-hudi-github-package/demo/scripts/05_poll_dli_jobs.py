from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_STATES = {"Success", "success", "FINISHED", "available"}
FAILURE_STATES = {"Dead", "dead", "Error", "error", "FAILED", "failed", "killed"}


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Auth-Token": token}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
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


def get_state_with_sdk(client: Any, batch_id: str) -> str:
    from huaweicloudsdkdli.v1 import ShowSparkJobStatusRequest

    data = response_to_json(client.show_spark_job_status(ShowSparkJobStatusRequest(batch_id=batch_id)))
    return data.get("state") or data.get("status") or data.get("job_state") or "unknown"


def main():
    parser = argparse.ArgumentParser(description="Poll DLI batch job states")
    parser.add_argument("--execute", action="store_true", help="Actually poll. Default is dry-run.")
    parser.add_argument("--interval-seconds", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=30)
    parser.add_argument("--auth", choices=["sdk", "token"], default="sdk", help="DLI auth mode. SDK uses AK/SK.")
    args = parser.parse_args()
    submitted_path = ROOT / "runtime" / "submitted-dli-jobs.json"
    submitted = json.loads(submitted_path.read_text(encoding="utf-8")) if submitted_path.exists() else []
    if not args.execute:
        print(f"DRY RUN would poll {len(submitted)} submitted jobs via /v2.0/{{project_id}}/batches/{{batch_id}}/state")
        return
    token = os.environ.get("HUAWEICLOUD_X_AUTH_TOKEN", "")
    project_id = os.environ["HUAWEICLOUD_PROJECT_ID"]
    endpoint = os.environ["DLI_ENDPOINT"].rstrip("/")
    client = dli_client() if args.auth == "sdk" else None
    for _ in range(args.max_polls):
        unfinished = []
        states = []
        for item in submitted:
            response = item["response"]
            batch_id = response.get("id") or response.get("appId") or response.get("job_id")
            if isinstance(batch_id, list):
                batch_id = batch_id[0]
            if args.auth == "sdk":
                state = get_state_with_sdk(client, batch_id)
            else:
                if not token:
                    raise SystemExit("HUAWEICLOUD_X_AUTH_TOKEN is required for token polling")
                state_url = f"{endpoint}/v2.0/{project_id}/batches/{batch_id}/state"
                state = get_json(state_url, token).get("state", "unknown")
            states.append({"name": item["name"], "batch_id": batch_id, "state": state})
            if state in FAILURE_STATES:
                raise SystemExit(f"DLI job failed: {states[-1]}")
            if state not in SUCCESS_STATES:
                unfinished.append(states[-1])
        print(json.dumps(states, indent=2))
        if not unfinished:
            return
        time.sleep(args.interval_seconds)
    raise SystemExit("Timed out waiting for DLI jobs")


if __name__ == "__main__":
    main()
