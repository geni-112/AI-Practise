from __future__ import annotations

import argparse
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from obs import ObsClient as EsdkObsClient


REQUIRED_MODULES = [
    "huaweicloudsdkcore",
    "huaweicloudsdkvpc",
    "huaweicloudsdkmrs",
    "huaweicloudsdkobs",
    "obs",
]


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def missing_modules() -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return missing


def safe_error(exc: BaseException) -> dict[str, str]:
    text = str(exc)
    for token in [
        os.environ.get("HUAWEICLOUD_ACCESS_KEY", ""),
        os.environ.get("HUAWEICLOUD_SECRET_KEY", ""),
        os.environ.get("HW_ACCESS_KEY", ""),
        os.environ.get("HW_SECRET_KEY", ""),
        os.environ.get("HUAWEICLOUD_SECURITY_TOKEN", ""),
        os.environ.get("HW_SECURITY_TOKEN", ""),
    ]:
        if token:
            text = text.replace(token, "<redacted>")
    return {
        "type": type(exc).__name__,
        "message": text[:800],
    }


def safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): safe_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        return safe_json(value.to_dict())
    return str(value)


def response_items(response: Any, attr_name: str) -> list[Any]:
    value = getattr(response, attr_name, None)
    if value is None and hasattr(response, "to_dict"):
        value = response.to_dict().get(attr_name)
    if isinstance(value, list):
        return value
    return []


def first_attr(item: Any, names: list[str]) -> Any:
    for name in names:
        if isinstance(item, dict) and item.get(name) is not None:
            return item.get(name)
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def build_basic_credentials(project_id: str) -> Any:
    credentials_module = importlib.import_module("huaweicloudsdkcore.auth.credentials")
    credentials_cls = getattr(credentials_module, "BasicCredentials")
    credentials = credentials_cls(
        env_first("HUAWEICLOUD_ACCESS_KEY", "HW_ACCESS_KEY"),
        env_first("HUAWEICLOUD_SECRET_KEY", "HW_SECRET_KEY"),
        project_id,
    )
    security_token = env_first("HUAWEICLOUD_SECURITY_TOKEN", "HW_SECURITY_TOKEN")
    if security_token:
        credentials = credentials.with_security_token(security_token)
    return credentials


def build_client(client_cls: Any, region_cls: Any, region: str, credentials: Any) -> Any:
    return (
        client_cls.new_builder()
        .with_credentials(credentials)
        .with_region(region_cls.value_of(region))
        .build()
    )


