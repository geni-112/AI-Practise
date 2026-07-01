#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkecs.v2 import (
    CreatePostPaidServersRequest,
    CreatePostPaidServersRequestBody,
    EcsClient,
    ListServersDetailsRequest,
    PostPaidServer,
    PostPaidServerEip,
    PostPaidServerEipBandwidth,
    PostPaidServerExtendParam,
    PostPaidServerNic,
    PostPaidServerPublicip,
    PostPaidServerRootVolume,
    PostPaidServerSecurityGroup,
    ShowServerRequest,
)
from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion


REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
PROJECT_ID = os.environ["HUAWEICLOUD_PROJECT_ID"]
VPC_ID = os.environ.get("STREAM_VPC_ID", "a4dc04af-99d8-488d-af55-f299df4cea85")
SUBNET_ID = os.environ.get("STREAM_SUBNET_ID", "f4767f67-4138-4d1b-be53-5448985d4b32")
MONITOR_WEB_SG_ID = os.environ.get("RUNNER_SECURITY_GROUP_ID", "74efd90d-7831-4d7f-ba71-46c01e317bb5")
UBUNTU_2404_IMAGE_ID = os.environ.get("RUNNER_IMAGE_ID", "c564385e-8f39-4d22-955f-e11005724221")


def creds():
    return BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        PROJECT_ID,
    )


def client():
    return EcsClient.new_builder().with_credentials(creds()).with_region(EcsRegion.value_of(REGION)).build()


def find_server(name: str):
    rows = client().list_servers_details(ListServersDetailsRequest(name=name, limit=100)).to_json_object().get("servers") or []
    for row in rows:
        if row.get("name") == name:
            return row
    return None


def show_server(server_id: str):
    return client().show_server(ShowServerRequest(server_id=server_id)).to_json_object().get("server") or {}


def cloud_init() -> str:
    text = """#cloud-config
disable_root: false
ssh_pwauth: true
chpasswd:
  expire: false
runcmd:
  - sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
  - sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart ssh || systemctl restart sshd
"""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def create_server(name: str):
    existing = find_server(name)
    if existing:
        return {"created": False, "server_ids": [existing.get("id")], "existing": existing}
    server = PostPaidServer(
        name=name,
        image_ref=UBUNTU_2404_IMAGE_ID,
        flavor_ref="s6.large.2",
        vpcid=VPC_ID,
        availability_zone="la-south-2a",
        admin_pass=os.environ["DWS_PASSWORD"],
        root_volume=PostPaidServerRootVolume(volumetype="GPSSD", size=40),
        nics=[PostPaidServerNic(subnet_id=SUBNET_ID)],
        security_groups=[PostPaidServerSecurityGroup(id=MONITOR_WEB_SG_ID)],
        publicip=PostPaidServerPublicip(
            eip=PostPaidServerEip(
                iptype="5_bgp",
                bandwidth=PostPaidServerEipBandwidth(size=5, sharetype="PER", chargemode="traffic"),
            ),
            delete_on_termination=True,
        ),
        extendparam=PostPaidServerExtendParam(charging_mode="postPaid", region_id=REGION),
        user_data=cloud_init(),
        description="Temporary private-network runner for DockOne RDS/DMS Kafka streaming POC",
    )
    resp = client().create_post_paid_servers(
        CreatePostPaidServersRequest(body=CreatePostPaidServersRequestBody(server=server))
    ).to_json_object()
    return {"created": True, **resp}


def public_ip(server: dict) -> str | None:
    addresses = server.get("addresses") or {}
    for rows in addresses.values():
        for item in rows:
            if item.get("OS-EXT-IPS:type") == "floating":
                return item.get("addr")
    return None


def main():
    name = os.environ.get("RUNNER_ECS_NAME", "dockone-stream-runner-ecs")
    Path("runs").mkdir(exist_ok=True)
    create = create_server(name)
    server_id = (create.get("server_ids") or create.get("serverIds") or [None])[0]
    if not server_id:
        raise SystemExit(f"No server id returned: {create}")
    last = None
    for _ in range(80):
        item = show_server(server_id)
        last = item
        print(json.dumps({"poll": "runner_ecs", "id": server_id, "status": item.get("status"), "public_ip": public_ip(item)}), flush=True)
        if item.get("status") == "ACTIVE" and public_ip(item):
            out = {"created": create.get("created"), "server": item, "public_ip": public_ip(item)}
            path = Path("runs") / "runner-ecs.json"
            path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            print(json.dumps({"path": str(path), "server_id": server_id, "public_ip": public_ip(item)}, indent=2))
            return
        time.sleep(15)
    raise TimeoutError(f"Runner ECS not ready. Last={last}")


if __name__ == "__main__":
    main()
