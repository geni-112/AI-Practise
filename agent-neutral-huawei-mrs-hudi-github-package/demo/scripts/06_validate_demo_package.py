from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "config/job-config.json",
    "config/minimal-huawei-resources.yaml",
    "jobs/dli/bronze_hudi_job.py",
    "jobs/dli/silver_hudi_job.py",
    "jobs/dataarts/workflow.yaml",
    "notebooks/dli_hudi_demo.ipynb",
    "preview/index.html",
    "docs/runbook-timeline.md",
]


def main():
    errors = []
    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            errors.append(f"missing {rel}")
    config = json.loads((ROOT / "config" / "job-config.json").read_text(encoding="utf-8"))
    if len(config["tables"]) != 21:
        errors.append(f"expected 21 tables, found {len(config['tables'])}")
    for table in config["tables"]:
        for key in ["raw_obs_path", "bronze_hudi_path", "silver_hudi_path", "record_key", "precombine_field"]:
            if key not in table:
                errors.append(f"{table.get('table_name')} missing {key}")
        if table.get("record_key") != "id":
            errors.append(f"{table['table_name']} record_key must be id")
        if table.get("precombine_field") != "_cdc_timestamp":
            errors.append(f"{table['table_name']} precombine must be _cdc_timestamp")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(json.dumps({"status": "ok", "tables": len(config["tables"]), "package": str(ROOT)}, indent=2))


if __name__ == "__main__":
    main()
