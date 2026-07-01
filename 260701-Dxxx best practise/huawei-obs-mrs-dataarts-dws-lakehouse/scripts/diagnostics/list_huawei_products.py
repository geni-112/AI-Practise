#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from huaweicloudsdkcore.auth.credentials import BasicCredentials


REGION = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
PROJECT_ID = os.environ["HUAWEICLOUD_PROJECT_ID"]


def creds() -> BasicCredentials:
    return BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        PROJECT_ID,
    )


def safe(label, fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def rds_datastores():
    from huaweicloudsdkrds.v3 import ListDatastoresRequest, RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion

    client = RdsClient.new_builder().with_credentials(creds()).with_region(RdsRegion.value_of(REGION)).build()
    return client.list_datastores(ListDatastoresRequest(database_name="PostgreSQL")).to_json_object()


def rds_flavors():
    from huaweicloudsdkrds.v3 import ListFlavorsRequest, RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion

    client = RdsClient.new_builder().with_credentials(creds()).with_region(RdsRegion.value_of(REGION)).build()
    return client.list_flavors(ListFlavorsRequest(database_name="PostgreSQL")).to_json_object()


def kafka_products():
    from huaweicloudsdkkafka.v2 import KafkaClient, ListEngineProductsRequest
    from huaweicloudsdkkafka.v2.region.kafka_region import KafkaRegion

    client = KafkaClient.new_builder().with_credentials(creds()).with_region(KafkaRegion.value_of(REGION)).build()
    return client.list_engine_products(ListEngineProductsRequest(engine="kafka")).to_json_object()


def kafka_instances():
    from huaweicloudsdkkafka.v2 import KafkaClient, ListInstancesRequest
    from huaweicloudsdkkafka.v2.region.kafka_region import KafkaRegion

    client = KafkaClient.new_builder().with_credentials(creds()).with_region(KafkaRegion.value_of(REGION)).build()
    return client.list_instances(ListInstancesRequest(engine="kafka", limit=10, offset=0)).to_json_object()


def main():
    out = {
        "region": REGION,
        "rds_datastores": safe("rds_datastores", rds_datastores),
        "rds_flavors": safe("rds_flavors", rds_flavors),
        "kafka_products": safe("kafka_products", kafka_products),
        "kafka_instances": safe("kafka_instances", kafka_instances),
    }
    Path("runs").mkdir(exist_ok=True)
    path = Path("runs") / "huawei-products.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "path": str(path),
        "ok": {k: v["ok"] for k, v in out.items() if isinstance(v, dict) and "ok" in v},
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
