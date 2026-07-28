from __future__ import annotations

import argparse
import csv
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obs import ObsClient


REGIONS = ["CDMX", "Jalisco", "Nuevo Leon", "Puebla", "Yucatan", "Chiapas"]
REGIMES = ["General", "RESICO", "Persona Fisica", "Persona Moral"]
AGENT_PACKAGE_FILES = [
    "prompt.txt",
    "request.json",
    "run_manifest.json",
    "review_status.json",
    "synthetic_rows.json",
    "gold_preview.json",
    "contract_audit.json",
    "local_execution.json",
    "quality_gates.json",
    "lineage_manifest.json",
    "maas_trace.json",
]


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def make_rows(count: int) -> list[dict[str, object]]:
    rng = random.Random(20250708)
    rows: list[dict[str, object]] = []
    for idx in range(count):
        regime = rng.choice(REGIMES)
        rows.append(
            {
                "taxpayer_id": f"taxpayer-{idx + 1:05d}",
                "rfc": f"RFC{idx + 100000:09d}",
                "year": 2025 if idx % 6 else 2024,
                "region": rng.choice(REGIONS),
                "regime": regime,
                "resico_flag": str(regime == "RESICO").lower(),
                "annual_income": rng.randint(120_000, 2_400_000),
            }
        )
    return rows


def upload_file(client: ObsClient, bucket: str, key: str, path: Path) -> None:
    response = client.putFile(bucket, key, str(path))
    if response.status >= 300:
        raise SystemExit(f"OBS upload failed for {key}: status={response.status}, reason={response.reason}")


def collect_agent_package_files(generated_run_dir: str) -> list[Path]:
    if not generated_run_dir:
        return []
    root = Path(generated_run_dir).resolve()
    if not root.exists():
        raise SystemExit(f"Generated agent run directory does not exist: {root}")
    if not (root / "run_manifest.json").exists():
        raise SystemExit(f"Generated agent run directory is missing run_manifest.json: {root}")

    files: list[Path] = []
    for name in AGENT_PACKAGE_FILES:
        path = root / name
        if path.is_file():
            files.append(path)

    artifacts_dir = root / "artifacts"
    if artifacts_dir.exists():
        files.extend(path for path in sorted(artifacts_dir.iterdir(), key=lambda item: item.name) if path.is_file())
    return files


def upload_agent_package(
    client: ObsClient,
    bucket: str,
    run_id: str,
    generated_run_dir: str,
) -> list[dict[str, Any]]:
    files = collect_agent_package_files(generated_run_dir)
    if not files:
        return []

    root = Path(generated_run_dir).resolve()
    uploaded: list[dict[str, Any]] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        key = f"release/{run_id}/agent_generated/{relative}"
        upload_file(client, bucket, key, path)
        uploaded.append(
            {
                "name": path.name,
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "object": f"obs://{bucket}/{key}",
            }
        )
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate tiny SAT-like data and upload sample artifacts to OBS.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--row-count", type=int, default=48)
    parser.add_argument("--agent-run-id", default="")
    parser.add_argument("--generated-run-dir", default="")
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION") or os.environ.get("HW_REGION_NAME") or "la-south-2")
    args = parser.parse_args()

    ak = os.environ.get("HUAWEICLOUD_ACCESS_KEY") or os.environ.get("HW_ACCESS_KEY") or require_env("HUAWEICLOUD_ACCESS_KEY")
    sk = os.environ.get("HUAWEICLOUD_SECRET_KEY") or os.environ.get("HW_SECRET_KEY") or require_env("HUAWEICLOUD_SECRET_KEY")
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or os.environ.get("HW_SECURITY_TOKEN")
    endpoint = f"https://obs.{args.region}.myhuaweicloud.com"

    work_dir = Path(".cloud_real_bigdata_work") / args.run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = work_dir / "taxpayer_registry.csv"
    manifest_json = work_dir / "release_manifest.json"
    spark_script = Path(__file__).resolve().parents[1] / "spark" / "sat_taxpayer_etl.py"

    rows = make_rows(args.row_count)
    with raw_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    client = ObsClient(
        access_key_id=ak,
        secret_access_key=sk,
        security_token=security_token,
        server=endpoint,
    )
    try:
        upload_file(client, args.bucket, f"raw/sat/{args.run_id}/taxpayer_registry.csv", raw_csv)
        upload_file(client, args.bucket, "scripts/sat_taxpayer_etl.py", spark_script)
        agent_files = upload_agent_package(client, args.bucket, args.run_id, args.generated_run_dir)

        manifest = {
            "run_id": args.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "execution_layer": "Huawei Cloud OBS + MRS Spark",
            "prompt_to_artifact": bool(args.generated_run_dir),
            "agent_run_id": args.agent_run_id,
            "agent_generated_dir": str(Path(args.generated_run_dir).resolve()) if args.generated_run_dir else "",
            "agent_release_prefix": f"obs://{args.bucket}/release/{args.run_id}/agent_generated/" if agent_files else "",
            "agent_artifacts_uploaded": agent_files,
            "cloud_execution_policy": (
                "Agent-generated PySpark, SQL, and DataArts DAG files are uploaded as review evidence. "
                "The minimal real E2E submits the reviewed cloud smoke script to MRS Spark."
            ),
            "raw_object": f"obs://{args.bucket}/raw/sat/{args.run_id}/taxpayer_registry.csv",
            "spark_script": f"obs://{args.bucket}/scripts/sat_taxpayer_etl.py",
            "gold_output": f"obs://{args.bucket}/gold/sat/{args.run_id}/taxpayer_gold_csv/",
            "iceberg_table": "spark_catalog.tax_gold.taxpayer_regime_year",
            "iceberg_warehouse": f"obs://{args.bucket}/lakehouse/iceberg/sat/",
            "audit_output": f"obs://{args.bucket}/audit/{args.run_id}/mrs_audit.json",
            "duckdb_used": False,
        }
        manifest_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        upload_file(client, args.bucket, f"release/{args.run_id}/release_manifest.json", manifest_json)
    finally:
        client.close()

    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
