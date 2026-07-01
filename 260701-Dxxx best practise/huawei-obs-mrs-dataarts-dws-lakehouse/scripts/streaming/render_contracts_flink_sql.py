#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from string import Template


def parse_args():
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Render Flink SQL for DMS Kafka billing.contracts to OBS raw JSON.")
    parser.add_argument("--template", default=str(skill_root / "assets" / "flink" / "contracts_kafka_to_obs.sql.tpl"))
    parser.add_argument("--out", default=str(Path.cwd() / "dockone-stream-run" / "flink_contracts_kafka_to_obs.sql"))
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET", "<OBS_BUCKET>"))
    parser.add_argument("--topic", default=os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts"))
    parser.add_argument("--bootstrap-servers", default=os.environ.get("DMS_KAFKA_BOOTSTRAP_SERVERS", "<DMS_KAFKA_BOOTSTRAP_SERVERS>"))
    parser.add_argument("--group-id", default=os.environ.get("DMS_KAFKA_GROUP_ID", "mrs-flink-contracts-to-obs"))
    parser.add_argument("--scan-startup-mode", default=os.environ.get("DMS_KAFKA_SCAN_STARTUP_MODE", "earliest-offset"))
    parser.add_argument("--security-protocol", default=os.environ.get("DMS_KAFKA_SECURITY_PROTOCOL"))
    parser.add_argument("--sasl-mechanism", default=os.environ.get("DMS_KAFKA_SASL_MECHANISM"))
    parser.add_argument("--sasl-username", default=os.environ.get("DMS_KAFKA_USERNAME"))
    parser.add_argument("--sasl-password-placeholder", default="${DMS_KAFKA_PASSWORD}")
    return parser.parse_args()


def sql_quote(value: str) -> str:
    return str(value).replace("'", "''")


def security_properties(args) -> str:
    lines = []
    if args.security_protocol:
        lines.append(f"  'properties.security.protocol' = '{sql_quote(args.security_protocol)}',")
    if args.sasl_mechanism:
        lines.append(f"  'properties.sasl.mechanism' = '{sql_quote(args.sasl_mechanism)}',")
    if args.sasl_username:
        jaas = (
            "org.apache.kafka.common.security.plain.PlainLoginModule required "
            f'username="{args.sasl_username}" password="{args.sasl_password_placeholder}";'
        )
        lines.append(f"  'properties.sasl.jaas.config' = '{sql_quote(jaas)}',")
    return ("\n".join(lines) + "\n") if lines else ""


def main():
    args = parse_args()
    template = Template(Path(args.template).read_text(encoding="utf-8"))
    obs_raw_path = (
        f"obs://{args.bucket}/raw/dockone_exampleapp/"
        "kfk.prd.cdc.dockone_exampleapp.billing.contracts"
    )
    rendered = template.safe_substitute(
        kafka_topic=sql_quote(args.topic),
        kafka_bootstrap_servers=sql_quote(args.bootstrap_servers),
        kafka_group_id=sql_quote(args.group_id),
        kafka_security_properties=security_properties(args),
        scan_startup_mode=sql_quote(args.scan_startup_mode),
        obs_raw_path=sql_quote(obs_raw_path),
    )
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
