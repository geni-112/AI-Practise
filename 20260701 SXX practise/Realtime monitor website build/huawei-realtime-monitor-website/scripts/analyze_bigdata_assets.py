#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MONITOR_DATA = ROOT / "monitor" / "data"
EXPORTS = ROOT / "exports"
SCRIPT_URI_RE = re.compile(r"obs://[^\s,\]\)\"']+\.(?:py|sql|jar)", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def refresh_seconds() -> int:
    try:
        return max(5, int(os.environ.get("SAT_MONITOR_REFRESH_SECONDS", "20")))
    except ValueError:
        return 20


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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
    resource = {
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
    if service == "ecs":
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        description = str(row.get("description") or "")
        name = str(resource.get("name") or "")
        if metadata.get("lockSource") == "MRS":
            resource["role"] = "MRS node"
            resource["pipeline_parent"] = metadata.get("lockSourceId", "")
        elif "monitor" in name.lower() or "realtime monitor" in description.lower():
            resource["role"] = "monitor website"
            resource["excluded_from_pipeline"] = True
        else:
            resource["role"] = "infrastructure"
    if service == "vpc":
        resource["role"] = "network / public ingress"
    return resource


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
        table_prefixes: set[str] = set()
        total_bytes = 0
        for obj in objects:
            key = str(obj.get("key", ""))
            prefix = key.split("/", 1)[0] if "/" in key else "(root)"
            prefixes[prefix] += 1
            total_bytes += int(obj.get("size") or 0)
            if "/metadata/" in key:
                table_prefixes.add(key.split("/metadata/", 1)[0])
            elif key.endswith((".parquet", ".orc", ".avro")) and "/" in key:
                parts = key.split("/")
                table_prefixes.add("/".join(parts[:-1]))
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
                "prefixes": len(prefixes),
                "tables": len(table_prefixes),
                "sample_limit": payload.get("sample_limit"),
                "is_truncated": bool(payload.get("is_truncated")),
            }
        )
        catalog.append(
            {
                "system": "OBS",
                "category": "bucket",
                "name": f"obs://{bucket}/",
                "format": "OBS bucket",
                "columns": None,
                "rows": None,
                "objects": len(objects),
                "bytes": total_bytes,
                "detail": f"{len(prefixes)} prefixes; {len(table_prefixes)} table-like paths inferred from object layout",
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
        for table in sorted(table_prefixes)[:80]:
            catalog.append(
                {
                    "system": "OBS",
                    "category": "table path",
                    "name": f"obs://{bucket}/{table}/",
                    "format": "Iceberg/object table path",
                    "columns": None,
                    "rows": None,
                    "objects": None,
                    "detail": "Table-like path inferred from metadata or columnar files",
                }
            )
    return catalog, resources


def catalog_layer(row: dict[str, Any]) -> str:
    name = str(row.get("name") or "").lower()
    system = str(row.get("system") or "").lower()
    category = str(row.get("category") or "").lower()
    if system == "rds" or "/gold/" in name or "serving" in category:
        return "Gold"
    if "/silver/" in name or "curated" in name or "/mvp/iceberg/mvp_rec_" in name or "resico_marcas" in name:
        return "Silver"
    if "/bronze/" in name or "/mvp/iceberg/" in name:
        return "Bronze"
    if (
        "/raw/" in name
        or "/input/" in name
        or "datos_idc" in name
        or "dlf-log" in name
        or "/tmp/" in name
        or "/temp/" in name
        or "log" in category
    ):
        return "RAW"
    return "Support"


def catalog_status(row: dict[str, Any]) -> str:
    if row.get("status"):
        return str(row["status"])
    if row.get("objects") == 0:
        return "empty"
    if row.get("objects") is not None:
        return "sampled"
    if str(row.get("category") or "").lower() == "table path":
        return "inferred"
    return "sampled"


def enrich_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in catalog:
        row["layer"] = row.get("layer") or catalog_layer(row)
        row["status"] = row.get("status") or catalog_status(row)
    return catalog


def iso_from_millis(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number_value = int(value)
    except (TypeError, ValueError):
        return str(value)
    if number_value > 10_000_000_000:
        number_value = number_value / 1000
    return datetime.fromtimestamp(number_value, timezone.utc).replace(microsecond=0).isoformat()


def script_name_from_uri(uri: str) -> str:
    clean = uri.split("#", 1)[0].rstrip("],)")
    return clean.rsplit("/", 1)[-1] or clean


def script_layer(name: str, detail: str = "") -> str:
    text_value = f"{name} {detail}".lower()
    if "iceberg2pg" in text_value or "rds" in text_value or "postgres" in text_value or "pg" in text_value:
        return "Gold"
    if "opt_zorder" in text_value or "partition" in text_value or "mvp_rec" in text_value:
        return "Silver"
    if "iceberg" in text_value or "create_table" in text_value or "padron" in text_value:
        return "Bronze"
    if "mock" in text_value or "raw" in text_value or "datos_idc" in text_value or "testcase" in text_value:
        return "RAW"
    return "Support"


def script_status_catalog(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for job in jobs:
        detail = str(job.get("detail") or "")
        script_uris = SCRIPT_URI_RE.findall(detail)
        if not script_uris:
            script_uris = [""]
        for uri in script_uris:
            name = script_name_from_uri(uri) if uri else str(job.get("name") or "unnamed flow job")
            key = (str(job.get("source") or ""), name, str(job.get("started_at") or ""))
            if key in seen:
                continue
            seen.add(key)
            layer = script_layer(name, detail)
            started = iso_from_millis(job.get("started_at"))
            finished = iso_from_millis(job.get("finished_at"))
            parts = [
                f"layer={layer}",
                f"job={job.get('name') or 'unnamed'}",
            ]
            if started:
                parts.append(f"started={started}")
            if finished:
                parts.append(f"finished={finished}")
            if uri:
                parts.append(f"path={uri}")
            elif detail:
                parts.append(f"detail={detail[:220]}")
            rows.append(
                {
                    "source": str(job.get("source") or "Unknown"),
                    "name": name,
                    "status": str(job.get("status") or "unknown"),
                    "type": str(job.get("type") or "Flow script"),
                    "layer": layer,
                    "detail": "; ".join(parts),
                }
            )
    return rows[:120]


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
    mrs_jobs = compact_list(source_payload(inventory, "mrs_jobs_v2"), ("job_list", "jobs", "job_executions", "data"))
    for job in mrs_jobs:
        jobs.append(
            {
                "source": "MRS",
                "name": first(job.get("job_name"), job.get("name"), job.get("job_id"), job.get("id")),
                "status": first(job.get("job_result"), job.get("job_state"), job.get("job_status"), job.get("status"), default="unknown"),
                "type": first(job.get("job_type"), job.get("type"), default="MRS job"),
                "started_at": first(job.get("started_time"), job.get("start_time"), default=""),
                "finished_at": first(job.get("finished_time"), job.get("end_time"), default=""),
                "detail": first(job.get("arguments"), job.get("jar_path"), default=""),
            }
        )
    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        started = row.get("started_at")
        if isinstance(started, (int, float)):
            return (int(started), row.get("source", ""))
        if isinstance(started, str) and started.isdigit():
            return (int(started), row.get("source", ""))
        return (0, row.get("source", ""))

    return sorted(jobs, key=sort_key, reverse=True)


def active_resources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inactive = {"terminated", "deleted", "deleting", "failed", "error", "unavailable"}
    return [row for row in rows if str(row.get("status", "")).lower() not in inactive]


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
    object_count = sum(int(row.get("objects") or 0) for row in resources)
    table_count = sum(int(row.get("tables") or 0) for row in resources)
    byte_count = sum(int(row.get("bytes") or 0) for row in resources)
    prefix_count = sum(int(row.get("prefixes") or 0) for row in resources)
    stage = {
        "key": key,
        "label": label,
        "status": status,
        "progress": progress,
        "resource_count": len(resources),
        "job_count": len(job_rows),
    }
    if object_count or table_count or byte_count or prefix_count:
        stage.update(
            {
                "object_count": object_count,
                "table_count": table_count,
                "byte_count": byte_count,
                "prefix_count": prefix_count,
            }
        )
    return stage


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

    catalog: list[dict[str, Any]] = []
    obs_catalog, obs_sample_resources = analyze_obs_samples(source_payload(inventory, "obs_samples"))
    catalog.extend(obs_catalog)
    service_rows["obs"].extend(obs_sample_resources)

    jobs = extract_jobs(inventory)

    services: dict[str, Any] = {}
    labels = {
        "obs": "OBS Object Storage",
        "oms": "OMS Migration",
        "rds": "RDS PostgreSQL Serving",
        "dms": "DMS Kafka",
        "mrs": "MRS Compute",
        "dataarts": "DataArts Factory",
        "cdm": "CDM Migration",
        "ecs": "ECS Infrastructure",
        "vpc": "VPC/EIP Infrastructure",
    }
    error_source_map = {
        "obs": ("obs_samples", "rms_all_resources"),
        "mrs": ("mrs_clusters_v11", "mrs_jobs_v2"),
        "dataarts": ("dataarts_workspaces", "dataarts_jobs"),
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
    if services["obs"]["resource_count"]:
        stages.append(build_stage("obs", "OBS Data Lake / Logs", active_resources(service_rows["obs"])))
    if services["oms"]["resource_count"]:
        stages.append(build_stage("oms", "OMS Batch Ingestion", active_resources(service_rows["oms"])))
    if services["rds"]["resource_count"] or services["dms"]["resource_count"]:
        if services["dms"]["resource_count"]:
            stages.append(build_stage("streaming", "DMS Realtime Ingestion", active_resources(service_rows["dms"])))
    stages.extend(
        [
            build_stage("dataarts", "DataArts / CDM Orchestration", active_resources(service_rows["dataarts"] + service_rows["cdm"]), dataarts_job_rows),
            build_stage("mrs", "MRS Spark/Flink Processing", active_resources(service_rows["mrs"]), mrs_jobs),
            build_stage("rds", "RDS PostgreSQL Serving", active_resources(service_rows["rds"])),
        ]
    )

    risks = []
    if not services["obs"]["resource_count"]:
        risks.append("No OBS bucket or object prefixes were sampled. Configure OBS_BUCKETS or keep OBS paths in job arguments if data-structure sampling is required.")
    if not services["mrs"]["resource_count"]:
        risks.append("No MRS cluster was identified. If MRS is used, verify the region, project ID, and IAM permissions.")
    if not dataarts_job_rows and not services["dataarts"]["resource_count"]:
        risks.append("No DataArts Factory jobs were identified. Set DATAARTS_WORKSPACE_ID when the workspace ID is confirmed.")
    if not catalog:
        risks.append("No OBS object prefix data was collected. The monitor is currently resource-level only.")
    if not jobs:
        risks.append("No live MRS/DataArts job records were collected from API responses during this refresh.")
    for name, message in source_errors.items():
        if name in {"dws_clusters", "dws_schema"}:
            continue
        risks.append(f"{name} collection was limited: {message}")

    recommendations = [
        "Use the SAT Mexico resource inventory as the source of truth for the end-to-end flow instead of reusing DockOne Brazil asset names.",
        "Keep the visible pipeline aligned to the current SAT flow: OBS storage, DataArts/CDM orchestration, MRS processing, then RDS PostgreSQL serving.",
        "Use OBS object counts as storage-level records; add table readers later if row-level counts are required.",
        "After the DataArts workspace ID is confirmed, collect job nodes and map each script to MRS and RDS actions.",
    ]

    pipeline_service_keys = ("obs", "oms", "dms", "cdm", "dataarts", "mrs", "rds")
    pipeline_services = {key: services[key] for key in pipeline_service_keys if key in services}
    healthy = sum(1 for service in pipeline_services.values() if service["status"] in {"healthy", "idle"})
    pipeline_resources = sum(len(active_resources(service_rows[key])) for key in pipeline_service_keys)
    infrastructure_resources = services["ecs"]["resource_count"] + services["vpc"]["resource_count"]
    inactive_resources = sum(service["resource_count"] for service in services.values()) - pipeline_resources - infrastructure_resources
    obs_resources = active_resources(service_rows["obs"])
    obs_object_count = sum(int(row.get("objects") or 0) for row in obs_resources)
    obs_table_count = sum(int(row.get("tables") or 0) for row in obs_resources)
    obs_prefix_count = sum(int(row.get("prefixes") or 0) for row in obs_resources)
    obs_byte_count = sum(int(row.get("bytes") or 0) for row in obs_resources)
    for row in active_resources(service_rows["rds"]):
        catalog.append(
            {
                "system": "RDS",
                "category": "serving database",
                "name": row.get("name") or row.get("id") or "RDS PostgreSQL",
                "format": row.get("type") or "PostgreSQL",
                "columns": None,
                "rows": None,
                "objects": None,
                "layer": "Gold",
                "status": row.get("status") or "healthy",
                "detail": "Serving layer after MRS processing.",
            }
        )
    catalog = enrich_catalog(catalog)
    return {
        "generated_at": utc_now(),
        "refresh_seconds": refresh_seconds(),
        "region": inventory.get("region", ""),
        "project": inventory.get("project", {}),
        "account": inventory.get("account", {}),
        "summary": {
            "healthy_services": healthy,
            "total_services": len(pipeline_services),
            "resource_count": pipeline_resources,
            "infrastructure_count": infrastructure_resources,
            "inactive_count": max(0, inactive_resources),
            "obs_object_count": obs_object_count,
            "obs_table_count": obs_table_count,
            "obs_prefix_count": obs_prefix_count,
            "obs_byte_count": obs_byte_count,
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
        "script_chain": script_status_catalog(jobs),
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
