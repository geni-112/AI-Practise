#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
MONITOR_DATA = ROOT / "monitor" / "data"
DEFAULT_REGION = "la-north-2"
REDACT_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "authorization",
    "access_key",
    "secret_key",
    "user_data",
    "userdata",
    "admin_pass",
    "private_key",
)
OBS_URI_RE = re.compile(r"obs://([A-Za-z0-9][A-Za-z0-9.-]{1,61})(?:/|$)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def redact(value: Any, key: str = "") -> Any:
    low = key.lower()
    if any(fragment in low for fragment in REDACT_KEY_FRAGMENTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class ApiError(RuntimeError):
    pass


def read_json_response(response: urllib.response.addinfourl) -> Any:
    raw = response.read()
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:2000]}


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, str], Any]:
    data = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    if token:
        request_headers["X-Auth-Token"] = token
    elif os.environ.get("HUAWEICLOUD_ACCESS_KEY") and os.environ.get("HUAWEICLOUD_SECRET_KEY"):
        request_headers = signed_headers(method, url, request_headers, data)
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers), read_json_response(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise ApiError(f"HTTP {exc.code} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"Network error {url}: {exc}") from exc


def signed_headers(method: str, url: str, headers: dict[str, str], data: bytes | None) -> dict[str, str]:
    ak = os.environ.get("HUAWEICLOUD_ACCESS_KEY")
    sk = os.environ.get("HUAWEICLOUD_SECRET_KEY")
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID")
    if not (ak and sk and project_id):
        return headers
    parts = urllib.parse.urlsplit(url)
    request = SdkRequest(
        method=method,
        schema=parts.scheme,
        host=parts.netloc,
        resource_path=parts.path or "/",
        query_params=urllib.parse.parse_qsl(parts.query, keep_blank_values=True),
        header_params=dict(headers),
        body=data or b"",
    )
    signed = BasicCredentials(ak, sk, project_id).sign_request(request)
    return dict(signed.header_params)


def endpoint(service: str, region: str) -> str:
    overrides = {
        "rms": os.environ.get("HUAWEICLOUD_RMS_ENDPOINT"),
        "iam": os.environ.get("HUAWEICLOUD_IAM_ENDPOINT"),
    }
    if overrides.get(service):
        return overrides[service].rstrip("/")
    if service == "iam":
        return "https://iam.myhuaweicloud.com"
    if service == "dayu-dlf":
        return f"https://dayu-dlf.{region}.myhuaweicloud.com"
    if service in {"dayu", "dataartsstudio"}:
        return f"https://dayu.{region}.myhuaweicloud.com"
    return f"https://{service}.{region}.myhuaweicloud.com"


def endpoint_candidates(service: str, region: str) -> list[str]:
    primary = endpoint(service, region)
    if service == "rms":
        return list(dict.fromkeys([primary, "https://rms.myhuaweicloud.com"]))
    return [primary]


def get_token(region: str, project_id: str | None) -> dict[str, Any]:
    access_key = os.environ.get("HUAWEICLOUD_ACCESS_KEY")
    secret_key = os.environ.get("HUAWEICLOUD_SECRET_KEY")
    if access_key and secret_key:
        if not project_id:
            raise SystemExit("AK/SK mode requires HUAWEICLOUD_PROJECT_ID or --project-id.")
        return {
            "token": "",
            "project_id": project_id,
            "project_name": region,
            "domain_id": os.environ.get("HUAWEICLOUD_DOMAIN_ID", ""),
            "domain_name": os.environ.get("HUAWEICLOUD_ACCOUNT_NAME", ""),
            "user_name": os.environ.get("HUAWEICLOUD_IAM_USER", ""),
            "mode": "aksk",
        }

    existing_token = os.environ.get("HUAWEICLOUD_TOKEN")
    if existing_token:
        if not project_id:
            raise SystemExit("HUAWEICLOUD_TOKEN mode requires HUAWEICLOUD_PROJECT_ID or --project-id.")
        return {
            "token": existing_token,
            "project_id": project_id,
            "domain_id": os.environ.get("HUAWEICLOUD_DOMAIN_ID", ""),
            "domain_name": os.environ.get("HUAWEICLOUD_ACCOUNT_NAME", ""),
            "user_name": os.environ.get("HUAWEICLOUD_IAM_USER", ""),
            "mode": "token",
        }

    account_name = os.environ.get("HUAWEICLOUD_ACCOUNT_NAME") or os.environ.get("HUAWEICLOUD_DOMAIN_NAME")
    iam_user = os.environ.get("HUAWEICLOUD_IAM_USER") or os.environ.get("HUAWEICLOUD_USERNAME")
    password = os.environ.get("HUAWEICLOUD_IAM_PASSWORD") or os.environ.get("HUAWEICLOUD_PASSWORD")
    if not (account_name and iam_user and password):
        raise SystemExit(
            "Missing credentials. Set HUAWEICLOUD_ACCOUNT_NAME, HUAWEICLOUD_IAM_USER, "
            "and HUAWEICLOUD_IAM_PASSWORD, or run scripts\\Set-HuaweiCredentialEnv.ps1."
        )

    scope = {"project": {"id": project_id}} if project_id else {"project": {"name": region}}
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": iam_user,
                        "password": password,
                        "domain": {"name": account_name},
                    }
                },
            },
            "scope": scope,
        }
    }
    url = f"{endpoint('iam', region)}/v3/auth/tokens?nocatalog=true"
    _, headers, body = request_json("POST", url, body=payload)
    token = headers.get("X-Subject-Token") or headers.get("x-subject-token")
    if not token:
        raise ApiError("IAM did not return X-Subject-Token.")
    token_body = body.get("token", {})
    project = token_body.get("project") or {}
    user = token_body.get("user") or {}
    domain = user.get("domain") or {}
    return {
        "token": token,
        "project_id": project.get("id") or project_id,
        "project_name": project.get("name") or region,
        "domain_id": domain.get("id", ""),
        "domain_name": domain.get("name", account_name),
        "user_name": user.get("name", iam_user),
        "mode": "password",
    }


