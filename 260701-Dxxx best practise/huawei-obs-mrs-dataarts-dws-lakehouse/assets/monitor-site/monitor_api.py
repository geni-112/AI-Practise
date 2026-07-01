#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
DEPLOYMENT = Path(
    os.environ.get("DOCKONE_DEPLOYMENT_DIR", str(WORKSPACE / "work" / "deployment"))
)
sys.path.insert(0, str(ROOT / "vendor"))

import requests
from obs import ObsClient
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdataartsstudio.v1 import (
    DataArtsStudioClient,
    ListFactoryJobInstancesByNameRequest,
    ListFactoryJobsRequest,
)
from huaweicloudsdkdataartsstudio.v1.region.dataartsstudio_region import (
    DataArtsStudioRegion,
)
from huaweicloudsdkdws.v2 import DwsClient, ListClusterDetailsRequest
from huaweicloudsdkdws.v2.region.dws_region import DwsRegion
from huaweicloudsdkmrs.v1 import MrsClient as MrsV1Client
from huaweicloudsdkmrs.v1 import ShowClusterDetailsRequest
from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion as MrsV1Region
from huaweicloudsdkmrs.v2 import MrsClient as MrsV2Client
from huaweicloudsdkmrs.v2 import ShowJobExeListNewRequest
from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion as MrsV2Region

try:
    import psycopg2
except ImportError:
    psycopg2 = None


