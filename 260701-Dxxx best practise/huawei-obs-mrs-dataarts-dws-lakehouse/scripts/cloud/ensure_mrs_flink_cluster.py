#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials


REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
PROJECT_ID = os.environ["HUAWEICLOUD_PROJECT_ID"]
VPC_ID = os.environ.get("STREAM_VPC_ID", "a4dc04af-99d8-488d-af55-f299df4cea85")
VPC_NAME = os.environ.get("MRS_VPC_NAME", "vpc-default-smb")
SUBNET_ID = os.environ.get("STREAM_SUBNET_ID", "f4767f67-4138-4d1b-be53-5448985d4b32")
SUBNET_NAME = os.environ.get("MRS_SUBNET_NAME", "subnet-default-smb")
SECURITY_GROUP_ID = os.environ.get("STREAM_SECURITY_GROUP_ID", "5045eb3c-81c7-4840-950b-06e890836322")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure a dedicated MRS Flink cluster for the DockOne streaming POC.")
    parser.add_argument("--name", default="dockone-stream-flink-mrs")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--components", default="Hadoop,Flink,JobGateway")
    parser.add_argument(
        "--az",
        default="4a5642bf1d7e421a8db631a447e140bc",
        help="MRS v1 create API expects the AZ ID, not the display AZ code.",
    )
    parser.add_argument("--master-num", type=int, default=2)
    parser.add_argument("--core-num", type=int, default=3)
    parser.add_argument("--node-size", default="c6.4xlarge.4.linux.bigdata")
    parser.add_argument("--root-volume-size", type=int, default=480)
    parser.add_argument("--data-volume-size", type=int, default=600)
    parser.add_argument("--data-volume-count", type=int, default=1)
    return parser.parse_args()


def creds() -> BasicCredentials:
    return BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        PROJECT_ID,
    )


def to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return response if isinstance(response, dict) else {}


def mrs_client_v1():
    from huaweicloudsdkmrs.v1 import MrsClient
    from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion

    return MrsClient.new_builder().with_credentials(creds()).with_region(MrsRegion.value_of(REGION)).build()


def mrs_client_v2():
    from huaweicloudsdkmrs.v2 import MrsClient
    from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion

    return MrsClient.new_builder().with_credentials(creds()).with_region(MrsRegion.value_of(REGION)).build()


def list_clusters(name: str) -> list[dict]:
    from huaweicloudsdkmrs.v1 import ListClustersRequest

    client = mrs_client_v1()
    data = to_json(client.list_clusters(ListClustersRequest(cluster_name=name, page_size="100", current_page="1")))
    clusters = data.get("clusters") or data.get("cluster_infos") or data.get("cluster_list") or []
    return [item for item in clusters if item.get("clusterName") == name or item.get("cluster_name") == name]


def cluster_detail(cluster_id: str) -> dict:
    from huaweicloudsdkmrs.v1 import ShowClusterDetailsRequest

    data = to_json(mrs_client_v1().show_cluster_details(ShowClusterDetailsRequest(cluster_id=cluster_id)))
    return data.get("cluster") or data


def first_active_cluster(name: str) -> dict | None:
    for item in list_clusters(name):
        cluster_id = item.get("clusterId") or item.get("cluster_id")
        state = str(item.get("clusterState") or item.get("cluster_state") or "").lower()
        if cluster_id and state not in {"terminated", "failed", "error"}:
            try:
                return cluster_detail(cluster_id)
            except Exception:
                return item
    return None


