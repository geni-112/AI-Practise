from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_REGION = "la-south-2"
DEFAULT_OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"
DEFAULT_DLI_ENDPOINT = "https://dli.la-south-2.myhuaweicloud.com"
DEFAULT_DLI_QUEUE = "dli_demo_min"
MIN_DLI_CU_COUNT = 16


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"{name} is required. Set it in the shell environment, not in source files.")
    return value or ""


def request_json(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-Auth-Token": token},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def ensure_obs_bucket(bucket: str, region: str, endpoint: str, execute: bool) -> None:
    print(f"OBS bucket target: {bucket} region={region} endpoint={endpoint}")
    if not execute:
        print(f"DRY RUN would create/check OBS bucket {bucket}")
        return
    try:
        from obs import ObsClient
    except ImportError as exc:
        raise SystemExit("Install OBS SDK first: pip install -r requirements.txt") from exc

    ak = env("HUAWEICLOUD_ACCESS_KEY", required=True)
    sk = env("HUAWEICLOUD_SECRET_KEY", required=True)
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None
    client = ObsClient(access_key_id=ak, secret_access_key=sk, security_token=security_token, server=endpoint)

    try:
        head = client.headBucket(bucket)
        if getattr(head, "status", 0) in (200, 204):
            print(f"OBS bucket already exists and is accessible: {bucket}")
            return
    except Exception:
        pass

    # The Python OBS SDK accepts location in recent versions. If the SDK version
    # differs, the fallback creates the bucket against the regional endpoint.
    try:
        response = client.createBucket(bucket, location=region)
    except TypeError:
        response = client.createBucket(bucket)
    status = getattr(response, "status", None)
    if status and status >= 300:
        raise RuntimeError(f"OBS bucket creation failed: status={status}, body={getattr(response, 'body', None)}")
    print(f"OBS bucket created: {bucket}")


def dli_client(region: str):
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkdli.v1 import DliClient
        from huaweicloudsdkdli.v1.region.dli_region import DliRegion
    except ImportError as exc:
        raise SystemExit("Install Huawei Cloud SDK first: pip install huaweicloudsdkcore huaweicloudsdkdli") from exc

    ak = env("HUAWEICLOUD_ACCESS_KEY", required=True)
    sk = env("HUAWEICLOUD_SECRET_KEY", required=True)
    project_id = env("HUAWEICLOUD_PROJECT_ID", required=True)
    credentials = BasicCredentials(ak, sk, project_id)
    if os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"):
        credentials.with_security_token(os.environ["HUAWEICLOUD_SECURITY_TOKEN"])
    return (
        DliClient.new_builder()
        .with_credentials(credentials)
        .with_region(DliRegion.value_of(region))
        .build()
    )


def response_to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return {}


def queue_exists_sdk(client: Any, queue_name: str) -> bool:
    from huaweicloudsdkdli.v1 import ListQueuesRequest

    try:
        data = response_to_json(client.list_queues(ListQueuesRequest()))
    except Exception as exc:
        print(f"Could not list DLI queues before create: {type(exc).__name__}: {exc}")
        return False
    queues = data.get("queues") or data.get("queue_info") or []
    return any((q.get("queue_name") or q.get("name") or "").lower() == queue_name.lower() for q in queues)


def ensure_dli_queue_sdk(region: str, queue_name: str, execute: bool, cu_count: int = MIN_DLI_CU_COUNT) -> None:
    payload = {
        "queue_name": queue_name,
        "queue_type": "general",
        "cu_count": cu_count,
        "charging_mode": 1,
        "resource_mode": 0,
        "description": "Minimal Chile POC queue for DLI Spark Hudi CDC demo",
        "platform": "x86_64",
        "feature": "basic",
        "tags": [{"key": "demo", "value": "dockone-dli-hudi"}],
    }
    print(f"DLI queue target: {queue_name} region={region} cu_count={cu_count}")
    if not execute:
        print("DRY RUN would create/check DLI queue with SDK payload:")
        print(json.dumps(payload, indent=2))
        return

    from huaweicloudsdkdli.v1 import CreateQueueRequest, CreateQueueRequestBody

    client = dli_client(region)
    if queue_exists_sdk(client, queue_name):
        print(f"DLI queue already appears to exist: {queue_name}")
        return
    body = CreateQueueRequestBody(**payload)
    response = client.create_queue(CreateQueueRequest(body=body))
    print("DLI queue creation requested:")
    print(json.dumps(response_to_json(response), indent=2))


def queue_exists(project_id: str, endpoint: str, token: str, queue_name: str) -> bool:
    url = f"{endpoint.rstrip('/')}/v1.0/{project_id}/queues"
    try:
        data = request_json("GET", url, token)
    except urllib.error.HTTPError as exc:
        print(f"Could not list DLI queues before create: HTTP {exc.code}")
        return False
    text = json.dumps(data).lower()
    return queue_name.lower() in text


def ensure_dli_queue(project_id: str, endpoint: str, token: str, queue_name: str, execute: bool, cu_count: int = MIN_DLI_CU_COUNT) -> None:
    payload = {
        "queue_name": queue_name,
        "queue_type": "general",
        "cu_count": cu_count,
        "charging_mode": 1,
        "resource_mode": 0,
        "description": "Minimal Chile POC queue for DLI Spark Hudi CDC demo",
        "platform": "x86_64",
        "feature": "basic",
        "tags": [{"key": "demo", "value": "dockone-dli-hudi"}],
    }
    url = f"{endpoint.rstrip('/')}/v1.0/{project_id}/queues"
    print(f"DLI queue target: {queue_name} endpoint={endpoint} cu_count={cu_count}")
    if not execute:
        print("DRY RUN would create/check DLI queue with payload:")
        print(json.dumps(payload, indent=2))
        return
    if queue_exists(project_id, endpoint, token, queue_name):
        print(f"DLI queue already appears to exist: {queue_name}")
        return
    try:
        response = request_json("POST", url, token, payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DLI queue creation failed: HTTP {exc.code} {detail}") from exc
    print("DLI queue creation requested:")
    print(json.dumps(response, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create minimal Huawei Cloud Chile resources for the DLI/Hudi demo.")
    parser.add_argument("--execute", action="store_true", help="Create resources. Default is dry-run.")
    parser.add_argument("--skip-obs", action="store_true")
    parser.add_argument("--skip-dli", action="store_true")
    parser.add_argument("--dli-auth", choices=["sdk", "token"], default="sdk", help="DLI auth mode. SDK uses AK/SK.")
    parser.add_argument("--dli-cu-count", type=int, default=int(os.environ.get("DLI_CU_COUNT", str(MIN_DLI_CU_COUNT))))
    args = parser.parse_args()

    region = env("HUAWEICLOUD_REGION", DEFAULT_REGION)
    if region != DEFAULT_REGION:
        raise SystemExit(f"This demo is pinned to Chile LA-Santiago: {DEFAULT_REGION}. Current HUAWEICLOUD_REGION={region}")

    bucket = env("DEMO_BUCKET", required=True)
    project_id = env("HUAWEICLOUD_PROJECT_ID", required=(not args.skip_dli and args.dli_auth == "token"))
    obs_endpoint = env("OBS_ENDPOINT", DEFAULT_OBS_ENDPOINT)
    dli_endpoint = env("DLI_ENDPOINT", DEFAULT_DLI_ENDPOINT)
    queue_name = env("DLI_QUEUE_NAME", DEFAULT_DLI_QUEUE)
    token = env("HUAWEICLOUD_X_AUTH_TOKEN", required=(args.execute and not args.skip_dli and args.dli_auth == "token"))

    print(f"Deployment mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print("Minimal resource scope: OBS bucket + DLI general queue only. CCE/DWS/CDM/MRS are optional and not created here.")

    if not args.skip_obs:
        ensure_obs_bucket(bucket, region, obs_endpoint, args.execute)
    if not args.skip_dli:
        if args.dli_auth == "sdk":
            env("HUAWEICLOUD_PROJECT_ID", required=args.execute)
            ensure_dli_queue_sdk(region, queue_name, args.execute, args.dli_cu_count)
        else:
            ensure_dli_queue(project_id, dli_endpoint, token, queue_name, args.execute, args.dli_cu_count)


if __name__ == "__main__":
    main()
