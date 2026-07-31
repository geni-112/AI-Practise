from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest
from prometheus_client import CollectorRegistry, Gauge, generate_latest

REGION = os.environ["HUAWEICLOUD_REGION"]
PROJECT = os.environ["HUAWEICLOUD_PROJECT_ID"]
AK = os.environ.get("HUAWEICLOUD_ACCESS_KEY", "")
SK = os.environ.get("HUAWEICLOUD_SECRET_KEY", "")
USE_METADATA = os.environ.get("HUAWEICLOUD_METADATA_AUTH", "").lower() in {"1", "true", "yes"}
INTERVAL = int(os.environ.get("COLLECT_INTERVAL_SECONDS", "60"))
MAX_CES_METRICS = int(os.environ.get("MAX_CES_METRICS", "450"))
MAX_MRS_JOBS = int(os.environ.get("MAX_MRS_JOBS", "2000"))
MRS_CLUSTER_ID = os.environ.get("MRS_CLUSTER_ID", "")
MRS_CLUSTER_NAME = os.environ.get("MRS_CLUSTER_NAME", "")
CREDS_LOCK = threading.Lock()
CREDS: BasicCredentials | None = None
CREDS_REFRESH_AT = 0.0

LOCK = threading.Lock()
LATEST = b""
LAST_ERROR = ""
TRACKING_LINKS_LOCK = threading.Lock()
TRACKING_LINKS: dict[str, str] = {}

PRIORITY_NAMESPACES = {
    "SYS.ECS",
    "AGT.ECS",
    "SYS.EVS",
    "SYS.VPC",
    "SYS.OBS",
    "SYS.RDS",
    "SYS.CDM",
    "SYS.DMS",
    "SYS.ELB",
}
PRIORITY_METRICS = re.compile(
    r"(cpu|mem|memory|disk|iops|read|write|network|bandwidth|connection|capacity|"
    r"request|latency|delay|throughput|usage|util|error|failed|status|queue)",
    re.I,
)
SENSITIVE_PARAMETER = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|access[._-]?key|"
    r"secret[._-]?key|client[._-]?secret|private[._-]?key)"
    r"(\s*[=:]\s*)([^,\s\]\}]+)"
)
SENSITIVE_NEXT_ARGUMENT = re.compile(
    r"(?i)(--?(?:password|passwd|pwd|secret|token|access[._-]?key|"
    r"secret[._-]?key|client[._-]?secret|private[._-]?key)"
    r"\s*[, ]+\s*)([^,\s\]\}]+)"
)
SENSITIVE_JSON_PARAMETER = re.compile(
    r"""(?i)(["'](?:password|passwd|pwd|secret|token|access[._-]?key|"""
    r"""secret[._-]?key|client[._-]?secret|private[._-]?key)["']"""
    r"""\s*:\s*["'])(.*?)(["'])"""
)


def endpoint(service: str) -> str:
    if service == "dataarts":
        return f"https://dayu.{REGION}.myhuaweicloud.com"
    return f"https://{service}.{REGION}.myhuaweicloud.com"


def register_tracking_link(target: str, links: dict[str, str]) -> str:
    if not target:
        return ""
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    token = hashlib.sha256(target.encode()).hexdigest()[:32]
    links[token] = target
    return f"/mrs-log/{token}"


def credentials() -> BasicCredentials:
    global CREDS, CREDS_REFRESH_AT
    with CREDS_LOCK:
        if CREDS is not None and time.time() < CREDS_REFRESH_AT:
            return CREDS
        if USE_METADATA:
            with urllib.request.urlopen(
                "http://169.254.169.254/openstack/latest/securitykey", timeout=5
            ) as response:
                payload = json.loads(response.read())
            item = payload.get("credential", payload)
            access = item.get("access", "")
            secret = item.get("secret", "")
            token = item.get("securitytoken", "")
            if not (access and secret and token):
                raise RuntimeError("ECS metadata did not return temporary agency credentials.")
            CREDS = BasicCredentials(access, secret, PROJECT).with_security_token(token)
            CREDS_REFRESH_AT = time.time() + 300
        else:
            if not (AK and SK):
                raise RuntimeError("Huawei AK/SK is missing and metadata authentication is disabled.")
            CREDS = BasicCredentials(AK, SK, PROJECT)
            CREDS_REFRESH_AT = time.time() + 3600
        return CREDS


