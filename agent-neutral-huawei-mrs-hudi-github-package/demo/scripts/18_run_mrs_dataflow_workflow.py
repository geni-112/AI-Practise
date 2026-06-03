from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_RESULTS = {"SUCCEEDED", "SUCCESS", "FINISHED"}
FAILURE_RESULTS = {"FAILED", "KILLED", "ERROR", "CANCELLED", "CANCELED"}


def response_to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return {}


def mrs_client_v2():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkmrs.v2 import MrsClient
    from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion

    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        os.environ["HUAWEICLOUD_PROJECT_ID"],
    )
    if os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"):
        credentials.with_security_token(os.environ["HUAWEICLOUD_SECURITY_TOKEN"])
    return (
        MrsClient.new_builder()
        .with_credentials(credentials)
        .with_region(MrsRegion.value_of(os.environ.get("HUAWEICLOUD_REGION", "la-south-2")))
        .build()
    )


def mrs_client_v1():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkmrs.v1 import MrsClient
    from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion

    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        os.environ["HUAWEICLOUD_PROJECT_ID"],
    )
    if os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"):
        credentials.with_security_token(os.environ["HUAWEICLOUD_SECURITY_TOKEN"])
    return (
        MrsClient.new_builder()
        .with_credentials(credentials)
        .with_region(MrsRegion.value_of(os.environ.get("HUAWEICLOUD_REGION", "la-south-2")))
        .build()
    )


def cluster_summary(client: Any, cluster_id: str) -> dict:
    from huaweicloudsdkmrs.v1 import ShowClusterDetailsRequest

    data = response_to_json(client.show_cluster_details(ShowClusterDetailsRequest(cluster_id=cluster_id)))
    detail = data.get("cluster") or data
    keys = [
        "clusterId",
        "clusterName",
        "clusterState",
        "stageDesc",
        "stagePercent",
        "mrsManagerFinish",
        "chargingStartTime",
        "duration",
        "fee",
        "errorInfo",
        "errorMessage",
    ]
    return {key: detail.get(key) for key in keys}


def list_cluster_jobs(client: Any, cluster_id: str) -> dict:
    from huaweicloudsdkmrs.v2 import ShowJobExeListNewRequest

    return response_to_json(
        client.show_job_exe_list_new(ShowJobExeListNewRequest(cluster_id=cluster_id, limit="100", offset="1"))
    )


def job_items(jobs_response: dict) -> list[dict]:
    return jobs_response.get("job_list") or jobs_response.get("job_executions") or jobs_response.get("jobs") or []


def job_field(job: dict, snake: str, camel: str) -> str:
    return str(job.get(snake) or job.get(camel) or "")


def find_job_by_name(jobs_response: dict, name: str) -> dict | None:
    for job in job_items(jobs_response):
        if job_field(job, "job_name", "jobName") == name:
            return job
    return None


def job_id_from_detail(job: dict) -> str:
    return job_field(job, "job_id", "jobId")


def job_status_from_detail(job: dict) -> str:
    result = job_field(job, "job_result", "jobResult")
    state = job_field(job, "job_state", "jobState")
    return result or state or "UNKNOWN"


def wait_for_transient_cluster(client_v1: Any, client_v2: Any, cluster_id: str, expected_jobs: int, interval: int, max_polls: int) -> dict:
    last = {"cluster_id": cluster_id}
    for poll in range(1, max_polls + 1):
        item = {"poll": poll}
        try:
            item["cluster"] = cluster_summary(client_v1, cluster_id)
        except Exception as exc:
            item["cluster_error"] = {
                "class": exc.__class__.__name__,
                "status_code": getattr(exc, "status_code", None),
                "error_code": getattr(exc, "error_code", None),
                "error_msg": getattr(exc, "error_msg", None),
            }
        try:
            item["jobs"] = list_cluster_jobs(client_v2, cluster_id)
        except Exception as exc:
            item["jobs_error"] = {
                "class": exc.__class__.__name__,
                "status_code": getattr(exc, "status_code", None),
                "error_code": getattr(exc, "error_code", None),
                "error_msg": getattr(exc, "error_msg", None),
            }
        print(json.dumps(item, default=str))
        last = item

        jobs = (item.get("jobs") or {}).get("job_list") or []
        if len(jobs) >= expected_jobs:
            results = {str(job.get("job_result", "")).upper() for job in jobs}
            if results and results.issubset(SUCCESS_RESULTS):
                return item
            if results & FAILURE_RESULTS:
                raise RuntimeError(f"Transient MRS jobs failed: cluster_id={cluster_id} detail={item}")

        state = str((item.get("cluster") or {}).get("clusterState") or "").lower()
        if state in {"terminated", "failed", "error"} and jobs:
            return item
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for transient MRS cluster: cluster_id={cluster_id} last={last}")


