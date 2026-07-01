#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from huaweicloudsdkcore.auth.credentials import BasicCredentials


REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
PROJECT_ID = os.environ["HUAWEICLOUD_PROJECT_ID"]
VPC_ID = os.environ.get("STREAM_VPC_ID", "a4dc04af-99d8-488d-af55-f299df4cea85")
SUBNET_ID = os.environ.get("STREAM_SUBNET_ID", "f4767f67-4138-4d1b-be53-5448985d4b32")
SECURITY_GROUP_ID = os.environ.get("STREAM_SECURITY_GROUP_ID", "5045eb3c-81c7-4840-950b-06e890836322")
KAFKA_AZ_ID = os.environ.get("DMS_KAFKA_AZ_ID", "4a5642bf1d7e421a8db631a447e140bc")


def parse_args():
    parser = argparse.ArgumentParser(description="Ensure real RDS PostgreSQL and DMS Kafka resources for the DockOne stream POC.")
    parser.add_argument("--rds-name", default="dockone-stream-rds-pg")
    parser.add_argument("--kafka-name", default="dockone-stream-dms-kafka")
    parser.add_argument("--current-public-cidr", required=True)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=3600)
    parser.add_argument("--rds-public", action="store_true", help="Allocate and bind an EIP to RDS. Default is private-only.")
    parser.add_argument("--kafka-public", action="store_true", help="Allocate and bind an EIP to DMS Kafka. Default is private-only.")
    return parser.parse_args()


def creds() -> BasicCredentials:
    return BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        PROJECT_ID,
    )


def j(obj):
    return obj.to_json_object() if hasattr(obj, "to_json_object") else obj


def now():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def log(stage: str, **kwargs):
    print(json.dumps({"stage": stage, **kwargs}, ensure_ascii=False, default=str), flush=True)


def eip_client():
    from huaweicloudsdkeip.v2 import EipClient
    from huaweicloudsdkeip.v2.region.eip_region import EipRegion

    return EipClient.new_builder().with_credentials(creds()).with_region(EipRegion.value_of(REGION)).build()


def rds_client():
    from huaweicloudsdkrds.v3 import RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion

    return RdsClient.new_builder().with_credentials(creds()).with_region(RdsRegion.value_of(REGION)).build()


def kafka_client():
    from huaweicloudsdkkafka.v2 import KafkaClient
    from huaweicloudsdkkafka.v2.region.kafka_region import KafkaRegion

    return KafkaClient.new_builder().with_credentials(creds()).with_region(KafkaRegion.value_of(REGION)).build()


def vpc_client():
    from huaweicloudsdkvpc.v2 import VpcClient
    from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion

    return VpcClient.new_builder().with_credentials(creds()).with_region(VpcRegion.value_of(REGION)).build()


def find_eip(alias: str):
    from huaweicloudsdkeip.v2 import ListPublicipsRequest

    client = eip_client()
    rows = j(client.list_publicips(ListPublicipsRequest(limit=100))).get("publicips") or []
    for row in rows:
        if row.get("alias") == alias:
            return row
    return None


def create_eip(alias: str):
    from huaweicloudsdkeip.v2 import (
        CreatePublicipBandwidthOption,
        CreatePublicipOption,
        CreatePublicipRequest,
        CreatePublicipRequestBody,
    )

    existing = find_eip(alias)
    if existing:
        return {"created": False, "publicip": existing}
    body = CreatePublicipRequestBody(
        publicip=CreatePublicipOption(type="5_bgp", ip_version=4, alias=alias),
        bandwidth=CreatePublicipBandwidthOption(
            name=f"{alias}-bw",
            share_type="PER",
            charge_mode="traffic",
            size=5,
        ),
    )
    resp = j(eip_client().create_publicip(CreatePublicipRequest(body=body)))
    return {"created": True, "publicip": resp.get("publicip") or resp}


def ensure_sg_rule(port: int, cidr: str, description: str):
    from huaweicloudsdkvpc.v2 import (
        CreateSecurityGroupRuleOption,
        CreateSecurityGroupRuleRequest,
        CreateSecurityGroupRuleRequestBody,
        ListSecurityGroupRulesRequest,
    )

    client = vpc_client()
    rows = j(client.list_security_group_rules(ListSecurityGroupRulesRequest(security_group_id=SECURITY_GROUP_ID, limit=200))).get("security_group_rules") or []
    for row in rows:
        if (
            row.get("direction") == "ingress"
            and str(row.get("protocol")).lower() == "tcp"
            and row.get("port_range_min") == port
            and row.get("port_range_max") == port
            and row.get("remote_ip_prefix") == cidr
        ):
            return {"created": False, "id": row.get("id"), "port": port, "cidr": cidr}
    body = CreateSecurityGroupRuleRequestBody(
        security_group_rule=CreateSecurityGroupRuleOption(
            security_group_id=SECURITY_GROUP_ID,
            description=description,
            direction="ingress",
            ethertype="IPv4",
            protocol="tcp",
            port_range_min=port,
            port_range_max=port,
            remote_ip_prefix=cidr,
        )
    )
    resp = j(client.create_security_group_rule(CreateSecurityGroupRuleRequest(body=body)))
    return {"created": True, "id": (resp.get("security_group_rule") or {}).get("id"), "port": port, "cidr": cidr}


