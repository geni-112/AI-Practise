from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkmrs.v2 import MrsClient
from huaweicloudsdkmrs.v2.model import ShowJobExeListNewRequest, ShowSingleJobExeRequest
from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion
from obs import ObsClient


SUCCESS_TOKENS = {"SUCCESS", "SUCCEEDED", "FINISHED", "COMPLETED", "COMPLETE"}
FAILURE_TOKENS = {"FAILED", "FAIL", "ERROR", "KILLED", "CANCELED", "CANCELLED", "TERMINATED"}


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit(f"Missing required environment variable. Tried: {', '.join(names)}")


def build_mrs_client(region: str) -> MrsClient:
    credentials = BasicCredentials(
        env_first("HUAWEICLOUD_ACCESS_KEY", "HW_ACCESS_KEY"),
        env_first("HUAWEICLOUD_SECRET_KEY", "HW_SECRET_KEY"),
        env_first("HUAWEICLOUD_PROJECT_ID", "HW_PROJECT_ID"),
    )
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or os.environ.get("HW_SECURITY_TOKEN")
    if security_token:
        credentials = credentials.with_security_token(security_token)
    return (
        MrsClient.new_builder()
        .with_credentials(credentials)
        .with_region(MrsRegion.value_of(region))
        .build()
    )


def build_obs_client(region: str) -> ObsClient:
    return ObsClient(
        access_key_id=env_first("HUAWEICLOUD_ACCESS_KEY", "HW_ACCESS_KEY"),
        secret_access_key=env_first("HUAWEICLOUD_SECRET_KEY", "HW_SECRET_KEY"),
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or os.environ.get("HW_SECURITY_TOKEN"),
        server=f"https://obs.{region}.myhuaweicloud.com",
    )


def job_to_dict(job: Any) -> dict[str, Any]:
    return {
        "job_id": getattr(job, "job_id", ""),
        "job_name": getattr(job, "job_name", ""),
        "job_state": getattr(job, "job_state", ""),
        "job_result": getattr(job, "job_result", ""),
        "job_progress": getattr(job, "job_progress", None),
        "job_type": getattr(job, "job_type", ""),
        "submitted_time": getattr(job, "submitted_time", None),
        "started_time": getattr(job, "started_time", None),
        "finished_time": getattr(job, "finished_time", None),
        "elapsed_time": getattr(job, "elapsed_time", None),
        "tracking_url": getattr(job, "tracking_url", ""),
        "app_id": getattr(job, "app_id", ""),
        "queue": getattr(job, "queue", ""),
    }


def terminal_status(job: Any) -> str | None:
    values = [
        str(getattr(job, "job_result", "") or "").upper(),
        str(getattr(job, "job_state", "") or "").upper(),
    ]
    if any(value in FAILURE_TOKENS for value in values):
        return "failed"
    if any(value in SUCCESS_TOKENS for value in values):
        return "success"
    return None


def find_latest_job(client: MrsClient, cluster_id: str, job_name: str) -> str:
    request = ShowJobExeListNewRequest(cluster_id=cluster_id, job_name=job_name, limit="20", offset="1")
    response = client.show_job_exe_list_new(request)
    jobs = list(response.job_list or [])
    if not jobs:
        raise SystemExit(f"No MRS jobs found for cluster_id={cluster_id}, job_name={job_name}")
    jobs.sort(key=lambda item: getattr(item, "submitted_time", 0) or 0, reverse=True)
    job_id = getattr(jobs[0], "job_id", "")
    if not job_id:
        raise SystemExit(f"Latest MRS job for {job_name} did not expose job_id")
    return job_id


