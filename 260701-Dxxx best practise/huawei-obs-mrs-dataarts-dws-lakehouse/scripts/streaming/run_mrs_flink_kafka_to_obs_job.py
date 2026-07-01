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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit the DockOne Kafka->OBS Flink jar through the MRS Add Job API.")
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET", "hwstaff-retail-lakehouse-09d63c-20260622"))
    parser.add_argument("--cluster-id", default=os.environ.get("MRS_FLINK_CLUSTER_ID", "8bde86de-a0a4-4ff1-a3bf-4bb2e1a75485"))
    parser.add_argument("--project-id", default=os.environ.get("HUAWEICLOUD_PROJECT_ID"))
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION", "la-south-2"))
    parser.add_argument("--jar-key", default="jobs/flink/dockone-kafka-to-obs-flink-202606281840.jar")
    parser.add_argument("--bootstrap", default=os.environ.get("DMS_KAFKA_BOOTSTRAP_SERVERS", "192.168.11.202:9093"))
    parser.add_argument("--topic", default=os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts"))
    parser.add_argument("--group-id", default=None)
    parser.add_argument("--output-prefix", default="raw_flink/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.billing.contracts/run=202606281840-mrsjob")
    parser.add_argument("--max-messages", type=int, default=0)
    parser.add_argument("--detached", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=90)
    parser.add_argument("--summary", default=str(Path("runs") / "mrs-flink-kafka-to-obs-job-202606281840.json"))
    return parser.parse_args()


def main() -> None:
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
    run_id = time.strftime("%Y%m%d%H%M%S")
    group_id = args.group_id or f"mrs-flink-contracts-to-obs-api-{run_id}"
    jar = f"obs://{args.bucket}/{args.jar_key}"
    output = args.output_prefix if args.output_prefix.startswith("obs://") else f"obs://{args.bucket}/{args.output_prefix.strip('/')}"
    arguments = [
        "run",
    ]
    if args.detached:
        arguments.append("-d")
    arguments.extend(
        [
            "-ynm",
            "dockone-kafka-to-obs-api",
            "-m",
            "yarn-cluster",
            "-c",
            "com.dockone.flink.KafkaToObsRaw",
            jar,
            "--bootstrap",
            args.bootstrap,
            "--topic",
            args.topic,
            "--group",
            group_id,
            "--output",
            output,
            "--maxMessages",
            str(args.max_messages),
        ]
    )
    body = JobExecution(
        job_type="Flink",
        job_name="dockone-kafka-to-obs-raw-json",
        arguments=arguments,
        properties={
            "fs.obs.endpoint": f"obs.{args.region}.myhuaweicloud.com",
        },
    )
    response = client.create_execute_job(CreateExecuteJobRequest(cluster_id=args.cluster_id, body=body)).to_json_object()
    submit = response.get("job_submit_result") or {}
    job_id = submit.get("job_id") or response.get("job_id")
    if not job_id:
        raise SystemExit(f"No job id in submit response: {response}")
    print(json.dumps({"submitted_job_id": job_id, "cluster_id": args.cluster_id, "output": output}))

    success = {"SUCCEEDED", "FINISHED", "SUCCESS"}
    failure = {"FAILED", "KILLED", "ERROR", "CANCELLED", "CANCELED"}
    detail = {}
    result = {
        "result": "submitted",
        "job_id": job_id,
        "cluster_id": args.cluster_id,
        "topic": args.topic,
        "group_id": group_id,
        "output": output,
        "arguments": arguments,
    }
    for poll in range(1, args.max_polls + 1):
        data = client.show_single_job_exe(
            ShowSingleJobExeRequest(cluster_id=args.cluster_id, job_execution_id=job_id)
        ).to_json_object()
        detail = data.get("job_detail") or data.get("job_execution") or data
        state = str(detail.get("job_result") or detail.get("job_state") or detail.get("state") or "UNKNOWN").upper()
        print(json.dumps({"poll": poll, "job_id": job_id, "state": state}, ensure_ascii=False))
        if state in success:
            result.update({"result": "success", "detail": detail})
            break
        if state in failure:
            result.update({"result": "failure", "detail": detail})
            Path(args.summary).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, default=str))
            raise SystemExit(2)
        time.sleep(args.poll_seconds)
    else:
        result.update({"result": "timeout", "detail": detail})
        Path(args.summary).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, default=str))
        raise SystemExit(3)

    Path(args.summary).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