def find_rds(name: str):
    from huaweicloudsdkrds.v3 import ListInstancesRequest

    rows = j(rds_client().list_instances(ListInstancesRequest(datastore_type="PostgreSQL", name=name, limit=100, offset=0))).get("instances") or []
    for row in rows:
        if row.get("name") == name:
            return row
    return None


def create_rds(name: str):
    from huaweicloudsdkrds.v3 import (
        BackupStrategy,
        ChargeInfo,
        CreateInstanceRequest,
        CustomerCreateInstanceReq,
        Datastore,
        Volume,
    )

    existing = find_rds(name)
    if existing:
        return {"created": False, "instance": existing}
    body = CustomerCreateInstanceReq(
        name=name,
        datastore=Datastore(type="PostgreSQL", version="16"),
        flavor_ref="rds.pg.n1.large.2",
        volume=Volume(type="CLOUDSSD", size=40),
        region=REGION,
        availability_zone="la-south-2a",
        vpc_id=VPC_ID,
        subnet_id=SUBNET_ID,
        security_group_id=SECURITY_GROUP_ID,
        port="5432",
        password=os.environ["RDS_PGPASSWORD"],
        backup_strategy=BackupStrategy(start_time="03:00-04:00", keep_days=1),
        charge_info=ChargeInfo(charge_mode="postPaid"),
    )
    resp = j(rds_client().create_instance(CreateInstanceRequest(body=body)))
    return {"created": True, "response": resp}


def get_rds(instance_id: str):
    from huaweicloudsdkrds.v3 import ListInstancesRequest

    rows = j(rds_client().list_instances(ListInstancesRequest(id=instance_id, limit=100, offset=0))).get("instances") or []
    return rows[0] if rows else None


def wait_rds(instance_id: str, max_wait_seconds: int):
    start = time.time()
    last = None
    while time.time() - start < max_wait_seconds:
        item = get_rds(instance_id)
        if item:
            last = item
            status = str(item.get("status") or "").upper()
            print(json.dumps({"poll": "rds", "id": instance_id, "status": status}))
            if status in {"ACTIVE", "AVAILABLE"}:
                return item
            if status in {"FAILED", "ERROR"}:
                raise RuntimeError(f"RDS entered failure state: {status}")
        time.sleep(30)
    raise TimeoutError(f"RDS did not become available in {max_wait_seconds}s. Last={last}")


def attach_rds_eip(instance_id: str, eip: dict):
    from huaweicloudsdkrds.v3 import AttachEipRequest, BindEipRequest

    public_ip = eip.get("public_ip_address")
    public_ip_id = eip.get("id")
    inst = get_rds(instance_id) or {}
    if inst.get("public_ips"):
        return {"attached": False, "public_ips": inst.get("public_ips")}
    resp = j(rds_client().attach_eip(AttachEipRequest(instance_id=instance_id, body=BindEipRequest(public_ip=public_ip, public_ip_id=public_ip_id, is_bind=True))))
    return {"attached": True, "response": resp, "public_ip": public_ip, "public_ip_id": public_ip_id}


def find_kafka(name: str):
    from huaweicloudsdkkafka.v2 import ListInstancesRequest

    rows = j(kafka_client().list_instances(ListInstancesRequest(engine="kafka", name=name, limit=10, offset=0))).get("instances") or []
    for row in rows:
        if row.get("name") == name:
            return row
    return None