def run_check(name: str, description: str, readonly_calls: list[str], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        details = fn()
        return {
            "name": name,
            "description": description,
            "status": "passed",
            "readonly_calls": readonly_calls,
            "network_calls": len(readonly_calls),
            "details": safe_json(details),
        }
    except Exception as exc:  # noqa: BLE001 - SDK exceptions vary by service.
        return {
            "name": name,
            "description": description,
            "status": "failed",
            "readonly_calls": readonly_calls,
            "network_calls": len(readonly_calls),
            "error": safe_error(exc),
        }


def check_vpc(region: str, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkvpc.v2")
    region_mod = importlib.import_module("huaweicloudsdkvpc.v2.region.vpc_region")
    client = build_client(sdk.VpcClient, region_mod.VpcRegion, region, credentials)

    def call() -> dict[str, Any]:
        vpc_response = client.list_vpcs(sdk.ListVpcsRequest(limit=10))
        subnet_response = client.list_subnets(sdk.ListSubnetsRequest(limit=10))
        quota_response = client.show_quota(sdk.ShowQuotaRequest())
        vpcs = response_items(vpc_response, "vpcs")
        subnets = response_items(subnet_response, "subnets")
        quotas = first_attr(quota_response, ["quotas"]) or safe_json(quota_response)
        return {
            "vpc_count_visible_sample": len(vpcs),
            "subnet_count_visible_sample": len(subnets),
            "quota_response_visible": bool(quotas),
        }

    return run_check("vpc", "VPC list/subnet/quota visibility", ["ListVpcs", "ListSubnets", "ShowQuota"], call)


def check_mrs(
    region: str,
    credentials: Any,
    mrs_version: str,
    availability_zone: str,
    master_flavor: str,
    core_flavor: str,
) -> dict[str, Any]:
    sdk_v1 = importlib.import_module("huaweicloudsdkmrs.v1")
    region_v1 = importlib.import_module("huaweicloudsdkmrs.v1.region.mrs_region")
    client_v1 = build_client(sdk_v1.MrsClient, region_v1.MrsRegion, region, credentials)
    sdk_v2 = importlib.import_module("huaweicloudsdkmrs.v2")
    region_v2 = importlib.import_module("huaweicloudsdkmrs.v2.region.mrs_region")
    client_v2 = build_client(sdk_v2.MrsClient, region_v2.MrsRegion, region, credentials)

    def call() -> dict[str, Any]:
        clusters_response = client_v1.list_clusters(sdk_v1.ListClustersRequest(page_size=10, current_page=1))
        versions_response = client_v2.show_mrs_version_list(sdk_v2.ShowMrsVersionListRequest())
        details: dict[str, Any] = {
            "visible_cluster_sample_count": len(response_items(clusters_response, "clusters")),
            "versions_response_visible": bool(safe_json(versions_response)),
            "requested_mrs_version": mrs_version,
            "requested_availability_zone": availability_zone,
        }
        if availability_zone:
            flavors_response = client_v2.show_mrs_flavors(
                sdk_v2.ShowMrsFlavorsRequest(version_name=mrs_version, availability_zone=availability_zone)
            )
            flavor_payload = safe_json(flavors_response)
            available = flavor_payload.get("available_flavors", []) if isinstance(flavor_payload, dict) else []
            zone_flavors = next(
                (
                    item
                    for item in available
                    if isinstance(item, dict) and item.get("az_code") == availability_zone
                ),
                available[0] if available else {},
            )

            def flavor_names(role: str) -> list[str]:
                values = zone_flavors.get(role, []) if isinstance(zone_flavors, dict) else []
                return sorted(
                    {
                        str(item.get("flavor_name"))
                        for item in values
                        if isinstance(item, dict) and item.get("flavor_name")
                    }
                )

            master_names = flavor_names("master")
            core_names = flavor_names("core")
            normalize_flavor = lambda value: value.removesuffix(".linux.bigdata")
            normalized_master_names = {normalize_flavor(value) for value in master_names}
            normalized_core_names = {normalize_flavor(value) for value in core_names}
            master_available = normalize_flavor(master_flavor) in normalized_master_names
            core_available = normalize_flavor(core_flavor) in normalized_core_names
            details.update(
                {
                    "flavors_response_visible": bool(available),
                    "requested_master_flavor": master_flavor,
                    "requested_core_flavor": core_flavor,
                    "master_flavor_available": master_available,
                    "core_flavor_available": core_available,
                    "available_master_flavors": master_names,
                    "available_core_flavors": core_names,
                }
            )
            unavailable = []
            if not master_available:
                unavailable.append(f"master={master_flavor}")
            if not core_available:
                unavailable.append(f"core={core_flavor}")
            if unavailable:
                raise RuntimeError(
                    f"Requested MRS flavors are unavailable in {availability_zone}: {', '.join(unavailable)}"
                )
        else:
            details["flavors_response_visible"] = False
            details["flavors_note"] = "Set TF_VAR_availability_zone to probe exact MRS flavor availability."
        return details

    calls = ["ListClusters", "ShowMrsVersionList"]
    if availability_zone:
        calls.append("ShowMrsFlavors")
    return run_check("mrs", "MRS read-only availability and version visibility", calls, call)


def check_obs(
    region: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    security_token: str = "",
    allow_existing_owned_bucket: bool = False,
) -> dict[str, Any]:
    endpoint = f"https://obs.{region}.myhuaweicloud.com"
    client = EsdkObsClient(
        access_key_id=access_key,
        secret_access_key=secret_key,
        security_token=security_token or None,
        server=endpoint,
    )

    def call() -> dict[str, Any]:
        try:
            buckets_response = client.listBuckets(isQueryLocation=True)
            own_bucket_names = [
                getattr(bucket_item, "name", "")
                for bucket_item in (getattr(buckets_response.body, "buckets", []) or [])
            ] if buckets_response.status < 300 else []
            head_status = None
            head_reason = ""
            if bucket:
                head_response = client.headBucket(bucket)
                head_status = head_response.status
                head_reason = head_response.reason
            owned_bucket = bool(bucket and bucket in own_bucket_names)
            expected_existing = bool(owned_bucket and allow_existing_owned_bucket)
            conflict = bool(
                bucket
                and head_status is not None
                and head_status < 300
                and not expected_existing
            )
            unavailable_or_forbidden = bool(bucket and head_status in {301, 302, 403, 409})
            return {
                "endpoint": endpoint,
                "own_bucket_sample_count": len(own_bucket_names),
                "target_bucket": bucket,
                "target_bucket_owned_by_account": owned_bucket,
                "target_bucket_expected_existing": expected_existing,
                "allow_existing_owned_bucket": allow_existing_owned_bucket,
                "target_bucket_head_status": head_status,
                "target_bucket_head_reason": head_reason,
                "target_bucket_appears_available": bool(bucket and head_status == 404),
                "target_bucket_conflict": conflict or unavailable_or_forbidden,
                "note": "Terraform creates the bucket, so an existing or forbidden bucket name should be treated as a conflict.",
            }
        finally:
            client.close()

    result = run_check("obs", "OBS authentication and target bucket name head check", ["ListBuckets", "HeadBucket"], call)
    details = result.get("details", {})
    if result["status"] == "passed" and isinstance(details, dict) and details.get("target_bucket_conflict"):
        result["status"] = "failed"
        result["error"] = {
            "type": "BucketNameConflict",
            "message": "Target OBS bucket appears to exist or is forbidden. Choose a globally unique bucket name.",
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Huawei Cloud read-only pre-create probes.")
    parser.add_argument("--bucket", default=os.environ.get("TF_VAR_obs_bucket_name", ""))
    parser.add_argument("--region", default=env_first("HUAWEICLOUD_REGION", "HW_REGION_NAME", default="la-south-2"))
    parser.add_argument("--project-id", default=env_first("HUAWEICLOUD_PROJECT_ID", "HW_PROJECT_ID"))
    parser.add_argument("--mrs-version", default=os.environ.get("TF_VAR_mrs_version", "MRS 3.5.0-LTS"))
    parser.add_argument("--availability-zone", default=os.environ.get("TF_VAR_availability_zone", ""))
    parser.add_argument("--mrs-master-flavor", default=os.environ.get("TF_VAR_mrs_master_flavor", "m6.2xlarge.8.linux.bigdata"))
    parser.add_argument("--mrs-core-flavor", default=os.environ.get("TF_VAR_mrs_core_flavor", "m6.2xlarge.8.linux.bigdata"))
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-existing-owned-bucket", action="store_true")
    args = parser.parse_args()

    access_key = env_first("HUAWEICLOUD_ACCESS_KEY", "HW_ACCESS_KEY")
    secret_key = env_first("HUAWEICLOUD_SECRET_KEY", "HW_SECRET_KEY")
    security_token = env_first("HUAWEICLOUD_SECURITY_TOKEN", "HW_SECURITY_TOKEN")
    missing = []
    if not access_key:
        missing.append("HUAWEICLOUD_ACCESS_KEY")
    if not secret_key:
        missing.append("HUAWEICLOUD_SECRET_KEY")
    if not args.project_id:
        missing.append("HUAWEICLOUD_PROJECT_ID")

    report: dict[str, Any] = {
        "status": "not_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "values_printed": False,
        "creates_resources": False,
        "uploads_obs_objects": False,
        "submits_mrs_job": False,
        "region": args.region,
        "project_id_present": bool(args.project_id),
        "access_key_present": bool(access_key),
        "secret_key_present": bool(secret_key),
        "target_bucket": args.bucket,
        "missing_required": missing,
        "missing_sdk_modules": missing_modules(),
        "network_calls": 0,
        "write_calls": 0,
        "checks": [],
    }

    if report["missing_sdk_modules"]:
        report["status"] = "failed"
        report["reason"] = "Required Huawei Cloud SDK modules are missing."
    elif missing:
        report["status"] = "missing_credentials"
        report["reason"] = "Required Huawei Cloud credential environment variables are missing."
    else:
        credentials = build_basic_credentials(args.project_id)
        checks = [
            check_obs(
                args.region,
                access_key,
                secret_key,
                args.bucket,
                security_token,
                args.allow_existing_owned_bucket,
            ),
            check_vpc(args.region, credentials),
            check_mrs(
                args.region,
                credentials,
                args.mrs_version,
                args.availability_zone,
                args.mrs_master_flavor,
                args.mrs_core_flavor,
            ),
        ]
        report["checks"] = checks
        report["network_calls"] = sum(int(check.get("network_calls", 0)) for check in checks)
        failed = [check for check in checks if check.get("status") == "failed"]
        report["status"] = "passed" if not failed else "failed"
        report["reason"] = f"{len(checks) - len(failed)} read-only probes passed, {len(failed)} failed."

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
