#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

import psycopg2


DEFAULT_SQL = """
SELECT domain,
       COUNT(*) AS table_count,
       SUM(raw_event_count) AS raw_events,
       SUM(active_record_count) AS active_records,
       SUM(delete_record_count) AS delete_records
FROM dockone_golden.table_metrics_bi
GROUP BY domain
ORDER BY domain
"""


def parse_args():
    parser = argparse.ArgumentParser(description="Query DockOne Golden objects in DWS.")
    parser.add_argument("--host", default=os.environ.get("DWS_HOST"))
    parser.add_argument("--port", default=os.environ.get("DWS_PORT", "8000"))
    parser.add_argument("--database", default=os.environ.get("DWS_DATABASE", "gaussdb"))
    parser.add_argument("--user", default=os.environ.get("DWS_USER", "dbaadmin"))
    parser.add_argument("--sql", default=DEFAULT_SQL)
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.host:
        raise SystemExit("Missing --host or DWS_HOST")
    conn = psycopg2.connect(
        host=args.host,
        port=int(args.port),
        dbname=args.database,
        user=args.user,
        password=os.environ["DWS_PASSWORD"],
        connect_timeout=30,
        sslmode="prefer",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(args.sql)
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    print(json.dumps(rows, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