def safe_call(name: str, method: str, url: str, token: str, **kwargs: Any) -> dict[str, Any]:
    started = time.time()
    try:
        status, _, payload = request_json(method, url, token=token, **kwargs)
        return {
            "ok": True,
            "name": name,
            "status": status,
            "duration_ms": int((time.time() - started) * 1000),
            "payload": redact(payload),
        }
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "duration_ms": int((time.time() - started) * 1000),
            "error": str(exc),
        }


def safe_call_first(name: str, method: str, urls: list[str], token: str, **kwargs: Any) -> dict[str, Any]:
    last_result: dict[str, Any] | None = None
    for url in urls:
        result = safe_call(name, method, url, token, **kwargs)
        result["url"] = url
        if result.get("ok"):
            return result
        last_result = result
    return last_result or {"ok": False, "name": name, "error": "No endpoint candidates were provided."}


def list_rms_resources(region: str, token: str, domain_id: str) -> dict[str, Any]:
    if not domain_id:
        return {"ok": False, "name": "rms_all_resources", "error": "No domain_id available from IAM token."}
    resources: list[dict[str, Any]] = []
    marker = None
    page_count = 0
    last_result: dict[str, Any] | None = None
    for base_url in endpoint_candidates("rms", region):
        resources = []
        marker = None
        page_count = 0
        while True:
            query = {"region_id": region, "limit": "200"}
            if marker:
                query["marker"] = marker
            url = (
                f"{base_url}/v1/resource-manager/domains/{domain_id}/all-resources?"
                f"{urllib.parse.urlencode(query)}"
            )
            result = safe_call("rms_all_resources", "GET", url, token)
            if not result.get("ok"):
                last_result = result
                break
            payload = result.get("payload") or {}
            page_items = payload.get("resources") or payload.get("data") or []
            if isinstance(page_items, list):
                resources.extend(page_items)
            page_info = payload.get("page_info") or {}
            marker = page_info.get("next_marker") or payload.get("next_marker")
            page_count += 1
            if not marker or page_count >= 20:
                result["payload"] = {"resources": resources, "page_count": page_count, "endpoint": base_url}
                return result
    return last_result or {"ok": False, "name": "rms_all_resources", "error": "No RMS endpoint responded."}


