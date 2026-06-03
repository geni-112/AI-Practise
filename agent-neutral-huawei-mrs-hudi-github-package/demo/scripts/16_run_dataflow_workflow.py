from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_STATES = {"success", "available", "finished", "succeeded", "completed"}
FAILURE_STATES = {"dead", "error", "failed", "killed", "cancelled", "canceled"}


def response_to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return {}


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Auth-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: HTTP {exc.code} {detail}") from exc


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Auth-Token": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code} {detail}") from exc


def dli_client():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkdli.v1 import DliClient
    from huaweicloudsdkdli.v1.region.dli_region import DliRegion

    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        os.environ["HUAWEICLOUD_PROJECT_ID"],
    )
    if os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"):
        credentials.with_security_token(os.environ["HUAWEICLOUD_SECURITY_TOKEN"])
    return (
        DliClient.new_builder()
        .with_credentials(credentials)
        .with_region(DliRegion.value_of(os.environ.get("HUAWEICLOUD_REGION", "la-south-2")))
        .build()
    )


def submit_spark_sdk(client: Any, payload: dict) -> dict:
    from huaweicloudsdkdli.v1 import CreateSparkJobRequest, CreateSparkJobRequestBody

    body = CreateSparkJobRequestBody(
        file=payload.get("file"),
        class_name=payload.get("className") or "",
        args=payload.get("args"),
        sc_type=payload.get("sc_type"),
        conf=payload.get("conf"),
        name=payload.get("name"),
        feature=payload.get("feature"),
        spark_version=payload.get("spark_version"),
        queue=payload.get("queue"),
        auto_recovery=payload.get("auto_recovery"),
        max_retry_times=payload.get("max_retry_times"),
        execution_agency_urn=payload.get("execution_agency_urn") or None,
    )
    return response_to_json(client.create_spark_job(CreateSparkJobRequest(body=body)))


def submit_sql_sdk(client: Any, sql: str, queue: str) -> dict:
    from huaweicloudsdkdli.v1 import CreateSqlJobRequest, CreateSqlJobRequestBody

    body = CreateSqlJobRequestBody(sql=sql, engine_type="spark", queue_name=queue)
    return response_to_json(client.create_sql_job(CreateSqlJobRequest(body=body)))


def spark_state_sdk(client: Any, batch_id: str) -> str:
    from huaweicloudsdkdli.v1 import ShowSparkJobStatusRequest

    data = response_to_json(client.show_spark_job_status(ShowSparkJobStatusRequest(batch_id=batch_id)))
    return str(data.get("state") or data.get("status") or data.get("job_state") or "unknown")


def sql_state_sdk(client: Any, job_id: str) -> str:
    from huaweicloudsdkdli.v1 import ShowSqlJobStatusRequest

    data = response_to_json(client.show_sql_job_status(ShowSqlJobStatusRequest(job_id=job_id)))
    return str(data.get("status") or data.get("state") or data.get("job_status") or "unknown")


def sql_preview_sdk(client: Any, job_id: str, queue: str) -> dict:
    from huaweicloudsdkdli.v1 import PreviewSqlJobResultRequest

    return response_to_json(client.preview_sql_job_result(PreviewSqlJobResultRequest(job_id=job_id, queue_name=queue)))


def extract_id(response: dict) -> str:
    for key in ("id", "job_id", "batch_id", "appId", "jobId"):
        value = response.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value)
    raise RuntimeError(f"Could not find job id in response: {response}")


def normalize_state(state: str) -> str:
    return state.strip().lower()


def wait_for_state(get_state, job_id: str, name: str, interval: int, max_polls: int) -> str:
    for poll in range(1, max_polls + 1):
        state = get_state(job_id)
        norm = normalize_state(state)
        print(json.dumps({"name": name, "job_id": job_id, "poll": poll, "state": state}))
        if norm in SUCCESS_STATES:
            return state
        if norm in FAILURE_STATES:
            raise RuntimeError(f"{name} failed with state={state}")
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for {name} job_id={job_id}")


def render_sql(template_name: str, table: dict) -> str:
    template = (ROOT / "sql" / "dli" / template_name).read_text(encoding="utf-8")
    values = {
        "table_name": table["table_name"],
        "silver_hudi_table_name": f"silver_{table['hudi_table_name']}",
        "bronze_hudi_table_name": f"bronze_{table['hudi_table_name']}",
    }
    for key, value in values.items():
        template = template.replace("${" + key + "}", value)
    return template


def submit_sql_token(endpoint: str, project_id: str, token: str, sql: str, queue: str) -> dict:
    url = f"{endpoint.rstrip('/')}/v1.0/{project_id}/jobs/submit-job"
    return post_json(url, token, {"sql": sql, "engine_type": "spark", "queue_name": queue})


