from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def expand_env(value: str) -> str:
    for key, val in os.environ.items():
        value = value.replace("${" + key + "}", val)
    return value


def payload_for(table, stage: str) -> dict:
    bucket = os.environ.get("DEMO_BUCKET", "${DEMO_BUCKET}")
    queue = os.environ.get("DLI_QUEUE_NAME", "${DLI_QUEUE_NAME}")
    agency = os.environ.get("DLI_AGENCY_URN", "")
    agency_name = os.environ.get("DLI_AGENCY_NAME", "dli_management_agency")
    spark_version = os.environ.get("DLI_SPARK_VERSION", "3.3.1")
    if stage == "bronze":
        file_name = f"obs://{bucket}/jobs/dli/bronze_hudi_job.py"
        args = [
            "--table-name", table["table_name"],
            "--raw-path", table["raw_obs_path"].replace("${DEMO_BUCKET}", bucket),
            "--bronze-path", table["bronze_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--checkpoint-path", f"obs://{bucket}/checkpoints/bronze/{table['domain']}/{table['entity']}",
            "--hudi-table-name", f"bronze_{table['hudi_table_name']}",
        ]
    elif stage == "silver":
        file_name = f"obs://{bucket}/jobs/dli/silver_hudi_job.py"
        args = [
            "--table-name", table["table_name"],
            "--bronze-path", table["bronze_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--silver-path", table["silver_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--hudi-table-name", f"silver_{table['hudi_table_name']}",
        ]
    else:
        raise ValueError(stage)
    return {
        "file": file_name,
        "className": "",
        "queue": queue,
        "name": f"{stage}-{table['table_name']}",
        "args": args,
        "sc_type": "A",
        "spark_version": spark_version,
        "feature": "basic",
        "auto_recovery": True,
        "max_retry_times": 3,
        "execution_agency_urn": agency,
        "conf": {
            "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
            "spark.sql.catalogImplementation": "hive",
            "spark.sql.shuffle.partitions": "2",
            "spark.sql.files.maxRecordsPerFile": "50000",
            "spark.dli.job.agency.name": agency_name,
        },
    }


def main():
    config = json.loads((ROOT / "config" / "job-config.json").read_text(encoding="utf-8"))
    out = ROOT / "runtime" / "dli-payloads"
    out.mkdir(parents=True, exist_ok=True)
    workflow = []
    for table in config["tables"]:
        bronze = payload_for(table, "bronze")
        silver = payload_for(table, "silver")
        (out / f"bronze-{table['table_name']}.json").write_text(json.dumps(bronze, indent=2), encoding="utf-8")
        (out / f"silver-{table['table_name']}.json").write_text(json.dumps(silver, indent=2), encoding="utf-8")
        workflow.append(
            {
                "table_name": table["table_name"],
                "bronze_payload": f"runtime/dli-payloads/bronze-{table['table_name']}.json",
                "silver_payload": f"runtime/dli-payloads/silver-{table['table_name']}.json",
                "dependency": "silver starts after bronze success",
            }
        )
    (ROOT / "runtime" / "workflow-plan.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    print(f"generated {len(workflow) * 2} DLI payloads under {out}")


if __name__ == "__main__":
    main()
