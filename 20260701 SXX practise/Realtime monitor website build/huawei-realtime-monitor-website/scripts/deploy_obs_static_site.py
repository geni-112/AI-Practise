#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from obs import ErrorDocument, IndexDocument, ObsClient, PutObjectHeader, WebsiteConfiguration

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGION = "la-north-2"


class ApiError(RuntimeError):
    pass


def request_json(method: str, url: str, *, token: str | None = None, body: Any | None = None) -> tuple[int, dict[str, str], Any]:
    headers = {"Content-Type": "application/json;charset=utf8"}
    if token:
        headers["X-Auth-Token"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, dict(response.headers), payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise ApiError(f"HTTP {exc.code} {url}: {detail}") from exc


def get_user_token(region: str) -> dict[str, Any]:
    account = os.environ.get("HUAWEICLOUD_ACCOUNT_NAME") or os.environ.get("HUAWEICLOUD_DOMAIN_NAME")
    user = os.environ.get("HUAWEICLOUD_IAM_USER") or os.environ.get("HUAWEICLOUD_USERNAME")
    password = os.environ.get("HUAWEICLOUD_IAM_PASSWORD") or os.environ.get("HUAWEICLOUD_PASSWORD")
    if not (account and user and password):
        raise SystemExit("Missing HUAWEICLOUD_ACCOUNT_NAME, HUAWEICLOUD_IAM_USER, or HUAWEICLOUD_IAM_PASSWORD.")
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "domain": {"name": account},
                        "name": user,
                        "password": password,
                    }
                },
            },
            "scope": {"project": {"name": region}},
        }
    }
    _, headers, body = request_json("POST", "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true", body=payload)
    token = headers.get("X-Subject-Token") or headers.get("x-subject-token")
    if not token:
        raise ApiError("IAM token response did not include X-Subject-Token.")
    return {
        "token": token,
        "project_id": ((body.get("token") or {}).get("project") or {}).get("id", ""),
        "user_name": (((body.get("token") or {}).get("user") or {}).get("name", user)),
    }


def get_temporary_aksk(token: str, duration_seconds: int = 3600) -> dict[str, str]:
    payload = {
        "auth": {
            "identity": {
                "methods": ["token"],
                "token": {
                    "id": token,
                    "duration_seconds": duration_seconds,
                },
            }
        }
    }
    _, _, body = request_json("POST", "https://iam.myhuaweicloud.com/v3.0/OS-CREDENTIAL/securitytokens", token=token, body=payload)
    credential = body.get("credential") or {}
    access = credential.get("access")
    secret = credential.get("secret")
    security_token = credential.get("securitytoken")
    if not (access and secret and security_token):
        raise ApiError(f"Temporary credential response missing fields: {list(credential.keys())}")
    return {"access": access, "secret": secret, "securitytoken": security_token}


def get_obs_auth(region: str) -> dict[str, str]:
    access_key = os.environ.get("HUAWEICLOUD_ACCESS_KEY")
    secret_key = os.environ.get("HUAWEICLOUD_SECRET_KEY")
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID", "")
    if access_key and secret_key:
        return {
            "access": access_key,
            "secret": secret_key,
            "securitytoken": "",
            "project_id": project_id,
            "mode": "aksk",
        }

    auth = get_user_token(region)
    temporary = get_temporary_aksk(auth["token"])
    temporary["project_id"] = auth["project_id"]
    temporary["mode"] = "password-temporary-aksk"
    return temporary


def default_bucket(project_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9-]", "", (project_id or "monitor")[:12].lower()) or "monitor"
    return f"huawei-realtime-monitor-{suffix}-la-north-2"


def ensure_ok(response: Any, action: str, allow: set[int] | None = None) -> None:
    status = int(getattr(response, "status", 0) or 0)
    allow = allow or set()
    if status < 300 or status in allow:
        return
    code = getattr(response, "errorCode", "")
    message = getattr(response, "errorMessage", "")
    raise RuntimeError(f"{action} failed: HTTP {status} {code} {message}")


