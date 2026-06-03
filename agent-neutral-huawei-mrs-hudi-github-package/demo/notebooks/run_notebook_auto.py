from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "dli_hudi_demo.ipynb"


def env_bool(value: bool) -> str:
    return "1" if value else "0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the DLI/Hudi demo notebook workflow automatically.")
    parser.add_argument("--bucket", default="docktest")
    parser.add_argument("--queue", default="default")
    parser.add_argument("--agency-name", default="dli_management_agency")
    parser.add_argument("--engine", choices=["dli", "mrs"], default="dli")
    parser.add_argument("--mrs-cluster-id", default="")
    parser.add_argument("--transient-mrs-cluster", action="store_true")
    parser.add_argument("--smoke-tables", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Run the notebook workflow without creating/submitting cloud work.")
    parser.add_argument("--force-fallback-auth", action="store_true", default=False)
    args = parser.parse_args()

    os.environ["DEMO_BUCKET"] = args.bucket
    os.environ["DLI_QUEUE_NAME"] = args.queue
    os.environ["DLI_AGENCY_NAME"] = args.agency_name
    if args.mrs_cluster_id:
        os.environ["MRS_CLUSTER_ID"] = args.mrs_cluster_id
    os.environ["DEMO_ENGINE"] = args.engine
    os.environ["TRANSIENT_MRS_CLUSTER"] = env_bool(args.transient_mrs_cluster)
    os.environ["SMOKE_TABLES"] = str(args.smoke_tables)
    os.environ["NOTEBOOK_EXECUTE"] = env_bool(not args.dry_run)
    os.environ["FORCE_FALLBACK_AUTH"] = env_bool(args.force_fallback_auth)

    notebook = json.loads(NB.read_text(encoding="utf-8"))
    namespace = {"__name__": "__notebook_auto__", "__file__": str(NB)}
    executed = []
    failures = []

    for index, cell in enumerate(notebook["cells"], start=1):
        if cell.get("cell_type") != "code":
            continue
        metadata = cell.get("metadata", {})
        if metadata.get("run_on_validate") is False and not metadata.get("run_on_auto"):
            continue
        code = "".join(cell.get("source", []))
        try:
            print(f"\n--- notebook cell {index} ({metadata.get('demo_cell', 'code')}) ---")
            exec(compile(code, f"{NB.name}:cell-{index}", "exec"), namespace)
            executed.append(index)
        except Exception:
            failures.append({"cell": index, "traceback": traceback.format_exc()})
            break

    result = {
        "notebook": str(NB),
        "bucket": args.bucket,
        "queue": args.queue,
        "agency_name": args.agency_name,
        "engine": args.engine,
        "mrs_cluster_id": args.mrs_cluster_id,
        "transient_mrs_cluster": args.transient_mrs_cluster,
        "smoke_tables": args.smoke_tables,
        "execute": not args.dry_run,
        "cells_executed": executed,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
