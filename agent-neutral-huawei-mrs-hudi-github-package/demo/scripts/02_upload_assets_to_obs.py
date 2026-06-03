from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = Path(
    os.environ.get(
        "SYNTHETIC_CDC_DATA_PATH",
        ROOT.parents[1] / "data",
    )
)


def iter_uploads(bucket: str):
    for path in (ROOT / "dist").glob("*.py"):
        yield path, f"obs://{bucket}/jobs/dli/{path.name}"
    for path in (ROOT / "sql" / "dli").glob("*.sql"):
        yield path, f"obs://{bucket}/jobs/sql/{path.name}"
    raw_map = SOURCE_DATA / "raw-map.json"
    if raw_map.exists():
        for item in json.loads(raw_map.read_text(encoding="utf-8-sig")):
            yield SOURCE_DATA / item["local_file"], f"obs://{bucket}/{item['obs_key']}"
    else:
        for path in SOURCE_DATA.joinpath("raw").rglob("*.json"):
            rel = path.relative_to(SOURCE_DATA)
            yield path, f"obs://{bucket}/{rel.as_posix()}"
    for path in SOURCE_DATA.joinpath("schema").glob("*"):
        yield path, f"obs://{bucket}/schema/{path.name}"


def main():
    parser = argparse.ArgumentParser(description="Upload demo assets to OBS")
    parser.add_argument("--execute", action="store_true", help="Actually upload. Default is dry-run.")
    args = parser.parse_args()
    bucket = os.environ.get("DEMO_BUCKET")
    if not bucket:
        raise SystemExit("DEMO_BUCKET is required")

    uploads = list(iter_uploads(bucket))
    if not args.execute:
        print("DRY RUN: would upload:")
        for src, dst in uploads[:20]:
            print(f"  {src} -> {dst}")
        print(f"  ... total objects: {len(uploads)}")
        return

    try:
        from obs import ObsClient
    except ImportError as exc:
        raise SystemExit("Install OBS SDK first: pip install esdk-obs-python") from exc

    ak = os.environ["HUAWEICLOUD_ACCESS_KEY"]
    sk = os.environ["HUAWEICLOUD_SECRET_KEY"]
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None
    endpoint = os.environ["OBS_ENDPOINT"]
    client = ObsClient(access_key_id=ak, secret_access_key=sk, security_token=security_token, server=endpoint)
    for src, dst in uploads:
        key = dst.split(f"obs://{bucket}/", 1)[1]
        resp = client.putFile(bucket, key, str(src))
        status = getattr(resp, "status", None)
        if status and status >= 300:
            raise RuntimeError(f"Upload failed {src} -> {dst}: {status}")
        print(f"uploaded {src} -> {dst}")


if __name__ == "__main__":
    main()