def wait_for_cluster_running(client_v1: Any, cluster_id: str, interval: int, max_polls: int) -> dict:
    last = {"cluster_id": cluster_id}
    for poll in range(1, max_polls + 1):
        item = {"poll": poll, "cluster": cluster_summary(client_v1, cluster_id)}
        print(json.dumps(item, default=str))
        last = item
        state = str((item.get("cluster") or {}).get("clusterState") or "").lower()
        if state == "running":
            return item
        if state in {"terminated", "failed", "error"}:
            raise RuntimeError(f"Transient MRS cluster did not reach running: cluster_id={cluster_id} detail={item}")
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for transient MRS cluster to run: cluster_id={cluster_id} last={last}")


def delete_cluster_best_effort(client_v1: Any, cluster_id: str) -> dict:
    from huaweicloudsdkmrs.v1 import DeleteClusterRequest

    try:
        response = response_to_json(client_v1.delete_cluster(DeleteClusterRequest(cluster_id=cluster_id)))
        return {"cluster_id": cluster_id, "delete": "submitted", "response": response}
    except Exception as exc:
        return {
            "cluster_id": cluster_id,
            "delete": "failed",
            "error": {
                "class": exc.__class__.__name__,
                "status_code": getattr(exc, "status_code", None),
                "error_code": getattr(exc, "error_code", None),
                "error_msg": getattr(exc, "error_msg", None),
            },
        }


def load_config() -> tuple[dict, dict]:
    mrs_path = Path(os.environ.get("MRS_CONFIG_PATH", ROOT / "config" / "mrs-config.json"))
    job_path = Path(os.environ.get("JOB_CONFIG_PATH", ROOT / "config" / "job-config.json"))
    mrs = json.loads(mrs_path.read_text(encoding="utf-8"))
    jobs = json.loads(job_path.read_text(encoding="utf-8"))
    return mrs, jobs


def expand(value: str) -> str:
    for key, val in os.environ.items():
        value = value.replace("${" + key + "}", val)
    return value


def spark_args(script_path: str, args: list[str], mrs_config: dict) -> list[str]:
    spark = mrs_config["spark"]
    result = [
        "--master",
        spark.get("master", "yarn"),
        "--deploy-mode",
        spark.get("deploy_mode", "cluster"),
    ]
    hudi_bundle = expand(spark.get("hudi_bundle", ""))
    if hudi_bundle:
        result.extend(["--jars", hudi_bundle])
    for key, value in spark.get("conf", {}).items():
        result.extend(["--conf", f"{key}={value}"])
    result.append(script_path)
    result.extend(args)
    return result