def wait_for_job(
    client: MrsClient,
    cluster_id: str,
    job_id: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_job: Any = None
    while time.time() <= deadline:
        response = client.show_single_job_exe(
            ShowSingleJobExeRequest(cluster_id=cluster_id, job_execution_id=job_id)
        )
        last_job = response.job_detail
        status = terminal_status(last_job)
        if status:
            result = job_to_dict(last_job)
            result["terminal_status"] = status
            return result
        time.sleep(poll_seconds)
    result = job_to_dict(last_job) if last_job else {"job_id": job_id}
    result["terminal_status"] = "timeout"
    return result


def list_csv_keys(client: ObsClient, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    marker: str | None = None
    while True:
        response = client.listObjects(bucket, prefix=prefix, marker=marker, max_keys=1000)
        if response.status >= 300:
            raise SystemExit(f"OBS listObjects failed: status={response.status}, reason={response.reason}")
        body = response.body
        for item in body.contents or []:
            key = item.key
            if key.endswith(".csv") and "/_" not in key and not key.endswith("_SUCCESS"):
                keys.append(key)
        if not body.is_truncated:
            break
        marker = body.next_marker
        if not marker:
            break
    return keys


def read_csv_object(client: ObsClient, bucket: str, key: str) -> list[dict[str, str]]:
    response = client.getObject(bucket, key, loadStreamInMemory=True)
    if response.status >= 300:
        raise SystemExit(f"OBS getObject failed for {key}: status={response.status}, reason={response.reason}")
    buffer = response.body.buffer
    if isinstance(buffer, bytes):
        text = buffer.decode("utf-8-sig")
    else:
        text = str(buffer)
    return list(csv.DictReader(text.splitlines()))


def fetch_gold_rows(client: ObsClient, bucket: str, prefix: str) -> tuple[list[str], list[dict[str, str]]]:
    keys = list_csv_keys(client, bucket, prefix)
    rows: list[dict[str, str]] = []
    for key in keys:
        rows.extend(read_csv_object(client, bucket, key))
    return keys, rows


def fetch_mrs_audit(client: ObsClient, bucket: str, prefix: str) -> dict[str, Any]:
    response = client.listObjects(bucket, prefix=prefix, max_keys=100)
    if response.status >= 300:
        raise SystemExit(
            f"OBS listObjects failed for MRS audit: status={response.status}, reason={response.reason}"
        )
    keys = [
        item.key
        for item in response.body.contents or []
        if not item.key.endswith("/") and "/_" not in item.key
    ]
    if not keys:
        return {}
    object_response = client.getObject(bucket, keys[0], loadStreamInMemory=True)
    if object_response.status >= 300:
        raise SystemExit(
            f"OBS getObject failed for MRS audit: status={object_response.status}, "
            f"reason={object_response.reason}"
        )
    buffer = object_response.body.buffer
    text = buffer.decode("utf-8-sig") if isinstance(buffer, bytes) else str(buffer)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return json.loads(first_line) if first_line else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def publish_evidence(public_dir: Path, run_id: str, evidence: dict[str, Any]) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    write_json(public_dir / "latest_e2e_result.json", evidence)
    write_json(public_dir / f"{run_id}_e2e_result.json", evidence)
    write_json(
        public_dir / "latest_gold_preview.json",
        {
            "run_id": run_id,
            "generated_at": evidence["generated_at"],
            "gold_prefix": evidence["gold_prefix"],
            "gold_row_count": evidence["gold_row_count"],
            "rows": evidence["gold_preview_rows"],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for MRS smoke job and fetch OBS gold preview.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument("--job-id", default="")
    parser.add_argument("--job-name", default="")
    parser.add_argument("--agent-run-id", default="")
    parser.add_argument("--agent-release-prefix", default="")
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION") or os.environ.get("HW_REGION_NAME") or "la-south-2")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--skip-job-wait", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--publish-dir",
        default=str(Path(__file__).resolve().parents[1] / "public_evidence"),
        help="Directory used by the FastAPI frontend to display latest real-cloud evidence.",
    )
    args = parser.parse_args()

    mrs_client = build_mrs_client(args.region)
    obs_client = build_obs_client(args.region)

    job_id = args.job_id
    if not args.skip_job_wait and not job_id:
        if not args.job_name:
            raise SystemExit("--job-id or --job-name is required unless --skip-job-wait is set")
        job_id = find_latest_job(mrs_client, args.cluster_id, args.job_name)

    if args.skip_job_wait:
        job_result = {"terminal_status": "skipped", "job_id": job_id, "job_name": args.job_name}
    else:
        job_result = wait_for_job(mrs_client, args.cluster_id, job_id, args.timeout_seconds, args.poll_seconds)

    gold_prefix = f"gold/sat/{args.run_id}/taxpayer_gold_csv/"
    object_keys, rows = fetch_gold_rows(obs_client, args.bucket, gold_prefix)
    mrs_audit = fetch_mrs_audit(
        obs_client,
        args.bucket,
        f"audit/{args.run_id}/mrs_audit.json/",
    )
    direct_rfc_exposed = any("rfc" == key.lower() for row in rows for key in row.keys())
    evidence = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region": args.region,
        "bucket": args.bucket,
        "cluster_id": args.cluster_id,
        "job": job_result,
        "prompt_to_artifact": bool(args.agent_run_id),
        "agent_run_id": args.agent_run_id,
        "agent_release_prefix": args.agent_release_prefix,
        "gold_prefix": f"obs://{args.bucket}/{gold_prefix}",
        "gold_object_keys": object_keys,
        "gold_row_count": len(rows),
        "gold_preview_rows": rows[:20],
        "iceberg": mrs_audit.get("iceberg", {}),
        "mrs_audit": mrs_audit,
        "direct_rfc_exposed": direct_rfc_exposed,
        "duckdb_used": False,
    }

    output = Path(args.output) if args.output else Path(".cloud_real_bigdata_work") / args.run_id / "e2e_result.json"
    write_json(output, evidence)
    publish_evidence(Path(args.publish_dir), args.run_id, evidence)

    upload_response = obs_client.putContent(
        args.bucket,
        f"audit/{args.run_id}/e2e_result.json",
        json.dumps(evidence, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    if upload_response.status >= 300:
        raise SystemExit(f"OBS audit upload failed: status={upload_response.status}, reason={upload_response.reason}")

    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    if job_result.get("terminal_status") not in {"success", "skipped"}:
        sys.exit(2)
    if not rows:
        sys.exit(4)
    if not evidence["iceberg"].get("verified"):
        sys.exit(5)
    if direct_rfc_exposed:
        sys.exit(3)


if __name__ == "__main__":
    main()
