#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from obs import ObsClient


def parse_args():
    parser = argparse.ArgumentParser(description="Download the latest Golden table metrics CSV from OBS.")
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument("--prefix", default="publish/dockone_table_metrics/current/")
    parser.add_argument("--out", default=str(Path.cwd() / "runtime" / "dockone_table_metrics.csv"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.bucket:
        raise SystemExit("Missing --bucket or DEPLOYMENT_OBS_BUCKET")
    client = ObsClient(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY"],
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_KEY"],
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None,
        server=f"https://obs.{args.region}.myhuaweicloud.com",
    )
    target = Path(args.out).resolve()
    try:
        listed = client.listObjects(args.bucket, prefix=args.prefix)
        objects = getattr(listed.body, "contents", []) or []
        csv_objects = [item for item in objects if item.key.endswith(".csv")]
        if not csv_objects:
            raise RuntimeError("No Golden CSV found")
        selected = max(csv_objects, key=lambda item: getattr(item, "lastModified", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        response = client.getObject(args.bucket, selected.key, downloadPath=str(target))
        if getattr(response, "status", 500) >= 300:
            raise RuntimeError(f"Golden download failed: {response.status}")
    finally:
        client.close()
    summary = {
        "key": selected.key,
        "bytes": target.stat().st_size,
        "download_seconds": round(time.perf_counter() - started, 3),
        "target": str(target),
    }
    (target.parent.parent / "golden-download-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