def signed_json(
    method: str, url: str, body: Any | None = None, headers: dict[str, str] | None = None
) -> Any:
    raw = json.dumps(body).encode() if body is not None else None
    parts = urllib.parse.urlsplit(url)
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    sdk_request = SdkRequest(
        method=method,
        schema=parts.scheme,
        host=parts.netloc,
        resource_path=parts.path or "/",
        query_params=urllib.parse.parse_qsl(parts.query, keep_blank_values=True),
        header_params=request_headers,
        body=raw or b"",
    )
    signed = credentials().sign_request(sdk_request)
    req = urllib.request.Request(
        url, data=raw, headers=dict(signed.header_params), method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"{method} {parts.path}: HTTP {exc.code}: {detail}") from exc


def list_ces_metrics() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    marker = ""
    for _ in range(20):
        query = {"limit": "1000"}
        if marker:
            query["start"] = marker
        url = (
            f"{endpoint('ces')}/V1.0/{PROJECT}/metrics?"
            + urllib.parse.urlencode(query)
        )
        payload = signed_json("GET", url)
        page = payload.get("metrics", [])
        rows.extend(page)
        marker = (
            payload.get("meta_data", {}).get("marker")
            or payload.get("marker")
            or ""
        )
        if not marker or len(page) < 1000:
            break
    preferred = [
        item
        for item in rows
        if item.get("namespace") in PRIORITY_NAMESPACES
        and PRIORITY_METRICS.search(item.get("metric_name", ""))
    ]
    preferred.sort(
        key=lambda item: (
            item.get("namespace", ""),
            item.get("metric_name", ""),
            json.dumps(item.get("dimensions", []), sort_keys=True),
        )
    )
    return preferred[:MAX_CES_METRICS]


