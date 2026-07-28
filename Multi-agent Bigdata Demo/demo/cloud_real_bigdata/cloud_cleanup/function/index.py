"""Idempotent Huawei Cloud cleanup handler for the SAT Agentic demo."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest
from obs import ObsClient, Versions


def _http(
    method: str,
    url: str,
    credentials: BasicCredentials,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    body_text = "" if body is None else json.dumps(body, separators=(",", ":"))
    payload = None if body is None else body_text.encode("utf-8")
    parsed = urllib.parse.urlsplit(url)
    request_headers = {"Host": parsed.netloc, "Content-Type": "application/json"}
    request_headers.update(headers or {})
    signed_request = SdkRequest(
        method=method,
        schema=parsed.scheme,
        host=parsed.netloc,
        resource_path=parsed.path,
        uri=parsed.path,
        query_params=urllib.parse.parse_qsl(parsed.query, keep_blank_values=True),
        header_params=request_headers,
        body=body_text,
    )
    credentials.sign_request(signed_request)
    request = urllib.request.Request(
        url=url,
        data=payload,
        headers=signed_request.header_params,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def _absent(status: int, body: str = "") -> bool:
    if status == 404:
        return "APIGW.0101" not in body
    return status == 400 and any(code in body for code in ("DLF.0100", "DLF.6241"))


def _result(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail[:400]}


def _delete_dataarts(
    config: dict[str, Any], credentials: BasicCredentials, dry_run: bool
) -> list[dict[str, str]]:
    base = f"https://dayu-dlf.{config['region']}.myhuaweicloud.com/v1/{config['project_id']}"
    headers = {"workspace": config["dataarts_workspace_id"]}
    targets = [
        ("dataarts_job", f"jobs/{config['dataarts_job_name']}"),
        ("dataarts_resource", f"resources/{config['dataarts_resource_id']}"),
    ]
    results = []
    for name, path in targets:
        url = f"{base}/{path}"
        status, body = _http("GET", url, credentials, headers=headers)
        if _absent(status, body):
            results.append(_result(name, "absent"))
            continue
        if status != 200:
            results.append(_result(name, "failed", f"probe HTTP {status}: {body}"))
            continue
        if dry_run:
            results.append(_result(name, "present"))
            continue
        status, body = _http("DELETE", url, credentials, headers=headers)
        if status in (200, 202, 204) or _absent(status, body):
            results.append(_result(name, "delete_requested"))
        else:
            results.append(_result(name, "failed", f"delete HTTP {status}"))
    return results


def _delete_mrs(
    config: dict[str, Any], credentials: BasicCredentials, dry_run: bool
) -> list[dict[str, str]]:
    show_url = (
        f"https://mrs.{config['region']}.myhuaweicloud.com/v1.1/"
        f"{config['project_id']}/cluster_infos/{config['mrs_cluster_id']}"
    )
    delete_url = (
        f"https://mrs.{config['region']}.myhuaweicloud.com/v1.1/"
        f"{config['project_id']}/clusters/{config['mrs_cluster_id']}"
    )
    status, body = _http("GET", show_url, credentials)
    if _absent(status, body):
        return [_result("mrs_cluster", "absent")]
    if status != 200:
        return [_result("mrs_cluster", "failed", f"probe HTTP {status}")]
    if dry_run:
        return [_result("mrs_cluster", "present")]
    status, body = _http("DELETE", delete_url, credentials)
    if status in (200, 202, 204) or _absent(status, body):
        return [_result("mrs_cluster", "delete_requested")]
    return [_result("mrs_cluster", "failed", f"delete HTTP {status}")]


def _delete_obs(config: dict[str, Any], context: Any, dry_run: bool) -> list[dict[str, str]]:
    client = ObsClient(
        access_key_id=context.getSecurityAccessKey(),
        secret_access_key=context.getSecuritySecretKey(),
        security_token=context.getSecurityToken(),
        server=f"https://obs.{config['region']}.myhuaweicloud.com",
    )
    bucket = config["obs_bucket"]
    try:
        response = client.headBucket(bucket)
        if response.status == 404:
            return [_result("obs_bucket", "absent")]
        if response.status >= 300:
            return [_result("obs_bucket", "failed", f"probe HTTP {response.status}")]
        if dry_run:
            return [_result("obs_bucket", "present")]

        deleted = 0
        for _ in range(200):
            listing = client.listVersions(bucket, Versions(max_keys=1000))
            if listing.status == 404:
                return [_result("obs_bucket", "absent")]
            if listing.status >= 300:
                return [_result("obs_bucket", "failed", f"list versions HTTP {listing.status}")]
            versions = list(getattr(listing.body, "versions", None) or [])
            markers = list(getattr(listing.body, "markers", None) or [])
            objects = versions + markers
            if not objects:
                break
            for item in objects:
                result = client.deleteObject(bucket, item.key, versionId=item.versionId)
                if result.status not in (200, 204, 404):
                    return [_result("obs_bucket", "failed", f"delete object HTTP {result.status}")]
                deleted += 1
        else:
            return [_result("obs_bucket", "failed", "version deletion safety limit reached")]

        response = client.deleteBucket(bucket)
        if response.status in (200, 204, 404):
            return [_result("obs_bucket", "deleted", f"versions_and_markers={deleted}")]
        return [_result("obs_bucket", "failed", f"delete bucket HTTP {response.status}")]
    finally:
        client.close()


def _delete_web_compute(
    config: dict[str, Any], credentials: BasicCredentials, dry_run: bool
) -> list[dict[str, str]]:
    project_id = config["project_id"]
    region = config["region"]
    server_id = config["web_server_id"]
    show_url = f"https://ecs.{region}.myhuaweicloud.com/v2.1/{project_id}/servers/{server_id}"
    status, body = _http("GET", show_url, credentials)
    if _absent(status, body):
        return [_result("web_ecs", "absent")]
    if status != 200:
        return [_result("web_ecs", "failed", f"probe HTTP {status}")]
    if dry_run:
        return [_result("web_ecs", "present")]

    delete_url = f"https://ecs.{region}.myhuaweicloud.com/v1/{project_id}/cloudservers/delete"
    status, body = _http(
        "POST",
        delete_url,
        credentials,
        body={
            "servers": [{"id": server_id}],
            "delete_publicip": True,
            "delete_volume": True,
        },
    )
    if status not in (200, 202, 204) and not _absent(status, body):
        return [_result("web_ecs", "failed", f"delete HTTP {status}")]

    for _ in range(36):
        status, body = _http("GET", show_url, credentials)
        if _absent(status, body):
            return [_result("web_ecs", "deleted")]
        time.sleep(10)
    return [_result("web_ecs", "delete_requested", "server deletion still in progress")]


def _delete_network(
    config: dict[str, Any], credentials: BasicCredentials, dry_run: bool
) -> list[dict[str, str]]:
    project_id = config["project_id"]
    region = config["region"]
    base = f"https://vpc.{region}.myhuaweicloud.com/v1/{project_id}"
    targets = []
    if config.get("web_eip_id"):
        path = f"publicips/{config['web_eip_id']}"
        targets.append(("web_eip", path, path))
    for index, rule_id in enumerate(config.get("security_group_rule_ids", []), start=1):
        path = f"security-group-rules/{rule_id}"
        targets.append((f"security_group_rule_{index}", path, path))
    targets.extend(
        [
            (
                "security_group",
                f"security-groups/{config['security_group_id']}",
                f"security-groups/{config['security_group_id']}",
            ),
            (
                "web_subnet",
                f"subnets/{config['web_subnet_id']}",
                f"vpcs/{config['web_vpc_id']}/subnets/{config['web_subnet_id']}",
            ),
            (
                "web_vpc",
                f"vpcs/{config['web_vpc_id']}",
                f"vpcs/{config['web_vpc_id']}",
            ),
        ]
    )

    results = []
    for name, show_path, delete_path in targets:
        show_url = f"{base}/{show_path}"
        delete_url = f"{base}/{delete_path}"
        status, body = _http("GET", show_url, credentials)
        if _absent(status, body):
            results.append(_result(name, "absent"))
            continue
        if status != 200:
            results.append(_result(name, "failed", f"probe HTTP {status}"))
            continue
        if dry_run:
            results.append(_result(name, "present"))
            continue
        final_status = "failed"
        final_detail = ""
        for attempt in range(8):
            status, body = _http("DELETE", delete_url, credentials)
            if status in (200, 202, 204) or _absent(status, body):
                final_status = "delete_requested"
                break
            if status in (409, 500, 503):
                final_detail = f"retryable HTTP {status}; attempt={attempt + 1}"
                time.sleep(12)
                continue
            final_detail = f"delete HTTP {status}"
            break
        results.append(_result(name, final_status, final_detail))
    return results


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    raw_config = context.getUserData("cleanup_config")
    config = json.loads(raw_config)
    dry_run = bool((event or {}).get("dry_run", False))
    event_time = str((event or {}).get("time") or datetime.now(timezone.utc).isoformat())
    event_date = event_time[:10]

    if not dry_run and event_date != config["expected_date"]:
        result = {
            "status": "ignored_outside_cleanup_date",
            "event_date": event_date,
            "expected_date": config["expected_date"],
        }
        print(json.dumps(result, sort_keys=True))
        return result

    credentials = BasicCredentials(
        context.getSecurityAccessKey(),
        context.getSecuritySecretKey(),
        config["project_id"],
    ).with_security_token(context.getSecurityToken())
    results: list[dict[str, str]] = []
    operations = [
        ("dataarts", lambda: _delete_dataarts(config, credentials, dry_run)),
        ("mrs", lambda: _delete_mrs(config, credentials, dry_run)),
        ("obs", lambda: _delete_obs(config, context, dry_run)),
        ("ecs", lambda: _delete_web_compute(config, credentials, dry_run)),
        ("network", lambda: _delete_network(config, credentials, dry_run)),
    ]
    for operation_name, operation in operations:
        try:
            results.extend(operation())
        except Exception as error:
            detail = f"{type(error).__name__}: {error}"
            results.append(_result(operation_name, "failed", detail))

    failures = [item for item in results if item["status"] == "failed"]
    response = {
        "status": "dry_run_passed" if dry_run and not failures else "completed" if not failures else "partial_failure",
        "dry_run": dry_run,
        "results": results,
    }
    print(json.dumps(response, sort_keys=True))
    return response