def create_cluster(args: argparse.Namespace) -> dict:
    from huaweicloudsdkmrs.v1 import ComponentAmbV11, CreateClusterReqV11, CreateClusterRequest, Tag

    component_list = [
        ComponentAmbV11(component_name=item.strip())
        for item in args.components.split(",")
        if item.strip()
    ]
    body = CreateClusterReqV11(
        cluster_version="MRS 3.5.0-LTS",
        cluster_name=args.name,
        master_node_num=args.master_num,
        core_node_num=args.core_num,
        billing_type=12,
        data_center=REGION,
        vpc=VPC_NAME,
        master_node_size=args.node_size,
        core_node_size=args.node_size,
        component_list=component_list,
        available_zone_id=args.az,
        vpc_id=VPC_ID,
        subnet_id=SUBNET_ID,
        subnet_name=SUBNET_NAME,
        security_groups_id=SECURITY_GROUP_ID,
        volume_type="SAS",
        volume_size=args.data_volume_size,
        master_data_volume_type="SAS",
        master_data_volume_size=args.data_volume_size,
        master_data_volume_count=args.data_volume_count,
        core_data_volume_type="SAS",
        core_data_volume_size=args.data_volume_size,
        core_data_volume_count=args.data_volume_count,
        cluster_admin_secret=os.environ["MRS_PASSWORD"],
        cluster_master_secret=os.environ["MRS_PASSWORD"],
        safe_mode=0,
        # MRS 3.5.0-LTS metadata lists Flink as available for analysis/mixed/custom,
        # not streaming. The v1 API uses 0 for analysis clusters.
        cluster_type=0,
        log_collection=0,
        login_mode=0,
        enterprise_project_id="0",
        tags=[
            Tag(key="project", value="dockone-streaming"),
            Tag(key="purpose", value="rds-dms-mrs-flink-obs"),
            Tag(key="managedBy", value="codex"),
        ],
    )
    response = to_json(mrs_client_v1().create_cluster(CreateClusterRequest(body=body)))
    return response


def wait_running(cluster_id: str, max_wait_seconds: int, poll_seconds: int) -> dict:
    start = time.time()
    last = {}
    while time.time() - start <= max_wait_seconds:
        detail = cluster_detail(cluster_id)
        last = detail
        state = str(detail.get("clusterState") or detail.get("cluster_state") or "").lower()
        print(json.dumps({"poll": "mrs_flink", "cluster_id": cluster_id, "state": state, "stage": detail.get("stageDesc"), "percent": detail.get("stagePercent")}, ensure_ascii=False, default=str), flush=True)
        if state == "running":
            return detail
        if state in {"terminated", "failed", "error"}:
            raise RuntimeError(f"MRS Flink cluster entered {state}: {detail}")
        time.sleep(poll_seconds)
    raise TimeoutError(f"MRS Flink cluster did not reach running in {max_wait_seconds}s: {last}")


def main() -> None:
    args = parse_args()
    Path("runs").mkdir(exist_ok=True)
    existing = first_active_cluster(args.name)
    result: dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "region": REGION,
        "name": args.name,
        "vpc_id": VPC_ID,
        "vpc_name": VPC_NAME,
        "subnet_id": SUBNET_ID,
        "security_group_id": SECURITY_GROUP_ID,
        "components": args.components,
    }
    if existing:
        result["created"] = False
        result["cluster"] = existing
    else:
        response = create_cluster(args)
        cluster_id = response.get("cluster_id") or response.get("clusterId") or response.get("job_flow_id")
        result["created"] = True
        result["create_response"] = response
        result["cluster_id"] = cluster_id
        if args.wait and cluster_id:
            result["cluster"] = wait_running(cluster_id, args.max_wait_seconds, args.poll_seconds)
    cluster = result.get("cluster") or {}
    result["summary"] = {
        "cluster_id": cluster.get("clusterId") or result.get("cluster_id"),
        "cluster_name": cluster.get("clusterName") or args.name,
        "cluster_state": cluster.get("clusterState"),
        "components": [
            item.get("componentName")
            for item in (cluster.get("componentList") or [])
            if item.get("componentName")
        ],
        "master_node_ip": cluster.get("masterNodeIp") or cluster.get("masterNodeIP"),
        "internal_ip": cluster.get("internalIp"),
    }
    path = Path("runs") / f"mrs-flink-cluster-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "path": str(path)}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
