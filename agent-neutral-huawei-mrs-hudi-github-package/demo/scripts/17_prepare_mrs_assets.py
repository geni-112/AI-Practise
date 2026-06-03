from __future__ import annotations

import argparse
import os
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUDI_VERSION = "0.15.0"
HUDI_JAR = f"hudi-spark3.3-bundle_2.12-{HUDI_VERSION}.jar"
HUDI_URL = f"https://repo1.maven.org/maven2/org/apache/hudi/hudi-spark3.3-bundle_2.12/{HUDI_VERSION}/{HUDI_JAR}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MRS assets such as the Hudi Spark bundle.")
    parser.add_argument("--execute", action="store_true", help="Download and upload assets. Default is dry-run.")
    args = parser.parse_args()

    bucket = os.environ.get("DEMO_BUCKET", "docktest")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    jar_path = dist / HUDI_JAR
    obs_target = f"obs://{bucket}/jobs/jars/{HUDI_JAR}"

    if not args.execute:
        print(f"DRY RUN would ensure local {jar_path}")
        print(f"DRY RUN would upload {jar_path} -> {obs_target}")
        return

    if not jar_path.exists():
        print(f"downloading {HUDI_URL}")
        urllib.request.urlretrieve(HUDI_URL, jar_path)

    try:
        from obs import ObsClient
    except ImportError as exc:
        raise SystemExit("Install OBS SDK first: pip install esdk-obs-python") from exc

    ak = os.environ["HUAWEICLOUD_ACCESS_KEY"]
    sk = os.environ["HUAWEICLOUD_SECRET_KEY"]
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None
    endpoint = os.environ.get("OBS_ENDPOINT", "https://obs.la-south-2.myhuaweicloud.com")
    client = ObsClient(access_key_id=ak, secret_access_key=sk, security_token=security_token, server=endpoint)
    key = f"jobs/jars/{HUDI_JAR}"
    resp = client.putFile(bucket, key, str(jar_path))
    status = getattr(resp, "status", None)
    if status and status >= 300:
        raise RuntimeError(f"Upload failed {jar_path} -> {obs_target}: {status}")
    print(f"uploaded {jar_path} -> {obs_target}")


if __name__ == "__main__":
    main()
