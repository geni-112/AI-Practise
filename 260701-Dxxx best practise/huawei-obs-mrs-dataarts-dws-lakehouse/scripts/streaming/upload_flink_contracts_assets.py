#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from obs import ObsClient


def parse_args():
    parser = argparse.ArgumentParser(description="Upload rendered contracts Flink SQL to OBS.")
    parser.add_argument("--sql", required=True)
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument("--key", default="jobs/flink/contracts_kafka_to_obs.sql")
    parser.add_argument("--summary", default=str(Path.cwd() / "flink-contracts-upload-summary.json"))
    return parser.parse_args()


def obs_client(region):
    return ObsClient(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY"],
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_KEY"],
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None,
        server=f"https://obs.{region}.myhuaweicloud.com",
    )


def main():
    args = parse_args()
    if not args.bucket:
        raise SystemExit("Missing --bucket or DEPLOYMENT_OBS_BUCKET")
    sql_path = Path(args.sql).resolve()
    if not sql_path.exists():
        raise SystemExit(f"SQL file not found: {sql_path}")
    client = obs_client(args.region)
    try:
        response = client.putFile(args.bucket, args.key, str(sql_path))
        if getattr(response, "status", 500) >= 300:
            raise RuntimeError(f"OBS upload failed key={args.key} status={response.status}")
    finally:
        client.close()
    summary = {"bucket": args.bucket, "key": args.key, "bytes": sql_path.stat().st_size}
    Path(args.summary).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