def sql_state_token(endpoint: str, project_id: str, token: str, job_id: str) -> str:
    url = f"{endpoint.rstrip('/')}/v1.0/{project_id}/jobs/{job_id}/status"
    data = get_json(url, token)
    return str(data.get("status") or data.get("state") or data.get("job_status") or "unknown")


def sql_preview_token(endpoint: str, project_id: str, token: str, job_id: str, queue: str) -> dict:
    encoded_queue = urllib.parse.quote(queue)
    url = f"{endpoint.rstrip('/')}/v1.0/{project_id}/jobs/{job_id}/preview?queue-name={encoded_queue}"
    return get_json(url, token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run notebook-triggered raw->bronze->silver->SQL DLI workflow.")
    parser.add_argument("--execute", action="store_true", help="Actually submit jobs. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--auth", choices=["sdk", "token"], default="token")
    parser.add_argument("--interval-seconds", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=30)
    args = parser.parse_args()

    workflow = json.loads((ROOT / "runtime" / "workflow-plan.json").read_text(encoding="utf-8"))
    if args.limit:
        workflow = workflow[: args.limit]

    endpoint = os.environ.get("DLI_ENDPOINT", "https://dli.la-south-2.myhuaweicloud.com")
    project_id = os.environ.get("HUAWEICLOUD_PROJECT_ID", "<project-id>")
    queue = os.environ.get("DLI_QUEUE_NAME", "default")
    token = os.environ.get("HUAWEICLOUD_X_AUTH_TOKEN", "")
    client = dli_client() if args.execute and args.auth == "sdk" else None

    run_summary = []
    for table_plan in workflow:
        table_name = table_plan["table_name"]
        table = next(t for t in json.loads((ROOT / "config" / "job-config.json").read_text(encoding="utf-8"))["tables"] if t["table_name"] == table_name)
        stage_summary = {"table_name": table_name, "stages": []}
        print(f"workflow_table_start {table_name}")

        for stage_name, payload_ref in [("bronze", table_plan["bronze_payload"]), ("silver", table_plan["silver_payload"])]:
            payload = json.loads((ROOT / payload_ref).read_text(encoding="utf-8"))
            if not args.execute:
                print(f"DRY RUN submit {stage_name} spark job {payload['name']}")
                stage_summary["stages"].append({"stage": stage_name, "mode": "dry-run", "payload": payload_ref})
                continue
            if args.auth == "sdk":
                response = submit_spark_sdk(client, payload)
                get_state = lambda job_id: spark_state_sdk(client, job_id)
            else:
                if not token:
                    raise SystemExit("HUAWEICLOUD_X_AUTH_TOKEN is required for token auth")
                url = f"{endpoint.rstrip('/')}/v2.0/{project_id}/batches"
                response = post_json(url, token, payload)
                get_state = lambda job_id: get_json(f"{endpoint.rstrip('/')}/v2.0/{project_id}/batches/{job_id}/state", token).get("state", "unknown")
            job_id = extract_id(response)
            final_state = wait_for_state(get_state, job_id, payload["name"], args.interval_seconds, args.max_polls)
            stage_summary["stages"].append({"stage": stage_name, "job_id": job_id, "state": final_state, "response": response})

        for sql_name in ["00_show_silver_table.sql", "01_validate_silver_table.sql"]:
            sql = render_sql(sql_name, table)
            if not args.execute:
                print(f"DRY RUN submit SQL {sql_name}: {sql}")
                stage_summary["stages"].append({"stage": "sql", "mode": "dry-run", "script": sql_name, "sql": sql})
                continue
            if args.auth == "sdk":
                response = submit_sql_sdk(client, sql, queue)
                job_id = extract_id(response)
                final_state = wait_for_state(lambda jid: sql_state_sdk(client, jid), job_id, sql_name, args.interval_seconds, args.max_polls)
                preview = sql_preview_sdk(client, job_id, queue)
            else:
                response = submit_sql_token(endpoint, project_id, token, sql, queue)
                job_id = extract_id(response)
                final_state = wait_for_state(lambda jid: sql_state_token(endpoint, project_id, token, jid), job_id, sql_name, args.interval_seconds, args.max_polls)
                preview = sql_preview_token(endpoint, project_id, token, job_id, queue)
            stage_summary["stages"].append({"stage": "sql", "script": sql_name, "job_id": job_id, "state": final_state, "preview": preview})

        run_summary.append(stage_summary)

    runtime = ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "notebook-dataflow-run-summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print(json.dumps({"tables": len(run_summary), "summary_path": str(runtime / "notebook-dataflow-run-summary.json")}, indent=2))


if __name__ == "__main__":
    main()
