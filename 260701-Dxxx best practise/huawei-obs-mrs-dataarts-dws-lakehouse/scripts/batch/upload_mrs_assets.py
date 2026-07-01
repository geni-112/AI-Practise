#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from obs import ObsClient


def parse_args():
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Upload MRS Iceberg job assets to OBS.")
    parser.add_argument("--data-dir", required=True, help="Generated data directory with manifest.json.")
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument(
        "--iceberg-jar",
        default=os.environ.get("ICEBERG_RUNTIME_JAR"),
        help="Local iceberg-spark-runtime jar path.",
    )
    parser.add_argument(
        "--spark-script",
        default=str(skill_root / "assets" / "mrs" / "dockone_iceberg_lakehouse.py"),
    )
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
    if not args.iceberg_jar:
        raise SystemExit("Missing --iceberg-jar or ICEBERG_RUNTIME_JAR")
    data = Path(args.data_dir).resolve()
    spark_script = Path(args.spark_script).resolve()
    iceberg_jar = Path(args.iceberg_jar).resolve()
    assets = [
        (spark_script, "jobs/mrs/dockone_iceberg_lakehouse.py"),
        (data / "manifest.json", "config/dockone/manifest.json"),
        (iceberg_jar, f"jobs/jars/{iceberg_jar.name}"),
    ]
    schema = data / "schema" / "inferred-table-schemas.json"
    if schema.exists():
        assets.append((schema, "config/dockone/inferred-table-schemas.json"))

    client = obs_client(args.region)
    summary = []
    try:
        for source, key in assets:
            if not source.exists():
                raise SystemExit(f"Missing deployment asset: {source}")
            response = client.putFile(args.bucket, key, str(source))
            if getattr(response, "status", 500) >= 300:
                raise RuntimeError(f"OBS upload failed key={key} status={response.status}")
            summary.append({"key": key, "bytes": source.stat().st_size})
            print(f"uploaded obs://{args.bucket}/{key} bytes={source.stat().st_size}")
    finally:
        client.close()
    result = {"bucket": args.bucket, "object_count": len(summary), "objects": summary}
    (data.parent / "mrs-assets-upload-summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({"bucket": args.bucket, "object_count": len(summary)}, indent=2))


if __name__ == "__main__":
    main()
