from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse


READONLY_PROBE_ENV = "HUAWEICLOUD_ENABLE_READONLY_PROBE"
REQUIRED_SDK_MODULES = [
    "huaweicloudsdkcore",
    "huaweicloudsdkvpc",
    "huaweicloudsdkmrs",
    "huaweicloudsdkdws",
    "huaweicloudsdkkms",
    "huaweicloudsdkdataartsstudio",
    "huaweicloudsdkobs",
]


@dataclass(frozen=True)
class HuaweiProbeConfig:
    access_key_present: bool
    secret_key_present: bool
    region: str
    project_id: str
    enabled: bool

    @property
    def credentials_present(self) -> bool:
        return self.access_key_present and self.secret_key_present


def load_probe_config(bindings: dict[str, str]) -> HuaweiProbeConfig:
    return HuaweiProbeConfig(
        access_key_present=bool(os.getenv("HUAWEICLOUD_ACCESS_KEY")),
        secret_key_present=bool(os.getenv("HUAWEICLOUD_SECRET_KEY")),
        region=(os.getenv("HUAWEICLOUD_REGION") or bindings.get("HUAWEICLOUD_REGION") or "la-south-2").strip(),
        project_id=(os.getenv("HUAWEICLOUD_PROJECT_ID") or bindings.get("HUAWEICLOUD_PROJECT_ID") or "").strip(),
        enabled=os.getenv(READONLY_PROBE_ENV, "").strip().lower() in {"1", "true", "yes"},
    )


def run_real_huaweicloud_readonly_probe(bindings: dict[str, str]) -> dict[str, Any]:
    config = load_probe_config(bindings)
    result: dict[str, Any] = {
        "status": "skipped",
        "reason": "",
        "credentials_present": config.credentials_present,
        "region": config.region,
        "project_id_present": bool(config.project_id),
        "network_calls": 0,
        "write_calls": 0,
        "services": [],
        "missing_sdk_modules": missing_sdk_modules(),
    }
    if not config.enabled:
        result["reason"] = f"Set {READONLY_PROBE_ENV}=true to allow Huawei Cloud read-only API calls."
        return result
    if result["missing_sdk_modules"]:
        result["status"] = "failed"
        result["reason"] = "Huawei Cloud SDK packages are not installed."
        return result
    if not config.credentials_present:
        result["status"] = "failed"
        result["reason"] = "HUAWEICLOUD_ACCESS_KEY or HUAWEICLOUD_SECRET_KEY is missing."
        return result
    if not config.project_id:
        result["status"] = "failed"
        result["reason"] = "HUAWEICLOUD_PROJECT_ID is missing."
        return result

    credentials = build_basic_credentials(config.project_id)
    service_specs = build_service_specs(bindings, config, credentials)
    services = []
    for spec in service_specs:
        service_result = execute_service_probe(spec)
        services.append(service_result)
        result["network_calls"] += int(service_result.get("network_calls", 0))
    result["services"] = services
    failed = [service for service in services if service["status"] == "failed"]
    verified = [service for service in services if service["status"] == "verified"]
    result["status"] = "passed" if not failed and verified else "failed"
    result["reason"] = (
        f"{len(verified)} read-only service validations passed, {len(failed)} failed."
        if result["status"] == "passed"
        else f"{len(failed)} read-only service validations failed."
    )
    return result


def missing_sdk_modules() -> list[str]:
    missing = []
    for module_name in REQUIRED_SDK_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def build_basic_credentials(project_id: str) -> Any:
    credentials_module = importlib.import_module("huaweicloudsdkcore.auth.credentials")
    credentials_cls = getattr(credentials_module, "BasicCredentials")
    return credentials_cls(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        project_id,
    )


def build_client(client_cls: Any, region_cls: Any, region: str, credentials: Any) -> Any:
    return (
        client_cls.new_builder()
        .with_credentials(credentials)
        .with_region(region_cls.value_of(region))
        .build()
    )


