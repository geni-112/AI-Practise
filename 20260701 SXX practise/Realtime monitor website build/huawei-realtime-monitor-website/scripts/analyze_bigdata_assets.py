#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MONITOR_DATA = ROOT / "monitor" / "data"
EXPORTS = ROOT / "exports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compact_list(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def source_payload(inventory: dict[str, Any], name: str) -> dict[str, Any]:
    source = (inventory.get("sources") or {}).get(name) or {}
    payload = source.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def resource_text(resource: dict[str, Any]) -> str:
    parts = [
        resource.get("provider"),
        resource.get("resource_provider"),
        resource.get("type"),
        resource.get("resource_type"),
        resource.get("name"),
        resource.get("resource_name"),
        resource.get("id"),
        resource.get("resource_id"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def classify_rms(resources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    classes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rules = {
        "obs": ("obs", "bucket"),
        "mrs": ("mrs", "mapreduce"),
        "dws": ("dws", "data warehouse"),
        "dataarts": ("dataarts", "dayu", "dataartsstudio"),
        "rds": ("rds", "postgres", "mysql"),
        "dms": ("dms", "kafka", "rabbitmq"),
        "oms": ("oms", "migration"),
        "cdm": ("cdm", "cloud data migration"),
        "ecs": ("ecs", "cloudservers", "server"),
        "vpc": ("vpc", "subnet", "securitygroup", "publicip", "eip"),
    }
    for resource in resources:
        text = resource_text(resource)
        matched = False
        for key, needles in rules.items():
            if any(needle in text for needle in needles):
                classes[key].append(resource)
                matched = True
        if not matched:
            classes["other"].append(resource)
    return classes


def first(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def normalize_resource(row: dict[str, Any], service: str) -> dict[str, Any]:
    datastore = row.get("datastore")
    return {
        "service": service.upper(),
        "name": first(
            row.get("name"),
            row.get("resource_name"),
            row.get("clusterName"),
            row.get("cluster_name"),
            row.get("instance_name"),
            row.get("server_name"),
            row.get("id"),
            row.get("resource_id"),
        ),
        "id": first(
            row.get("id"),
            row.get("resource_id"),
            row.get("clusterId"),
            row.get("cluster_id"),
            row.get("instanceId"),
            row.get("instance_id"),
        ),
        "type": first(
            row.get("type"),
            row.get("resource_type"),
            row.get("engine"),
            row.get("job_type"),
            row.get("clusterVersion"),
            datastore.get("type") if isinstance(datastore, dict) else "",
        ),
        "status": first(
            row.get("status"),
            row.get("resource_status"),
            row.get("clusterState"),
            row.get("cluster_state"),
            row.get("state"),
            default="unknown",
        ),
        "region": first(row.get("region_id"), row.get("region"), row.get("dataCenter"), row.get("availabilityZoneId"), default=""),
    }


def service_status(count: int, errors: list[str] | None = None) -> str:
    if errors:
        return "warning" if count else "unavailable"
    return "healthy" if count else "idle"


def table_key(row: dict[str, Any]) -> str:
    return f"{row.get('schema', '')}.{row.get('table', '')}".strip(".")


def analyze_dws_schema(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for column in columns:
        grouped[table_key(column)].append(column)
    catalog = []
    for name, cols in sorted(grouped.items()):
        catalog.append(
            {
                "system": "DWS",
                "category": "table",
                "name": name,
                "format": "GaussDB(DWS)",
                "columns": len(cols),
                "rows": None,
                "detail": ", ".join(f"{col['column']} {col['type']}" for col in cols[:8]),
            }
        )
    return catalog


def analyze_obs_samples(samples: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    for bucket, payload in samples.items():
        if not isinstance(payload, dict) or not payload.get("ok"):
            continue
        objects = payload.get("objects") or []
        prefixes = Counter()
        total_bytes = 0
        for obj in objects:
            key = str(obj.get("key", ""))
            prefix = key.split("/", 1)[0] if "/" in key else "(root)"
            prefixes[prefix] += 1
            total_bytes += int(obj.get("size") or 0)
        resources.append(
            {
                "service": "OBS",
                "name": bucket,
                "id": bucket,
                "type": "bucket",
                "status": "sampled",
                "region": "",
                "objects": len(objects),
                "bytes": total_bytes,
            }
        )
        for prefix, count in prefixes.most_common():
            catalog.append(
                {
                    "system": "OBS",
                    "category": "prefix",
                    "name": f"obs://{bucket}/{prefix}/",
                    "format": "object prefix",
                    "columns": None,
                    "rows": None,
                    "objects": count,
                    "detail": "Sampled from OBS object listing",
                }
            )
    return catalog, resources


def extract_jobs(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    dataarts_jobs = compact_list(source_payload(inventory, "dataarts_jobs"), ("jobs",))
    for job in dataarts_jobs:
        jobs.append(
            {
                "source": "DataArts",
                "name": first(job.get("name"), job.get("job_name"), job.get("id")),
                "status": first(job.get("last_instance_status"), job.get("status"), job.get("definition_status"), default="unknown"),
                "type": first(job.get("job_type"), job.get("type"), default="Factory job"),
                "started_at": first(job.get("start_time"), job.get("last_instance_start_time"), default=""),
                "finished_at": first(job.get("end_time"), job.get("last_instance_end_time"), default=""),
                "detail": first(job.get("description"), job.get("owner"), default=""),
            }
        )
    mrs_jobs = compact_list(source_payload(inventory, "mrs_jobs_v2"), ("job_list", "jobs", "data"))
    for job in mrs_jobs:
        jobs.append(
            {
                "source": "MRS",
                "name": first(job.get("job_name"), job.get("name"), job.get("job_id")),
                "status": first(job.get("job_result"), job.get("job_state"), job.get("status"), default="unknown"),
                "type": first(job.get("job_type"), job.get("type"), default="MRS job"),
                "started_at": first(job.get("started_time"), job.get("start_time"), default=""),
                "finished_at": first(job.get("finished_time"), job.get("end_time"), default=""),
                "detail": first(job.get("arguments"), job.get("jar_path"), default=""),
            }
        )
    return jobs


def build_stage(key: str, label: str, resources: list[dict[str, Any]], jobs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    job_rows = jobs or []
    has_failure = any(str(row.get("status", "")).lower() in {"failed", "failure", "error", "killed"} for row in job_rows)
    running = any(str(row.get("status", "")).lower() in {"running", "submitted", "executing"} for row in job_rows)
    if has_failure:
        progress = 45
        status = "warning"
    elif running:
        progress = 70
        status = "warning"
    elif resources or job_rows:
        progress = 100
        status = "healthy"
    else:
        progress = 0
        status = "idle"
    return {
        "key": key,
        "label": label,
        "status": status,
        "progress": progress,
        "resource_count": len(resources),
        "job_count": len(job_rows),
    }


def assess(inventory: dict[str, Any]) -> dict[str, Any]:
    sources = inventory.get("sources") or {}
    source_errors = {
        key: value.get("error", "")
        for key, value in sources.items()
        if isinstance(value, dict) and not value.get("ok")
    }
    rms_resources = compact_list(source_payload(inventory, "rms_all_resources"), ("resources",))
    classified = classify_rms(rms_resources)

    service_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for service, rows in classified.items():
        if service == "other":
            continue
        service_rows[service].extend(normalize_resource(row, service) for row in rows)

    service_map = {
        "mrs": ("mrs_clusters_v11", ("cluster_infos", "clusters", "data")),
        "dws": ("dws_clusters", ("clusters", "data")),
        "rds": ("rds_instances", ("instances", "data")),
        "dms": ("dms_instances", ("instances", "data")),
        "oms": ("oms_tasks", ("tasks", "data")),
        "cdm": ("cdm_clusters", ("clusters", "data")),
        "ecs": ("ecs_servers", ("servers", "cloudservers", "data")),
        "vpc": ("vpc_publicips", ("publicips", "data")),
    }
    for service, (source_name, keys) in service_map.items():
        rows = compact_list(source_payload(inventory, source_name), keys)
        service_rows[service].extend(normalize_resource(row, service) for row in rows)

    dws_columns = compact_list(source_payload(inventory, "dws_schema"), ("columns",))
    catalog = analyze_dws_schema(dws_columns)
    obs_catalog, obs_sample_resources = analyze_obs_samples(source_payload(inventory, "obs_samples"))
    catalog.extend(obs_catalog)
    service_rows["obs"].extend(obs_sample_resources)

    dataarts_jobs = compact_list(source_payload(inventory, "dataarts_jobs"), ("jobs",))
    service_rows["dataarts"].extend(normalize_resource(row, "dataarts") for row in dataarts_jobs)
    jobs = extract_jobs(inventory)

    services: dict[str, Any] = {}
    labels = {
        "obs": "OBS Object Storage",
        "oms": "OMS Migration",
        "rds": "RDS Data Source",
        "dms": "DMS Kafka",
        "mrs": "MRS Compute",
        "dataarts": "DataArts Orchestration",
        "dws": "DWS Warehouse",
        "cdm": "CDM Migration",
        "ecs": "ECS/Web",
        "vpc": "VPC/EIP",
    }
    error_source_map = {
        "obs": ("obs_samples", "rms_all_resources"),
        "mrs": ("mrs_clusters_v11", "mrs_jobs_v2"),
        "dataarts": ("dataarts_workspaces", "dataarts_jobs"),
        "dws": ("dws_clusters", "dws_schema"),
        "rds": ("rds_instances",),
        "dms": ("dms_instances",),
        "oms": ("oms_tasks",),
        "cdm": ("cdm_clusters",),
        "ecs": ("ecs_servers",),
        "vpc": ("vpc_publicips",),
    }
    for key, label in labels.items():
        rows = service_rows.get(key, [])
        relevant_errors = [
            message
            for name, message in source_errors.items()
            if name in error_source_map.get(key, ())
        ]
        services[key] = {
            "key": key,
            "label": label,
            "status": service_status(len(rows), relevant_errors),
            "resource_count": len(rows),
            "resources": rows[:80],
            "errors": relevant_errors,
        }

    mrs_jobs = [job for job in jobs if job.get("source") == "MRS"]
    dataarts_job_rows = [job for job in jobs if job.get("source") == "DataArts"]
    stages = []
    if services["oms"]["resource_count"]:
        stages.append(build_stage("oms", "S3/OMS Batch Ingestion", service_rows["oms"]))
    if services["rds"]["resource_count"] or services["dms"]["resource_count"]:
        stages.append(build_stage("streaming", "RDS/DMS Realtime Ingestion", service_rows["rds"] + service_rows["dms"]))
    stages.extend(
        [
            build_stage("obs", "OBS Raw/Lake", service_rows["obs"]),
            build_stage("mrs", "MRS Spark/Flink", service_rows["mrs"], mrs_jobs),
            build_stage("dataarts", "DataArts Scheduling", service_rows["dataarts"], dataarts_job_rows),
            build_stage("dws", "DWS Serving Layer", service_rows["dws"]),
        ]
    )
    if services["ecs"]["resource_count"]:
        stages.append(build_stage("ecs", "ECS/Web Monitoring", service_rows["ecs"]))

    risks = []
    if not services["obs"]["resource_count"]:
        risks.append("No OBS bucket or object prefixes were sampled. Configure OBS_BUCKETS and AK/SK if data-structure sampling is required.")
    if not services["mrs"]["resource_count"]:
        risks.append("No MRS cluster was identified. If MRS is used, verify the region, project ID, and IAM permissions.")
    if not services["dataarts"]["resource_count"]:
        risks.append("No DataArts jobs were identified. Set DATAARTS_WORKSPACE_ID when the workspace ID is confirmed.")
    if not catalog:
        risks.append("No DWS table schema or OBS object prefix data was collected. The monitor is currently resource-level only.")
    for name, message in source_errors.items():
        risks.append(f"{name} collection was limited: {message}")

    recommendations = [
        "Use the SAT Mexico resource inventory as the source of truth for the end-to-end flow instead of reusing DockOne Brazil asset names.",
        "Add OBS prefix sampling and DWS information_schema access to produce field-level data lineage.",
        "After the DataArts workspace ID is confirmed, collect job nodes and map each script to MRS and DWS actions.",
    ]

    healthy = sum(1 for service in services.values() if service["status"] in {"healthy", "idle"})
    total_resources = sum(service["resource_count"] for service in services.values())
    return {
        "generated_at": utc_now(),
        "refresh_seconds": 5,
        "region": inventory.get("region", ""),
        "project": inventory.get("project", {}),
        "account": inventory.get("account", {}),
        "summary": {
            "healthy_services": healthy,
            "total_services": len(services),
            "resource_count": total_resources,
            "catalog_count": len(catalog),
            "job_count": len(jobs),
            "risk_count": len(risks),
        },
        "topology": {
            "stages": stages,
        },
        "services": services,
        "catalog": catalog,
        "jobs": jobs[:80],
        "risks": risks,
        "recommendations": recommendations,
        "source_inventory_generated_at": inventory.get("generated_at"),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Huawei Cloud big-data inventory and generate monitor status.")
    parser.add_argument("--inventory", default=str(MONITOR_DATA / "inventory.json"))
    args = parser.parse_args()

    inventory = load_json(Path(args.inventory))
    if not inventory:
        inventory = {
            "generated_at": utc_now(),
            "region": "",
            "project": {},
            "account": {},
            "sources": {},
        }
    status = assess(inventory)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    snapshot = EXPORTS / f"bigdata_assessment_{timestamp()}.json"
    write_json(snapshot, status)
    write_json(MONITOR_DATA / "status.json", status)
    print(f"Assessment written: {snapshot}")
    print(
        f"Resources: {status['summary']['resource_count']}; "
        f"catalog objects: {status['summary']['catalog_count']}; "
        f"jobs: {status['summary']['job_count']}; risks: {status['summary']['risk_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
