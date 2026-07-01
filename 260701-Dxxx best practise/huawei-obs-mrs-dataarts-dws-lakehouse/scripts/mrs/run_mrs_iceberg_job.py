#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkmrs.v2 import CreateExecuteJobRequest, JobExecution, MrsClient, ShowSingleJobExeRequest
from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion


def parse_args():
    parser = argparse.ArgumentParser(description="Submit the DockOne Iceberg Spark job to MRS.")
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET"))
    parser.add_argument("--cluster-id", default=os.environ.get("DEPLOYMENT_MRS_CLUSTER_ID"))
    parser.add_argument("--project-id", default=os.environ.get("HUAWEICLOUD_PROJECT_ID"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument("--jar-name", default=os.environ.get("ICEBERG_RUNTIME_JAR_NAME", "iceberg-spark-runtime-3.3_2.12-1.5.2.jar"))
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--summary", default=str(Path.cwd() / "mrs-iceberg-job-summary.json"))
    return parser.parse_args()


def main():
    args = parse_args()
    missing = [name for name, value in {"bucket": args.bucket, "cluster-id": args.cluster_id, "project-id": args.project_id}.items() if not value]
    if missing:
        raise SystemExit(f"Missing required values: {', '.join(missing)}")
    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        args.project_id,
    )
    client = MrsClient.new_builder().with_credentials(credentials).with_region(MrsRegion.value_of(args.region)).build()

    script = f"obs://{args.bucket}/jobs/mrs/dockone_iceberg_lakehouse.py"
    jar = f"obs://{args.bucket}/jobs/jars/{args.jar_name}"
    warehouse = f"obs://{args.bucket}/lake/iceberg/dockone"
    arguments = [
        "--master", "yarn",
        "--deploy-mode", "cluster",
        "--jars", jar,
        "--conf", "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "--conf", "spark.sql.catalog.obs_iceberg=org.apache.iceberg.spark.SparkCatalog",
        "--conf", "spark.sql.catalog.obs_iceberg.type=hadoop",
        "--conf", f"spark.sql.catalog.obs_iceberg.warehouse={warehouse}",
        "--conf", "spark.sql.shuffle.partitions=2",
        "--conf", "spark.sql.adaptive.enabled=false",
        script,
        "--bucket", args.bucket,
        "--manifest-path", f"obs://{args.bucket}/config/dockone/manifest.json",
        "--raw-root", f"obs://{args.bucket}/raw/dockone_exampleapp",
        "--warehouse-path", warehouse,
        "--publish-path", f"obs://{args.bucket}/publish/dockone_table_metrics/current",
    ]
    body = JobExecution(
        job_type="SparkPython",
        job_name="dockone-iceberg-bronze-silver-golden",
        arguments=arguments,
        properties={"fs.obs.endpoint": f"obs.{args.region}.myhuaweicloud.com"},
    )
    response = client.create_execute_job(CreateExecuteJobRequest(cluster_id=args.cluster_id, body=body)).to_json_object()
    submit = response.get("job_submit_result") or {}
    job_id = submit.get("job_id") or response.get("job_id")
    if not job_id:
        raise SystemExit(f"No job id in submit response: {response}")
    print(json.dumps({"submitted_job_id": job_id, "cluster_id": args.cluster_id}))

    success = {"SUCCEEDED", "FINISHED", "SUCCESS"}
    failure = {"FAILED", "KILLED", "ERROR", "CANCELLED", "CANCELED"}
    last = {}
    for poll in range(1, args.max_polls + 1):
        data = client.show_single_job_exe(
            ShowSingleJobExeRequest(cluster_id=args.cluster_id, job_execution_id=job_id)
        ).to_json_object()
        detail = data.get("job_detail") or data.get("job_execution") or data
        state = str(detail.get("job_result") or detail.get("job_state") or detail.get("state") or "UNKNOWN").upper()
        print(json.dumps({"poll": poll, "job_id": job_id, "state": state}))
        last = data
        if state in success:
            result = {"result": "success", "job_id": job_id, "detail": detail}
            Path(args.summary).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            print(json.dumps(result, default=str))
            return
        if state in failure:
            result = {"result": "failure", "job_id": job_id, "detail": detail}
            Path(args.summary).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            print(json.dumps(result, default=str))
            raise SystemExit(2)
        time.sleep(args.poll_seconds)

    print(json.dumps({"result": "timeout", "job_id": job_id, "last": last}, default=str))
    raise SystemExit(3)


if __name__ == "__main__":
    main()
