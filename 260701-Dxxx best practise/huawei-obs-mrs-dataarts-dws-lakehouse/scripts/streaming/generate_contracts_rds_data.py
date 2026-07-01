#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


CONTRACT_COLUMNS = [
    "id",
    "client_id",
    "product_id",
    "account_id",
    "person_id",
    "external_id",
    "description",
    "status",
    "overdue_at",
    "amount_asset_iso_code",
    "created_at",
    "updated_at",
    "profile_id",
    "cycle_id",
    "first_due_date",
    "effective_date",
    "contracted_amount",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate 5-10 MiB synthetic RDS billing.contracts data and CDC JSON."
    )
    parser.add_argument("--target-mib", type=float, default=8.0)
    parser.add_argument("--out", default=str(Path.cwd() / "dockone-stream-run" / "data"))
    parser.add_argument("--seed", type=int, default=20260628)
    return parser.parse_args()


def uuid7(rng: random.Random, ts_ms: int | None = None) -> str:
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    timestamp = ts_ms & ((1 << 48) - 1)
    rand_a = rng.getrandbits(12)
    rand_b = rng.getrandbits(62)
    value = (timestamp << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return str(uuid.UUID(int=value))


def iso_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money(rng: random.Random) -> str:
    cents = rng.randint(3000, 50000000)
    fraction = rng.randint(0, 999999)
    return f"{Decimal(cents) / Decimal('100') + Decimal(fraction) / Decimal('100000000'):.8f}"


def make_row(rng: random.Random, index: int, base: datetime, pools: dict[str, list[str]]) -> dict[str, str | None]:
    created = base + timedelta(seconds=index * 7 + rng.randint(0, 120))
    updated = created + timedelta(days=rng.randint(0, 90), seconds=rng.randint(0, 86400))
    effective = created + timedelta(days=rng.randint(-10, 20))
    first_due = (effective + timedelta(days=rng.choice([15, 30, 45, 60]))).date()
    status = rng.choices(
        ["active", "pending", "suspended", "canceled", "overdue"],
        weights=[52, 13, 10, 11, 14],
    )[0]
    overdue_at = updated + timedelta(days=rng.randint(1, 25)) if status == "overdue" else None
    ts_ms = int(created.timestamp() * 1000)
    product_id = rng.choice(pools["products"])
    client_id = rng.choice(pools["clients"])
    return {
        "id": uuid7(rng, ts_ms),
        "client_id": client_id,
        "product_id": product_id,
        "account_id": None if rng.random() < 0.12 else uuid7(rng, ts_ms + rng.randint(1, 999)),
        "person_id": rng.choice(pools["persons"]),
        "external_id": f"CTR-{index:09d}-{rng.randint(1000, 9999)}",
        "description": f"DockOne billing contract {index:09d} for product {product_id[:8]}",
        "status": status,
        "overdue_at": iso_dt(overdue_at),
        "amount_asset_iso_code": rng.choices(["USD", "BRL", "CLP"], weights=[70, 20, 10])[0],
        "created_at": iso_dt(created),
        "updated_at": iso_dt(updated) if rng.random() < 0.85 else None,
        "profile_id": rng.choice(pools["profiles"]),
        "cycle_id": rng.choice(pools["cycles"]),
        "first_due_date": first_due.isoformat(),
        "effective_date": iso_dt(effective),
        "contracted_amount": money(rng),
    }


def cdc_event(row: dict[str, str | None]) -> dict:
    event_dt = row.get("updated_at") or row["created_at"]
    parsed = datetime.fromisoformat(str(event_dt).replace("Z", "+00:00"))
    return {
        "op": "c",
        "ts_ms": int(parsed.timestamp() * 1000),
        "source": {
            "db": "dockone_exampleapp",
            "schema": "billing",
            "table": "contracts",
        },
        "before": None,
        "after": row,
    }


def write_manifest(out_dir: Path, rows: int, raw_bytes: int):
    manifest = {
        "dataset_name": "streaming-dockone-rds-contracts-cdc",
        "format": "cdc-json-lines",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "source_flow": "rds-postgresql-dms-kafka-mrs-flink",
        "tables": [
            {
                "domain": "billing",
                "entity": "contracts",
                "event_count": rows,
                "operation_counts": {"c": rows, "r": 0, "u": 0, "d": 0},
                "raw_path": "raw/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.billing.contracts/part-*.json",
                "schema_field_count": len(CONTRACT_COLUMNS),
                "table_name": "dockone_exampleapp_billing_contracts",
                "task_id": "dockone_silver.dockone_exampleapp_billing_contracts",
            }
        ],
        "raw_json_bytes": raw_bytes,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main():
    args = parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "contracts.csv"
    jsonl_path = out_dir / "contracts_cdc.jsonl"
    summary_path = out_dir / "contracts_generation_summary.json"
    target_bytes = int(args.target_mib * 1024 * 1024)
    rng = random.Random(args.seed)
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    pools = {
        "clients": [uuid7(rng, int(base.timestamp() * 1000) + i) for i in range(160)],
        "products": [uuid7(rng, int(base.timestamp() * 1000) + 1000 + i) for i in range(80)],
        "persons": [uuid7(rng, int(base.timestamp() * 1000) + 2000 + i) for i in range(500)],
        "profiles": [uuid7(rng, int(base.timestamp() * 1000) + 3000 + i) for i in range(120)],
        "cycles": [uuid7(rng, int(base.timestamp() * 1000) + 4000 + i) for i in range(24)],
    }

    rows = 0
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file, jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        writer = csv.DictWriter(csv_file, fieldnames=CONTRACT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        while jsonl_file.tell() < target_bytes:
            rows += 1
            row = make_row(rng, rows, base, pools)
            writer.writerow({key: "" if row[key] is None else row[key] for key in CONTRACT_COLUMNS})
            jsonl_file.write(json.dumps(cdc_event(row), separators=(",", ":"), ensure_ascii=False) + "\n")

    raw_bytes = jsonl_path.stat().st_size
    write_manifest(out_dir, rows, raw_bytes)
    summary = {
        "rows": rows,
        "target_mib": args.target_mib,
        "raw_json_bytes": raw_bytes,
        "raw_json_mib": round(raw_bytes / 1024 / 1024, 3),
        "csv_bytes": csv_path.stat().st_size,
        "csv_path": str(csv_path),
        "cdc_jsonl_path": str(jsonl_path),
        "manifest_path": str(out_dir / "manifest.json"),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