def table_payload_args(table: dict, stage: str, bucket: str) -> tuple[str, list[str]]:
    if stage == "bronze":
        script = f"obs://{bucket}/jobs/dli/bronze_hudi_job.py"
        args = [
            "--table-name",
            table["table_name"],
            "--raw-path",
            table["raw_obs_path"].replace("${DEMO_BUCKET}", bucket),
            "--bronze-path",
            table["bronze_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--checkpoint-path",
            f"obs://{bucket}/checkpoints/bronze/{table['domain']}/{table['entity']}",
            "--hudi-table-name",
            f"bronze_{table['hudi_table_name']}",
        ]
    elif stage == "silver":
        script = f"obs://{bucket}/jobs/dli/silver_hudi_job.py"
        args = [
            "--table-name",
            table["table_name"],
            "--bronze-path",
            table["bronze_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--silver-path",
            table["silver_hudi_path"].replace("${DEMO_BUCKET}", bucket),
            "--hudi-table-name",
            f"silver_{table['hudi_table_name']}",
        ]
    else:
        raise ValueError(stage)
    return script, args


def job_properties(mrs_config: dict) -> dict[str, str]:
    return {key: expand(str(value)) for key, value in mrs_config.get("spark", {}).get("job_properties", {}).items()}


def submit_existing_cluster_job(
    client: Any,
    cluster_id: str,
    name: str,
    arguments: list[str],
    mrs_config: dict,
    retry_attempts: int = 6,
    retry_seconds: int = 60,
) -> str:
    from huaweicloudsdkmrs.v2 import CreateExecuteJobRequest, JobExecution

    body = JobExecution(job_type="SparkPython", job_name=name, arguments=arguments, properties=job_properties(mrs_config))
    last_error = None
    for attempt in range(1, retry_attempts + 1):
        try:
            response = response_to_json(client.create_execute_job(CreateExecuteJobRequest(cluster_id=cluster_id, body=body)))
            break
        except Exception as exc:
            last_error = exc
            try:
                existing = find_job_by_name(list_cluster_jobs(client, cluster_id), name)
                if existing:
                    existing_id = job_id_from_detail(existing)
                    if existing_id:
                        print(json.dumps({"adopted_existing_job": name, "job_id": existing_id, "attempt": attempt}))
                        return existing_id
            except Exception:
                pass
            if attempt >= retry_attempts:
                raise
            print(json.dumps({"submit_retry": name, "attempt": attempt, "error": str(exc)[:500]}))
            time.sleep(retry_seconds)
    result = response.get("job_submit_result") or {}
    job_id = result.get("job_id") or response.get("job_id")
    if not job_id:
        raise RuntimeError(f"MRS job submit response did not include job_id: {response}; last_error={last_error}")
    print(json.dumps({"submitted": name, "job_id": job_id, "response": response}, indent=2))
    return str(job_id)


def job_state(client: Any, cluster_id: str, job_id: str) -> tuple[str, dict]:
    from huaweicloudsdkmrs.v2 import ShowSingleJobExeRequest

    data = response_to_json(client.show_single_job_exe(ShowSingleJobExeRequest(cluster_id=cluster_id, job_execution_id=job_id)))
    detail = data.get("job_detail") or data.get("job_execution") or data
    result = str(detail.get("job_result") or detail.get("job_state") or detail.get("state") or "UNKNOWN")
    return result, data


def wait_for_job(client: Any, cluster_id: str, job_id: str, name: str, interval: int, max_polls: int) -> dict:
    last = {}
    for poll in range(1, max_polls + 1):
        try:
            state, detail = job_state(client, cluster_id, job_id)
        except Exception as exc:
            try:
                jobs = list_cluster_jobs(client, cluster_id)
                matched = [
                    item
                    for item in job_items(jobs)
                    if job_id_from_detail(item) == str(job_id)
                    or job_field(item, "job_name", "jobName") == str(name)
                ]
                for item in matched:
                    result = job_field(item, "job_result", "jobResult")
                    state_value = job_field(item, "job_state", "jobState")
                    if result.upper() in SUCCESS_RESULTS or state_value.upper() in SUCCESS_RESULTS:
                        return {"job_detail": item, "recovered_from": exc.__class__.__name__}
                    if result.upper() in FAILURE_RESULTS or state_value.upper() in FAILURE_RESULTS:
                        raise RuntimeError(f"MRS job failed after list fallback: {name} job_id={job_id} detail={item}") from exc
            except RuntimeError:
                raise
            except Exception:
                pass
            raise
        last = detail
        print(json.dumps({"name": name, "job_id": job_id, "poll": poll, "state": state}))
        upper = state.upper()
        if upper in SUCCESS_RESULTS:
            return detail
        if upper in FAILURE_RESULTS:
            raise RuntimeError(f"MRS job failed: {name} job_id={job_id} state={state} detail={detail}")
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for MRS job: {name} job_id={job_id} last={last}")


def random_password() -> str:
    chars = string.ascii_letters + string.digits + "!@$%^-_=+"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(18))
        if all(any(c in group for c in pwd) for group in [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@$%^-_=+"]):
            return pwd


def transient_cluster_body(mrs_config: dict, steps: list[Any], keep_cluster: bool = False, manual_submit: bool = False):
    from huaweicloudsdkmrs.v2 import ChargeInfo, NodeGroupV2, RunJobFlowCommand, Tag, Volume

    cluster = mrs_config["cluster"]
    password = os.environ.get("MRS_ADMIN_PASSWORD") or random_password()
    root_volume = Volume(type=cluster["root_volume_type"], size=cluster["root_volume_size"])
    data_volume = Volume(type=cluster["data_volume_type"], size=cluster["data_volume_size"])
    node_groups = [
        NodeGroupV2(
            group_name="master_node_default_group",
            node_num=cluster["master_node_num"],
            node_size=cluster["master_node_size"],
            root_volume=root_volume,
            data_volume=data_volume,
            data_volume_count=cluster["data_volume_count"],
        ),
        NodeGroupV2(
            group_name="core_node_analysis_group",
            node_num=cluster["core_node_num"],
            node_size=cluster["core_node_size"],
            root_volume=root_volume,
            data_volume=data_volume,
            data_volume_count=cluster["data_volume_count"],
        ),
    ]
    suffix = time.strftime("%Y%m%d%H%M%S")
    return RunJobFlowCommand(
        cluster_version=cluster["cluster_version"],
        cluster_name=f"{cluster['transient_cluster_name_prefix']}-{suffix}",
        cluster_type=cluster["cluster_type"],
        charge_info=ChargeInfo(charge_mode="postPaid"),
        region=mrs_config["region"],
        vpc_name=cluster["vpc_name"],
        subnet_id=cluster["subnet_id"],
        subnet_name=cluster["subnet_name"],
        components=cluster["components"],
        availability_zone=cluster["availability_zone"],
        security_groups_id=cluster["security_groups_id"],
        safe_mode="SIMPLE",
        manager_admin_password=password,
        login_mode="PASSWORD",
        node_root_password=password,
        enterprise_project_id="0",
        mrs_ecs_default_agency=cluster.get("mrs_ecs_default_agency", "MRS_ECS_DEFAULT_AGENCY"),
        tags=[Tag(key="demo", value="dockone-hudi-mrs")],
        node_groups=node_groups,
        delete_when_no_steps=False if manual_submit or keep_cluster else cluster.get("delete_when_no_steps", True),
        steps=steps[:1] if manual_submit else steps,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run raw->bronze->silver workflow on MRS.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--cluster-id", default=os.environ.get("MRS_CLUSTER_ID", ""))
    parser.add_argument("--transient-cluster", action="store_true")
    parser.add_argument("--keep-cluster", action="store_true", help="For debugging: keep transient cluster after steps finish.")
    parser.add_argument("--wait-transient", action="store_true", help="Poll transient cluster/job status until completion.")
    parser.add_argument(
        "--transient-submit-mode",
        choices=["manual", "steps"],
        default="manual",
        help="manual creates a transient cluster, submits jobs sequentially, then deletes it; steps uses MRS run-job-flow steps.",
    )
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--max-polls", type=int, default=80)
    args = parser.parse_args()

    mrs_config, job_config = load_config()
    bucket = os.environ.get("DEMO_BUCKET", mrs_config["bucket"])
    os.environ["DEMO_BUCKET"] = bucket
    tables = job_config["tables"][: args.limit] if args.limit else job_config["tables"]
    steps_summary = []

    if not args.cluster_id and not args.transient_cluster:
        raise SystemExit("Provide --cluster-id/MRS_CLUSTER_ID or use --transient-cluster.")

    client = mrs_client_v2()
    steps = []
    for table in tables:
        for stage in ["bronze", "silver"]:
            script, script_args = table_payload_args(table, stage, bucket)
            arguments = spark_args(script, script_args, mrs_config)
            name = f"{stage}-{table['table_name']}"[:64]
            steps_summary.append({"stage": stage, "table_name": table["table_name"], "job_name": name, "arguments": arguments})
            if args.transient_cluster:
                from huaweicloudsdkmrs.v2 import JobExecution, StepConfig

                steps.append(
                    StepConfig(
                        job_execution=JobExecution(
                            job_type="SparkPython",
                            job_name=name,
                            arguments=arguments,
                            properties=job_properties(mrs_config),
                        )
                    )
                )

    if not args.execute:
        print(json.dumps({"mode": "dry-run", "engine": "mrs", "bucket": bucket, "steps": steps_summary}, indent=2))
        return

    run_summary = []
    if args.transient_cluster:
        from huaweicloudsdkmrs.v2 import RunJobFlowRequest

        create_steps = steps[:1] if args.transient_submit_mode == "manual" else steps
        body = transient_cluster_body(
            mrs_config,
            create_steps,
            keep_cluster=args.keep_cluster,
            manual_submit=(args.transient_submit_mode == "manual"),
        )
        response = response_to_json(client.run_job_flow(RunJobFlowRequest(body=body)))
        runtime = ROOT / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "mrs-transient-run-response.json").write_text(json.dumps(response, indent=2), encoding="utf-8")
        print(json.dumps({"transient_cluster": response, "note": "Cluster creation and step execution started."}, indent=2))
        cluster_id = response.get("cluster_id")
        if not cluster_id:
            raise RuntimeError(f"Transient MRS response did not include cluster_id: {response}")
        if args.transient_submit_mode == "manual":
            client_v1 = mrs_client_v1()
            try:
                wait_for_cluster_running(client_v1, cluster_id, args.interval_seconds, args.max_polls)
                try:
                    step_jobs_response = list_cluster_jobs(client, cluster_id)
                except Exception:
                    step_jobs_response = {}
                first_name = steps_summary[0]["job_name"] if steps_summary else ""
                first_job = find_job_by_name(step_jobs_response, first_name) if first_name else None
                first_succeeded = False
                if first_job:
                    first_status = job_status_from_detail(first_job).upper()
                    first_job_id = job_id_from_detail(first_job)
                    if first_status in SUCCESS_RESULTS:
                        first_succeeded = True
                        run_summary.append({**steps_summary[0], "job_id": first_job_id, "detail": {"job_detail": first_job}})
                    elif first_status in FAILURE_RESULTS:
                        first_succeeded = False
                    elif first_job_id:
                        detail = wait_for_job(client, cluster_id, first_job_id, first_name, args.interval_seconds, args.max_polls)
                        run_summary.append({**steps_summary[0], "job_id": first_job_id, "detail": detail})
                        first_succeeded = True
                remaining_steps = steps_summary[1:] if first_succeeded else steps_summary
                print(
                    json.dumps(
                        {
                            "manual_submit": "submitting explicit bronze/silver steps",
                            "first_step": first_name,
                            "first_step_succeeded": first_succeeded,
                            "first_step_seen": bool(first_job),
                            "remaining_jobs": [item["job_name"] for item in remaining_steps],
                        }
                    )
                )
                for item in remaining_steps:
                    job_id = submit_existing_cluster_job(client, cluster_id, item["job_name"], item["arguments"], mrs_config)
                    detail = wait_for_job(client, cluster_id, job_id, item["job_name"], args.interval_seconds, args.max_polls)
                    run_summary.append({**item, "job_id": job_id, "detail": detail})
                cleanup = None if args.keep_cluster else delete_cluster_best_effort(client_v1, cluster_id)
                summary = {"cluster_id": cluster_id, "mode": "manual", "jobs": run_summary, "cleanup": cleanup}
                (runtime / "mrs-transient-run-summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
                print(json.dumps(summary, indent=2, default=str))
            except Exception:
                if not args.keep_cluster:
                    cleanup = delete_cluster_best_effort(client_v1, cluster_id)
                    print(json.dumps({"cleanup_after_error": cleanup}, indent=2, default=str))
                raise
            return
        if args.wait_transient:
            summary = wait_for_transient_cluster(mrs_client_v1(), client, cluster_id, len(steps_summary), args.interval_seconds, args.max_polls)
            (runtime / "mrs-transient-run-summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return

    for item in steps_summary:
        job_id = submit_existing_cluster_job(client, args.cluster_id, item["job_name"], item["arguments"], mrs_config)
        detail = wait_for_job(client, args.cluster_id, job_id, item["job_name"], args.interval_seconds, args.max_polls)
        run_summary.append({**item, "job_id": job_id, "detail": detail})

    runtime = ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "mrs-dataflow-run-summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print(json.dumps({"tables": len(tables), "summary_path": str(runtime / "mrs-dataflow-run-summary.json")}, indent=2))


if __name__ == "__main__":
    main()