def upload_site(client: ObsClient, bucket: str, site_dir: Path) -> int:
    count = 0
    for path in site_dir.rglob("*"):
        if not path.is_file():
            continue
        key = path.relative_to(site_dir).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif path.suffix in {".html", ".css", ".json"}:
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
            }[path.suffix]
        headers = PutObjectHeader(contentType=content_type)
        response = client.putFile(bucket, key, str(path), headers=headers)
        ensure_ok(response, f"upload {key}")
        count += 1
    return count


def public_read_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Statement": [
                {
                    "Sid": "SatMonitorObjectReadOnly",
                    "Effect": "Allow",
                    "Principal": {"ID": ["*"]},
                    "Action": ["GetObject"],
                    "Resource": [f"{bucket}/*"],
                }
            ]
        },
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy SAT Mexico monitor static site to OBS in Mexico City2.")
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", DEFAULT_REGION))
    parser.add_argument("--bucket", default=os.environ.get("SAT_MONITOR_OBS_BUCKET", ""))
    parser.add_argument("--site-dir", default=str(ROOT / "dist" / "realtime-monitor-site"))
    parser.add_argument("--create-bucket", action="store_true")
    args = parser.parse_args()

    if args.region != "la-north-2":
        raise SystemExit("This deployment script is pinned to Mexico City2. Use --region la-north-2.")

    site_dir = Path(args.site_dir)
    if not (site_dir / "index.html").exists():
        raise SystemExit(f"Static site directory is missing index.html: {site_dir}")

    obs_auth = get_obs_auth(args.region)
    bucket = args.bucket or default_bucket(obs_auth.get("project_id", ""))
    client_kwargs = {
        "access_key_id": obs_auth["access"],
        "secret_access_key": obs_auth["secret"],
        "server": f"https://obs.{args.region}.myhuaweicloud.com",
    }
    if obs_auth.get("securitytoken"):
        client_kwargs["security_token"] = obs_auth["securitytoken"]
    client = ObsClient(**client_kwargs)
    try:
        head = client.headBucket(bucket)
        if int(getattr(head, "status", 0) or 0) >= 300:
            if not args.create_bucket:
                raise SystemExit(f"Bucket {bucket} does not exist or is inaccessible. Re-run with --create-bucket.")
            created = client.createBucket(bucket, location=args.region)
            ensure_ok(created, f"create bucket {bucket}", allow={409})

        uploaded = upload_site(client, bucket, site_dir)
        try:
            ensure_ok(
                client.putBucketPublicAccessBlock(
                    bucket,
                    blockPublicAcls=True,
                    ignorePublicAcls=True,
                    blockPublicPolicy=False,
                    restrictPublicBuckets=False,
                ),
                "configure bucket public access block",
            )
        except Exception as exc:
            print(f"Warning: could not adjust bucket public access block: {exc}", file=sys.stderr)
        ensure_ok(client.setBucketPolicy(bucket, public_read_policy(bucket)), "set public read bucket policy")
        website = WebsiteConfiguration(
            indexDocument=IndexDocument(suffix="index.html"),
            errorDocument=ErrorDocument(key="index.html"),
        )
        ensure_ok(client.setBucketWebsite(bucket, website), "configure static website")
    finally:
        client.close()

    endpoint = f"{bucket}.obs-website.{args.region}.myhuaweicloud.com"
    url = f"https://{endpoint}/"
    result = {
        "region": args.region,
        "bucket": bucket,
        "auth_mode": obs_auth.get("mode", "unknown"),
        "uploaded_files": uploaded,
        "website_url": url,
        "note": "Huawei Cloud may require a custom domain for in-browser preview on default OBS website domains in Mexico regions.",
    }
    out = ROOT / "exports" / f"obs_website_{args.region}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