def query_ces(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not metrics:
        return []
    now_ms = int(time.time() * 1000)
    body = {
        "from": now_ms - 600_000,
        "to": now_ms,
        "period": "300",
        "filter": "average",
        "metrics": [
            {
                "namespace": item["namespace"],
                "metric_name": item["metric_name"],
                "dimensions": item.get("dimensions", []),
            }
            for item in metrics
        ],
    }
    payload = signed_json(
        "POST",
        f"{endpoint('ces')}/V1.0/{PROJECT}/batch-query-metric-data",
        body,
    )
    return payload.get("metrics", [])


def list_mrs_clusters() -> list[dict[str, Any]]:
    payload = signed_json(
        "GET", f"{endpoint('mrs')}/v1.1/{PROJECT}/cluster_infos?pageSize=100"
    )
    return payload.get("clusters", []) or payload.get("cluster_infos", [])


def list_mrs_jobs(cluster_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while len(rows) < MAX_MRS_JOBS:
        payload = signed_json(
            "GET",
            f"{endpoint('mrs')}/v2/{PROJECT}/clusters/{cluster_id}/"
            f"job-executions?limit=100&offset={page}",
        )
        current: list[dict[str, Any]] = []
        for key in ("job_list", "jobs", "job_exes", "job_executions", "data"):
            if isinstance(payload.get(key), list):
                current = payload[key]
                break
        rows.extend(current)
        try:
            total = int(payload.get("total_record", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        if not current or len(current) < 100 or (total and len(rows) >= total):
            break
        page += 1
    return rows[:MAX_MRS_JOBS]


def list_mrs_nodes(cluster_id: str) -> list[dict[str, Any]]:
    candidates = [
        f"{endpoint('mrs')}/v2/{PROJECT}/clusters/{cluster_id}/nodes?limit=500",
        f"{endpoint('mrs')}/v1.1/{PROJECT}/clusters/{cluster_id}/hosts",
    ]
    for url in candidates:
        try:
            payload = signed_json("GET", url)
            for key in ("nodes", "hosts", "instances"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        except Exception:
            continue
    return []


def list_dataarts_jobs() -> list[dict[str, Any]]:
    urls = [
        f"{endpoint('dataarts')}/v1/{PROJECT}/jobs?limit=100&offset=0",
        f"https://dayu-dlf.{REGION}.myhuaweicloud.com/v1/{PROJECT}/jobs?limit=100&offset=0",
    ]
    for url in urls:
        try:
            payload = signed_json("GET", url)
            for key in ("jobs", "job_list", "data"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        except Exception:
            continue
    return []


def first(item: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return default


def safe_text(value: Any, limit: int = 2048) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value or "")
    text = SENSITIVE_JSON_PARAMETER.sub(r"\1***\3", text)
    text = SENSITIVE_PARAMETER.sub(r"\1\2***", text)
    text = SENSITIVE_NEXT_ARGUMENT.sub(r"\1***", text)
    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def seconds(value: Any) -> float:
    try:
        result = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return result / 1000 if result > 10**12 else result


def state_value(state: str) -> float:
    return 1.0 if state.lower() in {"running", "active", "success", "succeeded", "finished", "completed"} else 0.0


def build_metrics() -> bytes:
    tracking_links: dict[str, str] = {}
    registry = CollectorRegistry()
    cloud_eye = Gauge(
        "huawei_cloud_eye_value",
        "Latest Cloud Eye metric value",
        ["namespace", "metric_name", "resource", "dimensions", "unit"],
        registry=registry,
    )
    cluster_state = Gauge(
        "huawei_mrs_cluster_state",
        "MRS cluster state (1 healthy/running)",
        ["cluster_id", "cluster_name", "state", "version"],
        registry=registry,
    )
    node_state = Gauge(
        "huawei_mrs_node_state",
        "MRS node state (1 healthy/running)",
        ["cluster_id", "node_id", "node_name", "node_group", "node_type", "state"],
        registry=registry,
    )
    job_state = Gauge(
        "huawei_mrs_job_state",
        "MRS job state (1 successful/running)",
        ["cluster_id", "cluster_name", "job_id", "job_name", "job_type", "state"],
        registry=registry,
    )
    job_duration = Gauge(
        "huawei_mrs_job_duration_seconds",
        "MRS job duration",
        ["cluster_id", "job_id", "job_name", "state"],
        registry=registry,
    )
    job_execution = Gauge(
        "huawei_mrs_job_execution_info",
        "MRS job execution traceability metadata (sensitive parameters are masked)",
        [
            "cluster_id",
            "cluster_name",
            "job_id",
            "job_name",
            "job_type",
            "job_state",
            "job_result",
            "user",
            "queue",
            "launcher_id",
            "app_id",
            "tracking_url",
            "log_status",
            "arguments",
            "properties",
            "submitted_at",
            "started_at",
            "finished_at",
            "assigned_node",
            "executor_nodes",
            "node_source",
        ],
        registry=registry,
    )
    job_progress = Gauge(
        "huawei_mrs_job_progress_percent",
        "MRS job execution progress",
        ["cluster_id", "job_id", "job_name", "job_result", "user"],
        registry=registry,
    )
    job_event_time = Gauge(
        "huawei_mrs_job_event_timestamp_seconds",
        "MRS job submitted, started, or finished timestamp",
        ["cluster_id", "job_id", "job_name", "event"],
        registry=registry,
    )
    job_log_available = Gauge(
        "huawei_mrs_job_log_link_available",
        "Whether the MRS job exposes a tracking/log URL",
        ["cluster_id", "job_id", "job_name", "job_result"],
        registry=registry,
    )
    job_history_total = Gauge(
        "huawei_mrs_job_history_total",
        "Number of MRS job executions returned by the configured history window",
        ["cluster_id", "cluster_name"],
        registry=registry,
    )
    dataarts_job = Gauge(
        "huawei_dataarts_job_info",
        "DataArts job definition information",
        ["job_id", "job_name", "job_type", "status", "schedule_type"],
        registry=registry,
    )
    exporter_ok = Gauge(
        "huawei_exporter_collection_success",
        "Whether the last Huawei collection succeeded",
        registry=registry,
    )
    exporter_ts = Gauge(
        "huawei_exporter_last_collection_timestamp_seconds",
        "Last Huawei collection timestamp",
        registry=registry,
    )

    discovered = list_ces_metrics()
    for item in query_ces(discovered):
        points = item.get("datapoints", [])
        if not points:
            continue
        point = max(points, key=lambda value: value.get("timestamp", 0))
        value = point.get("average")
        if value is None:
            for key in ("max", "min", "sum"):
                if point.get(key) is not None:
                    value = point[key]
                    break
        if value is None:
            continue
        dims = item.get("dimensions", [])
        resource = "|".join(str(d.get("value", "")) for d in dims)
        dim_text = ",".join(
            f"{d.get('name','')}={d.get('value','')}" for d in dims
        )
        cloud_eye.labels(
            item.get("namespace", ""),
            item.get("metric_name", ""),
            resource,
            dim_text,
            item.get("unit", ""),
        ).set(float(value))

    clusters = list_mrs_clusters()
    target_clusters = [
        c
        for c in clusters
        if (not MRS_CLUSTER_ID or first(c, "clusterId", "cluster_id") == MRS_CLUSTER_ID)
    ]
    for cluster in target_clusters:
        cid = str(first(cluster, "clusterId", "cluster_id", "id"))
        cname = str(first(cluster, "clusterName", "cluster_name", "name"))
        state = str(first(cluster, "clusterState", "cluster_state", "status", "state"))
        version = str(first(cluster, "clusterVersion", "cluster_version", "version"))
        cluster_state.labels(cid, cname, state, version).set(state_value(state))
        for node in list_mrs_nodes(cid):
            nid = str(first(node, "id", "node_id", "server_id", "instance_id"))
            nname = str(first(node, "name", "node_name", "server_name", default=nid))
            ngroup = str(first(node, "node_group", "node_group_name", "group_name"))
            ntype = str(first(node, "node_type", "type"))
            nstate = str(first(node, "status", "state", "node_status"))
            node_state.labels(cid, nid, nname, ngroup, ntype, nstate).set(
                state_value(nstate)
            )
        jobs = list_mrs_jobs(cid)
        job_history_total.labels(cid, cname).set(len(jobs))
        for job in jobs:
            jid = str(first(job, "id", "job_id", "jobId", "job_execution_id"))
            jname = str(first(job, "name", "job_name", "jobName", default=jid))
            jtype = str(first(job, "type", "job_type", "jobType"))
            jstate = str(first(job, "status", "state", "job_state"))
            jresult = str(first(job, "job_result", "result"))
            user = str(first(job, "user", "username", "created_by", "owner"))
            queue = str(first(job, "queue", default="default"))
            launcher_id = str(first(job, "launcher_id", "launcherId"))
            app_id = str(first(job, "app_id", "application_id", "appId"))
            tracking_target = safe_text(first(job, "tracking_url", "trackingUrl"), 1024)
            tracking_url = register_tracking_link(tracking_target, tracking_links)
            arguments = safe_text(first(job, "arguments", "args"))
            properties = safe_text(first(job, "properties", "configs"))
            assigned_node = str(
                first(
                    job,
                    "am_host",
                    "application_master_host",
                    "driver_host",
                    "assigned_node",
                )
            )
            executor_nodes = safe_text(
                first(job, "executor_nodes", "executor_hosts"), 1024
            )
            node_source = (
                "mrs-api"
                if assigned_node or executor_nodes
                else "unavailable_pending_yarn_or_fusioninsight"
            )
            submitted = seconds(first(job, "submitted_time", "submit_time"))
            started = seconds(first(job, "started_time", "start_time", "startTime"))
            finished = seconds(first(job, "finished_time", "end_time", "endTime"))
            job_state.labels(cid, cname, jid, jname, jtype, jstate).set(
                state_value(jstate)
            )
            job_execution.labels(
                cid,
                cname,
                jid,
                jname,
                jtype,
                jstate,
                jresult,
                user,
                queue,
                launcher_id,
                app_id,
                tracking_url,
                "available" if tracking_url else "not_available",
                arguments,
                properties,
                time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(submitted))
                if submitted
                else "",
                time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(started))
                if started
                else "",
                time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(finished))
                if finished
                else "",
                assigned_node,
                executor_nodes,
                node_source,
            ).set(1)
            try:
                progress = float(first(job, "job_progress", "progress", default=0))
            except (TypeError, ValueError):
                progress = 0
            job_progress.labels(cid, jid, jname, jresult, user).set(progress)
            job_log_available.labels(cid, jid, jname, jresult).set(
                1 if tracking_url else 0
            )
            for event, timestamp in (
                ("submitted", submitted),
                ("started", started),
                ("finished", finished),
            ):
                if timestamp:
                    job_event_time.labels(cid, jid, jname, event).set(timestamp)
            if finished >= started > 0:
                job_duration.labels(cid, jid, jname, jstate).set(finished - started)

    for job in list_dataarts_jobs():
        dataarts_job.labels(
            str(first(job, "id", "job_id")),
            str(first(job, "name", "job_name")),
            str(first(job, "type", "job_type")),
            str(first(job, "status", "state")),
            str(first(job, "schedule_type", "scheduleType")),
        ).set(1)

    with TRACKING_LINKS_LOCK:
        TRACKING_LINKS.clear()
        TRACKING_LINKS.update(tracking_links)
    exporter_ok.set(1)
    exporter_ts.set(time.time())
    return generate_latest(registry)


def collect_loop() -> None:
    global LATEST, LAST_ERROR
    while True:
        try:
            rendered = build_metrics()
            with LOCK:
                LATEST = rendered
                LAST_ERROR = ""
        except Exception as exc:
            with LOCK:
                LAST_ERROR = str(exc)
        time.sleep(INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        request_path = urllib.parse.urlsplit(self.path).path
        with LOCK:
            payload = LATEST
            error = LAST_ERROR
        if request_path.startswith("/mrs-log/"):
            token = request_path.removeprefix("/mrs-log/")
            with TRACKING_LINKS_LOCK:
                target = TRACKING_LINKS.get(token, "")
            if not re.fullmatch(r"[a-f0-9]{32}", token) or not target:
                body = b"log link expired or unavailable\n"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            else:
                escaped_target = html.escape(target, quote=True)
                script_target = (
                    json.dumps(target)
                    .replace("<", "\\u003c")
                    .replace(">", "\\u003e")
                    .replace("&", "\\u0026")
                )
                body = (
                    "<!doctype html><html><head>"
                    '<meta charset="utf-8">'
                    '<meta name="referrer" content="no-referrer">'
                    '<meta http-equiv="refresh" content="0;url='
                    + escaped_target
                    + '">'
                    "<title>Opening MRS log</title></head><body>"
                    "<p>Opening the authenticated MRS/YARN log page...</p>"
                    '<p><a rel="noreferrer noopener" href="'
                    + escaped_target
                    + '">Continue to the log</a></p>'
                    "<script>window.location.replace("
                    + script_target
                    + ");</script></body></html>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; script-src 'unsafe-inline'; "
                    "base-uri 'none'; frame-ancestors 'none'",
                )
        elif request_path == "/health":
            body = json.dumps({"ok": bool(payload) and not error, "error": error}).encode()
            self.send_response(200 if payload and not error else 503)
            self.send_header("Content-Type", "application/json")
        elif request_path == "/metrics":
            body = payload or b"# Huawei metrics collection is starting\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


if __name__ == "__main__":
    threading.Thread(target=collect_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9108), Handler).serve_forever()
