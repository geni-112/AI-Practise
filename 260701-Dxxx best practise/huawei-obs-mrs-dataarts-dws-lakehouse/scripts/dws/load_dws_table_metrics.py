#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


def parse_args():
    parser = argparse.ArgumentParser(description="Load DockOne Golden metrics CSV into DWS.")
    parser.add_argument("--csv", default=str(Path.cwd() / "runtime" / "dockone_table_metrics.csv"))
    parser.add_argument("--schema", default="dockone_golden")
    parser.add_argument("--host", default=os.environ.get("DWS_HOST"))
    parser.add_argument("--port", default=os.environ.get("DWS_PORT", "8000"))
    parser.add_argument("--database", default=os.environ.get("DWS_DATABASE", "gaussdb"))
    parser.add_argument("--user", default=os.environ.get("DWS_USER", "dbaadmin"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.host:
        raise SystemExit("Missing --host or DWS_HOST")
    csv_path = Path(args.csv).resolve()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    conn = psycopg2.connect(
        host=args.host,
        port=int(args.port),
        dbname=args.database,
        user=args.user,
        password=os.environ["DWS_PASSWORD"],
        connect_timeout=30,
        sslmode="prefer",
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {args.schema}")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {args.schema}.table_metrics_stage (
                    domain VARCHAR(64) NOT NULL,
                    entity VARCHAR(256) NOT NULL,
                    table_name VARCHAR(256) NOT NULL,
                    raw_event_count BIGINT NOT NULL,
                    bronze_event_count BIGINT NOT NULL,
                    active_record_count BIGINT NOT NULL,
                    delete_record_count BIGINT NOT NULL,
                    tenant_count BIGINT NOT NULL,
                    total_amount NUMERIC(38,2),
                    quality_status VARCHAR(32) NOT NULL,
                    loaded_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (table_name)
                )
                """
            )
            cur.execute(f"TRUNCATE TABLE {args.schema}.table_metrics_stage")
            loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
            values = [
                (
                    row["domain"],
                    row["entity"],
                    row["table_name"],
                    int(row["raw_event_count"]),
                    int(row["bronze_event_count"]),
                    int(row["active_record_count"]),
                    int(row["delete_record_count"]),
                    int(row["tenant_count"]),
                    row["total_amount"] or None,
                    row["quality_status"],
                    loaded_at,
                )
                for row in rows
            ]
            execute_values(
                cur,
                f"""
                INSERT INTO {args.schema}.table_metrics_stage (
                    domain, entity, table_name, raw_event_count,
                    bronze_event_count, active_record_count, delete_record_count,
                    tenant_count, total_amount, quality_status, loaded_at
                ) VALUES %s
                """,
                values,
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {args.schema}.table_metrics AS
                SELECT * FROM {args.schema}.table_metrics_stage
                """
            )
            cur.execute(f"TRUNCATE TABLE {args.schema}.table_metrics")
            cur.execute(f"INSERT INTO {args.schema}.table_metrics SELECT * FROM {args.schema}.table_metrics_stage")
            cur.execute(
                f"""
                CREATE OR REPLACE VIEW {args.schema}.table_metrics_bi AS
                SELECT domain, entity, table_name, raw_event_count, bronze_event_count,
                       active_record_count, delete_record_count, tenant_count,
                       total_amount, quality_status, loaded_at
                FROM {args.schema}.table_metrics
                """
            )
            cur.execute(
                f"""
                SELECT COUNT(*), SUM(raw_event_count), SUM(active_record_count),
                       SUM(delete_record_count), COUNT(DISTINCT domain)
                FROM {args.schema}.table_metrics
                """
            )
            count, raw_events, active_records, deletes, domains = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary = {
        "schema": args.schema,
        "rows": count,
        "raw_events": raw_events,
        "active_records": active_records,
        "delete_records": deletes,
        "domains": domains,
        "status": "SUCCEEDED",
    }
    (csv_path.parent.parent / "dws-load-summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, default=str, indent=2))


if __name__ == "__main__":
    main()