def compact_list(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def discover_obs_buckets(sources: dict[str, Any]) -> list[str]:
    configured = [item.strip() for item in os.environ.get("OBS_BUCKETS", "").split(",") if item.strip()]
    buckets: set[str] = set(configured)

    def scan(value: Any) -> None:
        if isinstance(value, str):
            buckets.update(OBS_URI_RE.findall(value))
        elif isinstance(value, dict):
            for nested in value.values():
                scan(nested)
        elif isinstance(value, list):
            for nested in value:
                scan(nested)

    scan(sources)
    return sorted(bucket for bucket in buckets if not bucket.startswith("sat-mexico-monitor-"))


def service_calls(region: str, project_id: str, token: str, workspace_ids: list[str]) -> dict[str, Any]:
    calls: dict[str, Any] = {}
    definitions = {
        "mrs_clusters_v11": ("mrs", f"/v1.1/{project_id}/cluster_infos"),
        "rds_instances": ("rds", f"/v3/{project_id}/instances"),
        "dms_instances": ("dms", f"/v2/{project_id}/instances"),
        "oms_tasks": ("oms", f"/v2/{project_id}/tasks"),
        "cdm_clusters": ("cdm", f"/v1.1/{project_id}/clusters"),
        "ecs_servers": ("ecs", f"/v1/{project_id}/cloudservers/detail?limit=100"),
        "vpc_publicips": ("vpc", f"/v1/{project_id}/publicips?limit=100"),
    }
    include_dws = os.environ.get("INCLUDE_DWS", "").lower() in {"1", "true", "yes"}
    if include_dws:
        definitions["dws_clusters"] = ("dws", f"/v2/{project_id}/clusters")
    for name, (service, path) in definitions.items():
        calls[name] = safe_call(name, "GET", f"{endpoint(service, region)}{path}", token)

    mrs_jobs: list[dict[str, Any]] = []
    mrs_job_errors: list[dict[str, str]] = []
    mrs_clusters = compact_list((calls.get("mrs_clusters_v11") or {}).get("payload"), ("clusters", "cluster_infos", "data"))
    for cluster in mrs_clusters:
        cluster_id = cluster.get("clusterId") or cluster.get("cluster_id") or cluster.get("id")
        if not cluster_id:
            continue
        result = safe_call(
            f"mrs_jobs_v2_{cluster_id}",
            "GET",
            f"{endpoint('mrs', region)}/v2/{project_id}/clusters/{cluster_id}/job-executions?limit=50",
            token,
        )
        if result.get("ok"):
            payload = result.get("payload") or {}
            rows = compact_list(payload, ("job_list", "jobs", "job_exes", "job_executions", "data"))
            for row in rows:
                if isinstance(row, dict):
                    row["cluster_id"] = cluster_id
                    row["cluster_name"] = cluster.get("clusterName") or cluster.get("cluster_name")
                    mrs_jobs.append(row)
        else:
            mrs_job_errors.append({"cluster_id": str(cluster_id), "error": result.get("error", "")})
    calls["mrs_jobs_v2"] = {
        "ok": len(mrs_job_errors) == 0,
        "name": "mrs_jobs_v2",
        "payload": {"jobs": mrs_jobs, "errors": mrs_job_errors},
        "error": "; ".join(item["error"] for item in mrs_job_errors),
    }

    dataarts_jobs: list[dict[str, Any]] = []
    dataarts_errors: list[dict[str, str]] = []
    workspace_result = safe_call_first(
        "dataarts_workspaces",
        "GET",
        [
            f"{endpoint('dayu', region)}/v1/{project_id}/workspaces?limit=100&offset=0",
            f"{endpoint('dayu-dlf', region)}/v1/{project_id}/workspaces?limit=100&offset=0",
        ],
        token,
    )
    calls["dataarts_workspaces"] = workspace_result
    if not workspace_ids and workspace_result.get("ok"):
        for workspace in compact_list(workspace_result.get("payload"), ("workspaces", "data", "items")):
            workspace_id = workspace.get("id") or workspace.get("workspace_id")
            if workspace_id:
                workspace_ids.append(str(workspace_id))
        workspace_ids = sorted(set(workspace_ids))
    if workspace_ids:
        for workspace_id in workspace_ids:
            path = f"/v1/{project_id}/jobs?limit=100&offset=0"
            result = safe_call_first(
                f"dataarts_jobs_{workspace_id}",
                "GET",
                [
                    f"{endpoint('dayu-dlf', region)}{path}",
                    f"{endpoint('dayu', region)}{path}",
                ],
                token,
                headers={"workspace": workspace_id},
            )
            if result.get("ok"):
                jobs = compact_list(result.get("payload"), ("jobs", "job_list", "data"))
                dataarts_jobs.extend(jobs)
            else:
                dataarts_errors.append({"workspace_id": workspace_id, "error": result.get("error", "")})
    else:
        result = safe_call_first(
            "dataarts_jobs_without_workspace",
            "GET",
            [
                f"{endpoint('dayu-dlf', region)}/v1/{project_id}/jobs?limit=100&offset=0",
                f"{endpoint('dayu', region)}/v1/{project_id}/jobs?limit=100&offset=0",
            ],
            token,
        )
        if result.get("ok"):
            dataarts_jobs = compact_list(result.get("payload"), ("jobs", "job_list", "data"))
        else:
            dataarts_errors.append({"workspace_id": "", "error": result.get("error", "")})
    calls["dataarts_jobs"] = {
        "ok": len(dataarts_errors) == 0,
        "name": "dataarts_jobs",
        "payload": {"jobs": dataarts_jobs, "errors": dataarts_errors},
        "error": "; ".join(item["error"] for item in dataarts_errors),
    }
    return calls


def collect_dws_schema() -> dict[str, Any]:
    required = ("DWS_HOST", "DWS_DATABASE", "DWS_USER", "DWS_PASSWORD")
    if not all(os.environ.get(name) for name in required):
        return {"ok": False, "name": "dws_schema", "error": "DWS_* environment variables are not set."}
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return {"ok": False, "name": "dws_schema", "error": "psycopg2 is not installed."}

    try:
        connection = psycopg2.connect(
            host=os.environ["DWS_HOST"],
            port=int(os.environ.get("DWS_PORT", "8000")),
            dbname=os.environ["DWS_DATABASE"],
            user=os.environ["DWS_USER"],
            password=os.environ["DWS_PASSWORD"],
            connect_timeout=8,
            sslmode=os.environ.get("DWS_SSLMODE", "prefer"),
        )
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_schema, table_name, column_name, data_type, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_schema, table_name, ordinal_position
                    """
                )
                rows = [
                    {
                        "schema": schema,
                        "table": table,
                        "column": column,
                        "type": data_type,
                        "position": position,
                    }
                    for schema, table, column, data_type, position in cursor.fetchall()
                ]
        return {"ok": True, "name": "dws_schema", "payload": {"columns": rows}}
    except Exception as exc:
        return {"ok": False, "name": "dws_schema", "error": str(exc)}


def collect_obs_samples(region: str, sources: dict[str, Any] | None = None) -> dict[str, Any]:
    buckets = discover_obs_buckets(sources or {})
    if not buckets:
        return {"ok": False, "name": "obs_samples", "error": "No OBS bucket was discovered from OBS_BUCKETS or job arguments."}
    ak = os.environ.get("HUAWEICLOUD_ACCESS_KEY")
    sk = os.environ.get("HUAWEICLOUD_SECRET_KEY")
    if not (ak and sk):
        return {"ok": False, "name": "obs_samples", "error": "AK/SK is required for OBS object listing."}
    try:
        from obs import ObsClient  # type: ignore
    except ImportError:
        return {"ok": False, "name": "obs_samples", "error": "huaweicloud OBS SDK is not installed."}

    client = ObsClient(
        access_key_id=ak,
        secret_access_key=sk,
        server=f"https://obs.{region}.myhuaweicloud.com",
    )
    max_objects = int(os.environ.get("OBS_SAMPLE_MAX_OBJECTS", "5000"))
    sampled: dict[str, Any] = {}
    try:
        for bucket in buckets:
            objects = []
            marker = None
            truncated = False
            while len(objects) < max_objects:
                kwargs: dict[str, Any] = {"max_keys": min(1000, max_objects - len(objects))}
                if marker:
                    kwargs["marker"] = marker
                response = client.listObjects(bucket, **kwargs)
                if response.status >= 300:
                    sampled[bucket] = {"ok": False, "error": f"HTTP {response.status}"}
                    break
                body = response.body
                contents = list(getattr(body, "contents", None) or [])
                for item in contents:
                    objects.append(
                        {
                            "key": item.key,
                            "size": int(item.size or 0),
                            "modified": str(item.lastModified or ""),
                        }
                    )
                truncated = bool(getattr(body, "is_truncated", False) or getattr(body, "isTruncated", False))
                marker = getattr(body, "next_marker", None) or getattr(body, "nextMarker", None)
                if not truncated or not marker or not contents:
                    break
            if bucket not in sampled:
                sampled[bucket] = {
                    "ok": True,
                    "objects": objects,
                    "object_count": len(objects),
                    "sample_limit": max_objects,
                    "is_truncated": truncated and len(objects) >= max_objects,
                }
        return {"ok": True, "name": "obs_samples", "payload": sampled}
    finally:
        client.close()


def summarize(inventory: dict[str, Any]) -> dict[str, Any]:
    sources = inventory.get("sources", {})
    rms_items = compact_list((sources.get("rms_all_resources") or {}).get("payload"), ("resources",))
    summary: dict[str, Any] = {
        "rms_resource_count": len(rms_items),
        "services": {},
        "errors": [],
    }
    for name, source in sources.items():
        if not isinstance(source, dict):
            continue
        if not source.get("ok"):
            summary["errors"].append({"source": name, "error": source.get("error", "unknown error")})
            continue
        payload = source.get("payload")
        rows = []
        if name == "rms_all_resources":
            rows = compact_list(payload, ("resources",))
        elif name == "dataarts_jobs":
            rows = compact_list(payload, ("jobs",))
        elif name == "dws_schema":
            rows = compact_list(payload, ("columns",))
        elif name == "obs_samples":
            rows = [bucket for bucket, payload in (payload or {}).items() if isinstance(payload, dict) and payload.get("ok")]
        else:
            rows = compact_list(payload, ("clusters", "cluster_infos", "instances", "servers", "publicips", "tasks", "jobs"))
        summary["services"][name] = len(rows)
    return summary


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Huawei Cloud big-data resources without storing secrets.")
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", DEFAULT_REGION))
    parser.add_argument("--project-id", default=os.environ.get("HUAWEICLOUD_PROJECT_ID", ""))
    parser.add_argument("--workspace-id", action="append", default=[])
    parser.add_argument("--skip-service-calls", action="store_true")
    args = parser.parse_args()

    region = args.region
    workspace_ids = list(args.workspace_id)
    workspace_env = os.environ.get("DATAARTS_WORKSPACE_IDS") or os.environ.get("DATAARTS_WORKSPACE_ID")
    if workspace_env:
        workspace_ids.extend([item.strip() for item in workspace_env.split(",") if item.strip()])
    workspace_ids = sorted(set(workspace_ids))

    auth = get_token(region, args.project_id or None)
    project_id = auth.get("project_id")
    if not project_id:
        raise SystemExit("Could not determine project id from IAM token. Pass --project-id explicitly.")

    sources: dict[str, Any] = {
        "rms_all_resources": list_rms_resources(region, auth["token"], auth.get("domain_id", "")),
    }
    include_dws = os.environ.get("INCLUDE_DWS", "").lower() in {"1", "true", "yes"} or all(
        os.environ.get(name) for name in ("DWS_HOST", "DWS_DATABASE", "DWS_USER", "DWS_PASSWORD")
    )
    if include_dws:
        sources["dws_schema"] = collect_dws_schema()
    if not args.skip_service_calls:
        sources.update(service_calls(region, project_id, auth["token"], workspace_ids))
    sources["obs_samples"] = collect_obs_samples(region, sources)

    inventory = {
        "generated_at": utc_now(),
        "region": region,
        "project": {
            "id": project_id,
            "name": auth.get("project_name") or region,
        },
        "account": {
            "domain_id": auth.get("domain_id", ""),
            "domain_name": auth.get("domain_name", ""),
            "iam_user": auth.get("user_name", ""),
            "auth_mode": auth.get("mode", ""),
        },
        "workspace_ids": workspace_ids,
        "sources": sources,
    }
    inventory["summary"] = summarize(inventory)

    EXPORTS.mkdir(parents=True, exist_ok=True)
    MONITOR_DATA.mkdir(parents=True, exist_ok=True)
    snapshot = EXPORTS / f"huawei_inventory_{timestamp()}.json"
    write_json(snapshot, inventory)
    write_json(MONITOR_DATA / "inventory.json", inventory)

    summary = inventory["summary"]
    print(f"Inventory written: {snapshot}")
    print(f"Region: {region}; project: {project_id}; RMS resources: {summary['rms_resource_count']}")
    if summary["errors"]:
        print("Limited sources:")
        for item in summary["errors"]:
            print(f"  - {item['source']}: {item['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