def build_service_specs(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    specs.append(make_vpc_spec(bindings, config, credentials))
    specs.append(make_obs_spec(bindings, config, credentials))
    specs.append(make_mrs_spec(bindings, config, credentials))
    specs.append(make_dws_spec(bindings, config, credentials))
    specs.append(make_kms_spec(bindings, config, credentials))
    specs.append(make_dataarts_spec(bindings, config, credentials))
    return specs


def make_vpc_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkvpc.v2")
    region_mod = importlib.import_module("huaweicloudsdkvpc.v2.region.vpc_region")
    client = build_client(sdk.VpcClient, region_mod.VpcRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        vpc_id = bindings.get("VPC_ID", "")
        subnet_id = bindings.get("PRIVATE_SUBNET_ID", "")
        vpc_response = client.list_vpcs(sdk.ListVpcsRequest(limit=100, id=vpc_id or None))
        subnet_response = client.list_subnets(sdk.ListSubnetsRequest(limit=100, vpc_id=vpc_id or None))
        vpcs = response_items(vpc_response, "vpcs")
        subnets = response_items(subnet_response, "subnets")
        return {
            "vpc_id": vpc_id,
            "vpc_found": any(getattr(item, "id", None) == vpc_id for item in vpcs) if vpc_id else bool(vpcs),
            "subnet_id": subnet_id,
            "subnet_found": any(getattr(item, "id", None) == subnet_id for item in subnets) if subnet_id else bool(subnets),
            "vpc_count_visible": len(vpcs),
            "subnet_count_visible": len(subnets),
        }

    return service_spec("vpc", "VPC and private subnet visibility", ["ListVpcs", "ListSubnets"], call)


def make_obs_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkobs.v1")
    region_mod = importlib.import_module("huaweicloudsdkobs.v1.region.obs_region")
    client = build_client(sdk.ObsClient, region_mod.ObsRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        uris = {
            key: value
            for key, value in bindings.items()
            if key.startswith("OBS_") and str(value).startswith("obs://")
        }
        checks = []
        for key, uri in sorted(uris.items()):
            parsed = parse_obs_uri(uri)
            response = client.list_objects(
                sdk.ListObjectsRequest(
                    bucket_name=parsed["bucket"],
                    prefix=parsed["prefix"],
                    max_keys=1,
                )
            )
            checks.append({
                "binding": key,
                "bucket": parsed["bucket"],
                "prefix": parsed["prefix"],
                "visible": response is not None,
            })
        return {
            "layer_checks": checks,
            "checked_layers": len(checks),
        }

    return service_spec("obs", "OBS bucket and layer prefix visibility", ["ListObjects"], call)


def make_mrs_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkmrs.v1")
    region_mod = importlib.import_module("huaweicloudsdkmrs.v1.region.mrs_region")
    client = build_client(sdk.MrsClient, region_mod.MrsRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        cluster_id = bindings.get("MRS_CLUSTER_ID", "")
        response = client.show_cluster_details(sdk.ShowClusterDetailsRequest(cluster_id=cluster_id))
        return {
            "cluster_id": cluster_id,
            "visible": response is not None,
            "state": first_existing_attr(response, ["cluster_state", "state", "status"]),
        }

    return service_spec("mrs", "MRS cluster detail visibility", ["ShowClusterDetails"], call)


def make_dws_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkdws.v2")
    region_mod = importlib.import_module("huaweicloudsdkdws.v2.region.dws_region")
    client = build_client(sdk.DwsClient, region_mod.DwsRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        connection_name = bindings.get("DWS_CONNECTION_NAME", "")
        response = client.list_cluster_details(sdk.ListClusterDetailsRequest())
        clusters = response_items(response, "clusters")
        return {
            "connection_name": connection_name,
            "visible_clusters": len(clusters),
            "matching_name_found": any(
                str(first_existing_attr(item, ["name", "cluster_name", "id"]) or "") == connection_name
                for item in clusters
            ) if connection_name else bool(clusters),
        }

    return service_spec("dws", "DWS cluster list visibility", ["ListClusterDetails"], call)


def make_kms_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkkms.v2")
    region_mod = importlib.import_module("huaweicloudsdkkms.v2.region.kms_region")
    client = build_client(sdk.KmsClient, region_mod.KmsRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        key_id = bindings.get("KMS_KEY_ID", "")
        response = client.list_keys(sdk.ListKeysRequest())
        keys = response_items(response, "keys")
        return {
            "key_id": key_id,
            "visible_keys": len(keys),
            "key_found": any(str(first_existing_attr(item, ["key_id", "id"]) or "") == key_id for item in keys) if key_id else bool(keys),
        }

    return service_spec("kms", "KMS key list visibility", ["ListKeys"], call)


def make_dataarts_spec(bindings: dict[str, str], config: HuaweiProbeConfig, credentials: Any) -> dict[str, Any]:
    sdk = importlib.import_module("huaweicloudsdkdataartsstudio.v1")
    region_mod = importlib.import_module("huaweicloudsdkdataartsstudio.v1.region.dataartsstudio_region")
    client = build_client(sdk.DataArtsStudioClient, region_mod.DataArtsStudioRegion, config.region, credentials)

    def call() -> dict[str, Any]:
        workspace_id = bindings.get("DATAARTS_WORKSPACE_ID", "")
        response = client.list_workspaces(sdk.ListWorkspacesRequest(limit=100))
        workspaces = response_items(response, "workspaces") or response_items(response, "data")
        return {
            "workspace_id": workspace_id,
            "visible_workspaces": len(workspaces),
            "workspace_found": any(
                str(first_existing_attr(item, ["id", "workspace_id", "workspace"]) or "") == workspace_id
                for item in workspaces
            ) if workspace_id else bool(workspaces),
        }

    return service_spec("dataarts", "DataArts workspace list visibility", ["ListWorkspaces"], call)


def service_spec(service: str, description: str, calls: list[str], function: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    return {
        "service": service,
        "description": description,
        "readonly_calls": calls,
        "function": function,
    }


def execute_service_probe(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        details = spec["function"]()
        return {
            "service": spec["service"],
            "description": spec["description"],
            "status": "verified",
            "readonly_calls": spec["readonly_calls"],
            "network_calls": len(spec["readonly_calls"]),
            "details": safe_json(details),
        }
    except Exception as exc:  # noqa: BLE001 - cloud SDK exceptions vary by service.
        return {
            "service": spec["service"],
            "description": spec["description"],
            "status": "failed",
            "readonly_calls": spec["readonly_calls"],
            "network_calls": len(spec["readonly_calls"]),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def parse_obs_uri(uri: str) -> dict[str, str]:
    parsed = urlparse(uri)
    prefix = parsed.path.lstrip("/")
    return {
        "bucket": parsed.netloc,
        "prefix": prefix,
    }


def response_items(response: Any, attr_name: str) -> list[Any]:
    value = getattr(response, attr_name, None)
    if value is None and hasattr(response, "to_dict"):
        value = response.to_dict().get(attr_name)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def first_existing_attr(item: Any, names: list[str]) -> Any:
    for name in names:
        if isinstance(item, dict) and item.get(name) is not None:
            return item.get(name)
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


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