def create_kafka(name: str, eip: dict | None = None):
    from huaweicloudsdkkafka.v2 import CreateInstanceByEngineReq, CreatePostPaidKafkaInstanceRequest

    existing = find_kafka(name)
    if existing:
        return {"created": False, "instance": existing}
    body = CreateInstanceByEngineReq(
        name=name,
        description="DockOne streaming POC DMS Kafka",
        engine="kafka",
        engine_version="3.x",
        broker_num=1,
        storage_space=100,
        access_user=os.environ.get("DMS_KAFKA_USERNAME", "dockone"),
        password=os.environ["DMS_KAFKA_PASSWORD"],
        vpc_id=VPC_ID,
        security_group_id=SECURITY_GROUP_ID,
        subnet_id=SUBNET_ID,
        available_zones=[KAFKA_AZ_ID],
        product_id="s6.2u4g.single.small",
        maintain_begin="02:00",
        maintain_end="06:00",
        enable_publicip=bool(eip),
        publicip_id=(eip or {}).get("id"),
        ssl_enable=True,
        kafka_security_protocol="SASL_SSL",
        sasl_enabled_mechanisms=["PLAIN"],
        storage_spec_code="dms.physical.storage.high.v2",
        enable_auto_topic=True,
        vpc_client_plain=True,
    )
    resp = j(kafka_client().create_post_paid_kafka_instance(CreatePostPaidKafkaInstanceRequest(body=body)))
    return {"created": True, "response": resp}


def wait_kafka(name: str, max_wait_seconds: int):
    start = time.time()
    last = None
    while time.time() - start < max_wait_seconds:
        item = find_kafka(name)
        if item:
            last = item
            status = str(item.get("status") or "").upper()
            print(json.dumps({"poll": "kafka", "id": item.get("instance_id"), "status": status}))
            if status in {"RUNNING", "AVAILABLE"}:
                return item
            if status in {"FAULTY", "CREATEFAILED", "FAILED", "ERROR"}:
                raise RuntimeError(f"Kafka entered failure state: {status}")
        time.sleep(30)
    raise TimeoutError(f"Kafka did not become available in {max_wait_seconds}s. Last={last}")


def main():
    args = parse_args()
    Path("runs").mkdir(exist_ok=True)

    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "region": REGION,
        "vpc_id": VPC_ID,
        "subnet_id": SUBNET_ID,
        "security_group_id": SECURITY_GROUP_ID,
        "security_group_rules": [
            ensure_sg_rule(5432, args.current_public_cidr, "Temporary RDS PostgreSQL access for Codex POC load"),
            ensure_sg_rule(9092, args.current_public_cidr, "Temporary Kafka plaintext/public access for Codex POC publish"),
            ensure_sg_rule(9093, args.current_public_cidr, "Temporary Kafka SASL access for Codex POC publish"),
            ensure_sg_rule(9094, args.current_public_cidr, "Temporary Kafka SASL_SSL access for Codex POC publish"),
        ],
        "eips": {},
        "rds": {},
        "kafka": {},
    }

    log("ensure_eips", rds_public=args.rds_public, kafka_public=args.kafka_public)
    rds_eip = create_eip(f"{args.rds_name}-eip") if args.rds_public else None
    kafka_eip = create_eip(f"{args.kafka_name}-eip") if args.kafka_public else None
    result["eips"]["rds"] = rds_eip
    result["eips"]["kafka"] = kafka_eip

    log("ensure_rds", name=args.rds_name)
    rds = create_rds(args.rds_name)
    result["rds"]["ensure"] = rds
    rds_id = ((rds.get("instance") or {}).get("id") or (rds.get("response") or {}).get("instance", {}).get("id") or (rds.get("response") or {}).get("id"))
    if rds_id and args.wait:
        log("wait_rds", id=rds_id)
        result["rds"]["available"] = wait_rds(rds_id, args.max_wait_seconds)
        if rds_eip:
            log("attach_rds_eip", id=rds_id)
            result["rds"]["eip"] = attach_rds_eip(rds_id, (rds_eip.get("publicip") or {}))

    log("ensure_kafka", name=args.kafka_name, public=bool(kafka_eip))
    kafka = create_kafka(args.kafka_name, (kafka_eip.get("publicip") or {}) if kafka_eip else None)
    result["kafka"]["ensure"] = kafka
    if args.wait:
        log("wait_kafka", name=args.kafka_name)
        result["kafka"]["available"] = wait_kafka(args.kafka_name, args.max_wait_seconds)

    # Emit only non-secret connection outputs.
    available_rds = result["rds"].get("available") or find_rds(args.rds_name) or {}
    available_kafka = result["kafka"].get("available") or find_kafka(args.kafka_name) or {}
    summary = {
        "rds_id": available_rds.get("id") or rds_id,
        "rds_name": args.rds_name,
        "rds_status": available_rds.get("status"),
        "rds_public_ips": available_rds.get("public_ips"),
        "kafka_id": available_kafka.get("instance_id"),
        "kafka_name": args.kafka_name,
        "kafka_status": available_kafka.get("status"),
        "kafka_connect_address": available_kafka.get("connect_address"),
        "kafka_public_connect_address": available_kafka.get("public_connect_address"),
        "topic": os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts"),
    }
    result["summary"] = summary
    path = Path("runs") / f"stream-resources-{now()}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"summary": summary, "path": str(path)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
