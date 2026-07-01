#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials


REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
PROJECT_ID = os.environ.get("HUAWEICLOUD_PROJECT_ID")
OBS_BUCKET = os.environ.get("DEPLOYMENT_OBS_BUCKET")
MRS_CLUSTER_ID = os.environ.get("DEPLOYMENT_MRS_CLUSTER_ID")
DATAARTS_WORKSPACE_ID = os.environ.get("DATAARTS_WORKSPACE_ID")


def creds() -> BasicCredentials:
    missing = [
        name
        for name in ["HUAWEICLOUD_ACCESS_KEY", "HUAWEICLOUD_SECRET_KEY", "HUAWEICLOUD_PROJECT_ID"]
        if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        os.environ["HUAWEICLOUD_PROJECT_ID"],
    )


def safe_call(label: str, fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception as exc:  # noqa: BLE001 - inventory should continue
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def compact_list(items: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    result = []
    for item in items or []:
        row = {}
        for key in keys:
            value = item.get(key)
            if value is not None:
                row[key] = value
        result.append(row)
    return result


def obs_inventory():
    from obs import ObsClient

    client = ObsClient(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY"],
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_KEY"],
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None,
        server=f"https://obs.{REGION}.myhuaweicloud.com",
    )
    try:
        if not OBS_BUCKET:
            return {"bucket": None, "exists": False, "note": "DEPLOYMENT_OBS_BUCKET not set"}
        prefixes = [
            "raw/dockone_exampleapp/",
            "lake/iceberg/dockone/",
            "publish/dockone_table_metrics/current/",
            "jobs/",
        ]
        rows = {}
        for prefix in prefixes:
            resp = client.listObjects(OBS_BUCKET, prefix=prefix, max_keys=50)
            status = getattr(resp, "status", 0)
            body = getattr(resp, "body", None)
            contents = getattr(body, "contents", []) if body else []
            rows[prefix] = {
                "status": status,
                "object_count_sample": len(contents or []),
                "bytes_sample": sum(int(getattr(obj, "size", 0) or 0) for obj in contents or []),
            }
        return {"bucket": OBS_BUCKET, "prefixes": rows}
    finally:
        client.close()


def vpc_inventory():
    from huaweicloudsdkvpc.v2 import ListSecurityGroupsRequest, ListSubnetsRequest, ListVpcsRequest, VpcClient
    from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion

    client = VpcClient.new_builder().with_credentials(creds()).with_region(VpcRegion.value_of(REGION)).build()
    vpcs = client.list_vpcs(ListVpcsRequest(limit=100)).to_json_object().get("vpcs") or []
    subnets = client.list_subnets(ListSubnetsRequest(limit=100)).to_json_object().get("subnets") or []
    sgs = client.list_security_groups(ListSecurityGroupsRequest(limit=100)).to_json_object().get("security_groups") or []
    return {
        "vpcs": compact_list(vpcs, ["id", "name", "cidr", "status"]),
        "subnets": compact_list(subnets, ["id", "name", "cidr", "gateway_ip", "vpc_id", "status"]),
        "security_groups": compact_list(sgs, ["id", "name", "description", "vpc_id"]),
    }


def ecs_inventory():
    from huaweicloudsdkecs.v2 import EcsClient, ListServersDetailsRequest
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

    client = EcsClient.new_builder().with_credentials(creds()).with_region(EcsRegion.value_of(REGION)).build()
    servers = client.list_servers_details(ListServersDetailsRequest(limit=100)).to_json_object().get("servers") or []
    return compact_list(servers, ["id", "name", "status", "flavor", "addresses"])


def mrs_inventory():
    from huaweicloudsdkmrs.v1 import ListClustersRequest, MrsClient
    from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion

    client = MrsClient.new_builder().with_credentials(creds()).with_region(MrsRegion.value_of(REGION)).build()
    data = client.list_clusters(ListClustersRequest(page_size=100, current_page=1)).to_json_object()
    clusters = data.get("clusters") or []
    return {
        "known_cluster_id": MRS_CLUSTER_ID,
        "clusters": compact_list(
            clusters,
            [
                "cluster_id",
                "cluster_name",
                "cluster_state",
                "node_count",
                "component_list",
                "create_at",
                "billing_type",
            ],
        ),
    }


def dws_inventory():
    from huaweicloudsdkdws.v2 import DwsClient, ListClustersRequest
    from huaweicloudsdkdws.v2.region.dws_region import DwsRegion

    client = DwsClient.new_builder().with_credentials(creds()).with_region(DwsRegion.value_of(REGION)).build()
    clusters = client.list_clusters(ListClustersRequest()).to_json_object().get("clusters") or []
    return compact_list(
        clusters,
        ["id", "name", "status", "version", "public_endpoint", "private_endpoint", "node_type", "number_of_node"],
    )


def dataarts_inventory():
    from huaweicloudsdkdataartsstudio.v1 import (
        DataArtsStudioClient,
        ListFactoryJobsRequest,
        ListWorkspacesRequest,
    )
    from huaweicloudsdkdataartsstudio.v1.region.dataartsstudio_region import DataArtsStudioRegion

    client = (
        DataArtsStudioClient.new_builder()
        .with_credentials(creds())
        .with_region(DataArtsStudioRegion.value_of(REGION))
        .build()
    )
    workspaces = client.list_workspaces(ListWorkspacesRequest(limit=100, offset=0)).to_json_object()
    jobs = {}
    if DATAARTS_WORKSPACE_ID:
        jobs = client.list_factory_jobs(
            ListFactoryJobsRequest(workspace=DATAARTS_WORKSPACE_ID, limit=100, offset=0)
        ).to_json_object()
    return {
        "known_workspace_id": DATAARTS_WORKSPACE_ID,
        "workspaces": workspaces,
        "jobs": jobs,
    }


def rds_inventory():
    from huaweicloudsdkrds.v3 import ListInstancesRequest, RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion

    client = RdsClient.new_builder().with_credentials(creds()).with_region(RdsRegion.value_of(REGION)).build()
    instances = client.list_instances(
        ListInstancesRequest(datastore_type="PostgreSQL", limit=100, offset=0)
    ).to_json_object().get("instances") or []
    return compact_list(
        instances,
        ["id", "name", "status", "type", "datastore", "flavor_ref", "volume", "vpc_id", "subnet_id", "security_group_id"],
    )


def kafka_inventory():
    from huaweicloudsdkkafka.v2 import KafkaClient, ListInstancesRequest
    from huaweicloudsdkkafka.v2.region.kafka_region import KafkaRegion

    client = KafkaClient.new_builder().with_credentials(creds()).with_region(KafkaRegion.value_of(REGION)).build()
    instances = client.list_instances(
        ListInstancesRequest(engine="kafka", limit=10, offset=0)
    ).to_json_object().get("instances") or []
    return compact_list(
        instances,
        [
            "instance_id",
            "name",
            "status",
            "engine",
            "engine_version",
            "specification",
            "connect_address",
            "port",
            "vpc_id",
            "subnet_id",
            "security_group_id",
            "storage_space",
        ],
    )


def main():
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "region": REGION,
        "project_id": PROJECT_ID,
        "checks": {},
    }
    for label, fn in [
        ("obs", obs_inventory),
        ("vpc", vpc_inventory),
        ("ecs", ecs_inventory),
        ("mrs", mrs_inventory),
        ("dws", dws_inventory),
        ("dataarts", dataarts_inventory),
        ("rds_postgresql", rds_inventory),
        ("dms_kafka", kafka_inventory),
    ]:
        out["checks"][label] = safe_call(label, fn)

    output_dir = Path("runs")
    output_dir.mkdir(exist_ok=True)
    path = output_dir / f"huawei-inventory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"inventory_path": str(path), "ok": {k: v["ok"] for k, v in out["checks"].items()}}, indent=2))


if __name__ == "__main__":
    main()
