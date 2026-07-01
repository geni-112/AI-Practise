#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from obs import ObsClient


def parse_args():
    parser = argparse.ArgumentParser(description="Upload DockOne raw CDC files to OBS.")
    parser.add_argument("--data-dir", required=True, help="Generated data directory.")
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
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
    data = Path(args.data_dir).resolve()
    raw_map = json.loads((data / "raw-map.json").read_text(encoding="utf-8"))
    client = obs_client(args.region)
    started = time.perf_counter()
    objects = []
    try:
        for item in raw_map:
            source = data / item["local_file"]
            response = client.putFile(args.bucket, item["obs_key"], str(source))
            if getattr(response, "status", 500) >= 300:
                raise RuntimeError(f"OBS upload failed: {item['obs_key']} status={response.status}")
            objects.append({"key": item["obs_key"], "bytes": source.stat().st_size})
        response = client.putFile(
            args.bucket, "config/dockone/manifest.json", str(data / "manifest.json")
        )
        if getattr(response, "status", 500) >= 300:
            raise RuntimeError("OBS manifest upload failed")
    finally:
        client.close()

    elapsed = time.perf_counter() - started
    total_bytes = sum(item["bytes"] for item in objects)
    summary = {
        "bucket": args.bucket,
        "objects": len(objects),
        "bytes": total_bytes,
        "size_mib": round(total_bytes / 1024 / 1024, 6),
        "upload_seconds": round(elapsed, 3),
        "throughput_mib_per_second": round(total_bytes / 1024 / 1024 / elapsed, 3),
    }
    (data.parent / "upload-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
