#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest


def signed_request(method: str, url: str, *, body: dict | None = None) -> tuple[int, dict]:
    ak = os.environ.get("HUAWEICLOUD_ACCESS_KEY")
    sk = os.environ.get("HUAWEICLOUD_SECRET_KEY")
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID")
    if not (ak and sk and project_id):
        raise RuntimeError("HUAWEICLOUD_ACCESS_KEY, HUAWEICLOUD_SECRET_KEY, and HUAWEICLOUD_PROJECT_ID are required.")

    raw_body = json.dumps(body).encode("utf-8") if body is not None else None
    parts = urllib.parse.urlsplit(url)
    request = SdkRequest(
        method=method,
        schema=parts.scheme,
        host=parts.netloc,
        resource_path=parts.path or "/",
        query_params=urllib.parse.parse_qsl(parts.query, keep_blank_values=True),
        header_params={"Content-Type": "application/json"},
        body=raw_body or b"",
    )
    signed = BasicCredentials(ak, sk, project_id).sign_request(request)
    req = urllib.request.Request(url, data=raw_body, headers=signed.header_params, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = response.read()
        return response.status, json.loads(payload.decode("utf-8")) if payload else {}


def main() -> int:
    region = os.environ.get("HUAWEICLOUD_REGION", "la-north-2")
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID")
    url = f"https://ecs.{region}.myhuaweicloud.com/v1/{project_id}/cloudservers/detail?limit=1"
    try:
        status, payload = signed_request("GET", url)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        print(f"AK/SK validation failed: HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"AK/SK validation failed: {exc}", file=sys.stderr)
        return 1
    servers = payload.get("servers") or payload.get("cloudservers") or []
    print(f"AK/SK validation succeeded: HTTP {status}; ecs_sample_count={len(servers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