REGION = "la-south-2"
PROJECT_ID = "09d63c269e80f5e32f4ec00754ed462d"
WORKSPACE_ID = "c4fc507387fa4d2983d569c490525f86"
BUCKET = "hwstaff-retail-lakehouse-09d63c-20260622"
MRS_ID = "2a45044c-7506-4b96-9993-70d8a8397ed5"
DWS_ID = "704f35bb-e05a-48cb-a765-9a543fe07bd8"
REFRESH_SECONDS = 5


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def epoch_ms(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def byte_label(value):
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024


def clamp_value(value, minimum=0, maximum=100):
    try:
        number = int(float(value or 0))
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class MonitorCollector:
    def __init__(self):
        ak = os.environ["HUAWEICLOUD_ACCESS_KEY"]
        sk = os.environ["HUAWEICLOUD_SECRET_KEY"]
        self.credentials = BasicCredentials(ak, sk, PROJECT_ID)
        self.obs = ObsClient(
            access_key_id=ak,
            secret_access_key=sk,
            server=f"https://obs.{REGION}.myhuaweicloud.com",
        )
        self.mrs_v1 = (
            MrsV1Client.new_builder()
            .with_credentials(self.credentials)
            .with_region(MrsV1Region.value_of(REGION))
            .build()
        )
        self.mrs_v2 = (
            MrsV2Client.new_builder()
            .with_credentials(self.credentials)
            .with_region(MrsV2Region.value_of(REGION))
            .build()
        )
        self.dws = (
            DwsClient.new_builder()
            .with_credentials(self.credentials)
            .with_region(DwsRegion.value_of(REGION))
            .build()
        )
        self.dataarts = (
            DataArtsStudioClient.new_builder()
            .with_credentials(self.credentials)
            .with_region(DataArtsStudioRegion.value_of(REGION))
            .build()
        )
        self.dws_sql_disabled_until = 0
        self.dws_sql_last_error = None

    def list_obs(self, prefix):
        marker = None
        rows = []
        while True:
            response = self.obs.listObjects(
                BUCKET, prefix=prefix, marker=marker, max_keys=1000
            )
            if response.status >= 300:
                raise RuntimeError(f"OBS list failed: {prefix} HTTP {response.status}")
            for item in response.body.contents or []:
                rows.append(
                    {
                        "key": item.key,
                        "size": int(item.size),
                        "modified": str(item.lastModified or ""),
                    }
                )
            if not response.body.is_truncated:
                return rows
            marker = response.body.next_marker

    def metric_rows(self):
        path = DEPLOYMENT / "runtime" / "dockone_table_metrics.csv"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return {row["table_name"]: row for row in csv.DictReader(handle)}

    def collect_obs(self):
        prefixes = {
            "raw": "raw/dockone_exampleapp/",
            "iceberg": "lake/iceberg/dockone/",
            "publish": "publish/dockone_table_metrics/current/",
        }
        objects = {name: self.list_obs(prefix) for name, prefix in prefixes.items()}
        metrics = self.metric_rows()
        table_files = {}
        for item in objects["iceberg"]:
            parts = item["key"].split("/")
            if len(parts) < 6 or parts[3] not in {"bronze", "silver", "golden"}:
                continue
            layer, table = parts[3], parts[4]
            key = (layer, table)
            row = table_files.setdefault(
                key, {"objects": 0, "bytes": 0, "metadata": 0, "parquet": 0}
            )
            row["objects"] += 1
            row["bytes"] += item["size"]
            row["metadata"] += int("/metadata/" in item["key"])
            row["parquet"] += int(item["key"].endswith(".parquet"))

        tables = []
        for (layer, table), stats in sorted(table_files.items()):
            metric = metrics.get(table, {})
            if layer == "bronze":
                rows = metric.get("bronze_event_count")
            elif layer == "silver":
                rows = metric.get("active_record_count")
            else:
                rows = len(metrics) if table == "dockone_table_metrics" else None
            tables.append(
                {
                    "system": "MRS Iceberg",
                    "category": layer.title(),
                    "name": table,
                    "format": "Apache Iceberg v2",
                    "rows": int(rows) if rows not in (None, "") else None,
                    **stats,
                }
            )

        layers = []
        for name, rows in objects.items():
            layers.append(
                {
                    "name": name,
                    "objects": len(rows),
                    "bytes": sum(item["size"] for item in rows),
                    "size": byte_label(sum(item["size"] for item in rows)),
                }
            )
        return {
            "status": "healthy",
            "name": BUCKET,
            "spec": "OBS Standard · pay-per-use",
            "region": REGION,
            "layers": layers,
            "objects": sum(len(rows) for rows in objects.values()),
            "bytes": sum(item["size"] for rows in objects.values() for item in rows),
            "tables": tables,
            "updated_at": utc_now(),
        }

    def collect_mrs(self):
        cluster = self.mrs_v1.show_cluster_details(
            ShowClusterDetailsRequest(cluster_id=MRS_ID)
        ).to_json_object()["cluster"]
        jobs = self.mrs_v2.show_job_exe_list_new(
            ShowJobExeListNewRequest(cluster_id=MRS_ID, limit="12")
        ).to_json_object()
        history = []
        for job in jobs.get("job_list") or []:
            history.append(
                {
                    "source": "MRS",
                    "name": job.get("job_name"),
                    "status": str(job.get("job_result") or job.get("job_state")).lower(),
                    "progress": job.get("job_progress"),
                    "started_at": epoch_ms(job.get("started_time")),
                    "finished_at": epoch_ms(job.get("finished_time")),
                    "duration_ms": job.get("elapsed_time"),
                    "id": job.get("job_id"),
                }
            )
        groups = [
            {
                "name": item.get("GroupName"),
                "role": item.get("nodeType"),
                "nodes": item.get("NodeNum"),
                "flavor": item.get("NodeSize"),
                "root_disk": f"{item.get('RootVolumeSize')} GB {item.get('RootVolumeType')}",
                "data_disk": (
                    f"{item.get('DataVolumeCount')} × {item.get('DataVolumeSize')} GB "
                    f"{item.get('DataVolumeType')}"
                ),
            }
            for item in cluster.get("nodeGroups") or []
        ]
        latest = history[0] if history else {}
        return {
            "status": "healthy"
            if str(cluster.get("clusterState")).lower() == "running"
            else "warning",
            "name": cluster.get("clusterName"),
            "spec": f"{cluster.get('clusterVersion')} · {cluster.get('totalNodeNum')} nodes",
            "state": cluster.get("clusterState"),
            "progress": latest.get("progress", 0),
            "components": [
                {
                    "name": item.get("componentName"),
                    "version": item.get("componentVersion"),
                }
                for item in cluster.get("componentList") or []
            ],
            "node_groups": groups,
            "history": history,
            "updated_at": utc_now(),
        }

    def collect_dataarts(self):
        response = self.dataarts.list_factory_jobs(
            ListFactoryJobsRequest(workspace=WORKSPACE_ID, limit=50, offset=0)
        ).to_json_object()
        jobs = []
        history = []
        for item in response.get("jobs") or []:
            if not (
                str(item.get("name", "")).startswith("dockone")
                or "golden" in str(item.get("name", ""))
            ):
                continue
            jobs.append(
                {
                    "name": item.get("name"),
                    "type": item.get("job_type"),
                    "definition_status": item.get("status"),
                    "last_status": item.get("last_instance_status"),
                    "last_finished_at": epoch_ms(item.get("last_instance_end_time")),
                }
            )
        for name in ("dockone_pipeline", "dockone_golden_to_dws"):
            try:
                result = self.dataarts.list_factory_job_instances_by_name(
                    ListFactoryJobInstancesByNameRequest(
                        workspace=WORKSPACE_ID, job_name=name, limit=10
                    )
                ).to_json_object()
            except Exception:
                continue
            for item in result.get("instances") or []:
                history.append(
                    {
                        "source": "DataArts",
                        "name": item.get("job_name"),
                        "status": item.get("status"),
                        "progress": 100 if item.get("status") == "success" else None,
                        "started_at": epoch_ms(item.get("start_time")),
                        "finished_at": epoch_ms(item.get("end_time")),
                        "duration_ms": item.get("execute_time"),
                        "id": str(item.get("instance_id")),
                    }
                )
        last = next((job for job in jobs if job.get("last_status")), {})
        return {
            "status": "healthy"
            if str(last.get("last_status", "")).lower() == "success"
            else "idle",
            "name": "DataArts Studio",
            "spec": "DataArts Factory · batch orchestration",
            "workspace_id": WORKSPACE_ID,
            "jobs": jobs,
            "history": history,
            "updated_at": utc_now(),
        }

    def collect_cdm(self):
        response = self.cdm.list_clusters(ListClustersRequest()).to_json_object()
        clusters = response.get("clusters") or []
        selected = next((item for item in clusters if item.get("id") == CDM_ID), None)
        if not selected:
            selected = clusters[0] if clusters else {}
        return {
            "status": "healthy"
            if selected.get("statusDetail") == "Normal"
            else "warning",
            "name": selected.get("name") or "CDM",
            "spec": (
                f"{selected.get('flavorName', 'unknown')} · "
                f"{(selected.get('datastore') or {}).get('version', 'unknown')}"
            ),
            "state": selected.get("statusDetail"),
            "private_ip": (
                (selected.get("instances") or [{}])[0].get("private_ip")
            ),
            "jobs": [],
            "note": "Cluster ready; no active Iceberg migration job is configured.",
            "updated_at": utc_now(),
        }

    def collect_dws_tables(self):
        if psycopg2 is None or not os.environ.get("DWS_PASSWORD"):
            raise RuntimeError("DWS SQL driver or password is unavailable")
        connection = psycopg2.connect(
            host=os.environ.get("DWS_HOST", "182.160.26.143"),
            port=int(os.environ.get("DWS_PORT", "8000")),
            dbname="gaussdb",
            user="dbaadmin",
            password=os.environ["DWS_PASSWORD"],
            connect_timeout=5,
            sslmode="prefer",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = 'dockone_golden'
                    ORDER BY table_type, table_name
                    """
                )
                definitions = cursor.fetchall()
                tables = []
                for schema, name, table_type in definitions:
                    count = None
                    if name in {"table_metrics", "table_metrics_stage"}:
                        cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{name}"')
                        count = int(cursor.fetchone()[0])
                    tables.append(
                        {
                            "system": "DWS",
                            "category": "View"
                            if table_type == "VIEW"
                            else (
                                "Staging" if name.endswith("_stage") else "Serving"
                            ),
                            "name": f"{schema}.{name}",
                            "format": table_type,
                            "rows": count,
                            "objects": None,
                            "bytes": None,
                        }
                    )
                return tables
        finally:
            connection.close()

    def collect_dws(self):
        cluster = self.dws.list_cluster_details(
            ListClusterDetailsRequest(cluster_id=DWS_ID)
        ).to_json_object()["cluster"]
        sql_error = None
        fallback_summary = load_json(DEPLOYMENT / "dockone-dws-load-summary.json")
        fallback_tables = [
            {
                "system": "DWS",
                "category": "Staging",
                "name": "dockone_golden.table_metrics_stage",
                "format": "DWS table - latest load summary",
                "rows": fallback_summary.get("rows"),
                "objects": None,
                "bytes": None,
            },
            {
                "system": "DWS",
                "category": "Serving",
                "name": "dockone_golden.table_metrics",
                "format": "DWS table - latest load summary",
                "rows": fallback_summary.get("rows"),
                "objects": None,
                "bytes": None,
            },
            {
                "system": "DWS",
                "category": "View",
                "name": "dockone_golden.table_metrics_bi",
                "format": "DWS view - latest DataArts publish",
                "rows": fallback_summary.get("rows"),
                "objects": None,
                "bytes": None,
            },
        ]
        try:
            if time.time() < self.dws_sql_disabled_until:
                raise RuntimeError(self.dws_sql_last_error or "DWS SQL collector is cooling down")
            tables = self.collect_dws_tables()
        except Exception as exc:
            tables = fallback_tables
            sql_error = str(exc)
            if "locked" in sql_error.lower() or "username/password" in sql_error.lower():
                self.dws_sql_last_error = sql_error
                self.dws_sql_disabled_until = time.time() + 900
        if not tables:
            tables = fallback_tables
        return {
            "status": "healthy"
            if cluster.get("status") == "AVAILABLE"
            else "warning",
            "name": cluster.get("name"),
            "spec": (
                f"{cluster.get('node_type')} · {cluster.get('number_of_node')} nodes · "
                f"DWS {cluster.get('version')}"
            ),
            "state": cluster.get("status"),
            "port": cluster.get("port"),
            "nodes": cluster.get("nodes") or [],
            "tables": tables,
            "table_query_error": sql_error,
            "updated_at": utc_now(),
        }

    def signed_get(self, host, path):
        request = SdkRequest(
            method="GET",
            schema="https",
            host=host,
            resource_path=path,
            query_params=[],
            header_params={"Content-Type": "application/json"},
            body=None,
        )
        signed = Signer(self.credentials).sign(request)
        response = requests.get(
            f"https://{host}{signed.uri}",
            headers=signed.header_params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def rds_validation(self):
        rows = self.list_obs("validation/iceberg-to-rds/latest/")
        json_item = next((item for item in rows if item["key"].endswith(".json")), None)
        if not json_item:
            return {}
        result = self.obs.getObject(BUCKET, json_item["key"], loadStreamInMemory=True)
        if result.status >= 300:
            return {}
        payload = json.loads(result.body.buffer.decode("utf-8"))
        payload["object_modified"] = json_item.get("modified")
        return payload

    def collect_rds(self):
        host = f"rds.{REGION}.myhuaweicloud.com"
        response = self.signed_get(host, f"/v3/{PROJECT_ID}/instances")
        instance = next(
            (item for item in response.get("instances") or [] if item.get("id") == RDS_ID),
            {},
        )
        validation = self.rds_validation()
        tables = [
            {
                "system": "RDS PostgreSQL",
                "category": "Relational target",
                "name": item.get("target_table"),
                "format": "PostgreSQL table",
                "rows": item.get("target_count"),
                "objects": None,
                "bytes": None,
            }
            for item in validation.get("tables") or []
        ]
        volume = instance.get("volume") or {}
        flavor = instance.get("flavor_ref") or instance.get("flavor_ref")
        return {
            "status": "healthy"
            if str(instance.get("status")).upper() == "ACTIVE"
            else "warning",
            "name": instance.get("name") or "dockone-iceberg-v1-rds-pg",
            "spec": (
                f"PostgreSQL {(instance.get('datastore') or {}).get('version', '16')} · "
                f"{flavor or 'rds.pg.n1.large.2'} · {volume.get('size', 40)} GB"
            ),
            "state": instance.get("status"),
            "private_ip": (instance.get("private_ips") or ["192.168.5.1"])[0],
            "port": instance.get("port", 5432),
            "tables": tables,
            "validation": validation,
            "note": "Table metrics use the latest MRS JDBC write/read-back validation because RDS is private-only.",
            "updated_at": utc_now(),
        }

    def stage_progress(self, services, history):
        progress = {"obs": 0, "mrs": 0, "dataarts": 0, "dws": 0}
        if services.get("obs", {}).get("bytes", 0) > 0:
            progress["obs"] = 100

        def latest(source, name=None):
            for item in history:
                if item.get("source") != source:
                    continue
                if name and item.get("name") != name:
                    continue
                return item
            return {}

        def state(item):
            return str(item.get("status") or "").lower()

        mrs_job = latest("MRS")
        if mrs_job:
            mrs_state = state(mrs_job)
            mrs_value = clamp_value(mrs_job.get("progress"))
            if mrs_state in {"success", "succeeded", "finished"}:
                progress["mrs"] = 100
            elif mrs_state in {"failed", "failure", "killed", "error"}:
                progress["mrs"] = mrs_value
            else:
                progress["mrs"] = max(1, mrs_value)

        golden_job = latest("DataArts", "dockone_golden_to_dws")
        if golden_job:
            dataarts_state = state(golden_job)
            if dataarts_state in {"success", "failed", "failure", "error"}:
                progress["dataarts"] = 100
            else:
                progress["dataarts"] = 35

            if dataarts_state == "success":
                progress["dws"] = 100
            elif dataarts_state in {"running", "submitted"}:
                progress["dws"] = 35
            elif dataarts_state in {"failed", "failure", "error"}:
                progress["dws"] = 20

        if not golden_job and services.get("dws", {}).get("table_query_error"):
            progress["dws"] = 20

        return progress

    def collect(self):
        tasks = {
            "obs": self.collect_obs,
            "mrs": self.collect_mrs,
            "dataarts": self.collect_dataarts,
            "dws": self.collect_dws,
        }
        services = {}
        errors = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(func): key for key, func in tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    services[key] = future.result()
                except Exception as exc:
                    services[key] = {
                        "status": "unavailable",
                        "name": key.upper(),
                        "spec": "Live API unavailable",
                        "error": str(exc),
                        "updated_at": utc_now(),
                    }
                    errors.append({"service": key, "message": str(exc)})

        tables = []
        for key in ("obs", "dws"):
            tables.extend(services.get(key, {}).get("tables") or [])
        history = (
            (services.get("mrs", {}).get("history") or [])
            + (services.get("dataarts", {}).get("history") or [])
        )
        history.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        stage_order = ["obs", "mrs", "dataarts", "dws"]
        stage_progress = self.stage_progress(services, history)
        completed = sum(
            services.get(key, {}).get("status") in {"healthy", "idle"}
            for key in stage_order
        )
        return {
            "generated_at": utc_now(),
            "refresh_seconds": REFRESH_SECONDS,
            "region": REGION,
            "pipeline": stage_order,
            "stage_progress": stage_progress,
            "summary": {
                "healthy_services": completed,
                "total_services": len(stage_order),
                "table_count": len(tables),
                "history_count": len(history),
                "obs_bytes": services.get("obs", {}).get("bytes", 0),
                "mrs_progress": stage_progress.get("mrs", 0),
            },
            "services": services,
            "tables": tables,
            "history": history[:40],
            "errors": errors,
        }


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.payload = {
            "generated_at": utc_now(),
            "refresh_seconds": REFRESH_SECONDS,
            "loading": True,
            "services": {},
            "tables": [],
            "history": [],
            "errors": [],
        }
        self.collector = MonitorCollector()
        self.refresh_requested = threading.Event()

    def update(self):
        try:
            payload = self.collector.collect()
            payload["loading"] = False
        except Exception as exc:
            payload = dict(self.payload)
            payload["generated_at"] = utc_now()
            payload["loading"] = False
            payload["errors"] = [{"service": "collector", "message": str(exc)}]
        with self.lock:
            self.payload = payload

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.payload, default=str))

    def loop(self):
        while True:
            started = time.time()
            self.update()
            remaining = max(0.1, REFRESH_SECONDS - (time.time() - started))
            self.refresh_requested.wait(remaining)
            self.refresh_requested.clear()


STATE = State()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json(200, {"ok": True, "time": utc_now()})
            return
        if path == "/api/status":
            self.send_json(200, STATE.snapshot())
            return
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/refresh":
            self.send_json(404, {"error": "not found"})
            return
        STATE.refresh_requested.set()
        self.send_json(202, {"accepted": True})


def main():
    thread = threading.Thread(target=STATE.loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer(("127.0.0.1", 8787), Handler)
    print("DockOne realtime monitor: http://127.0.0.1:8787")
    server.serve_forever()


if __name__ == "__main__":
    main()
