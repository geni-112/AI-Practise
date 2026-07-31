from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from bisect import bisect_left
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.sdk_request import SdkRequest
from obs import ObsClient
from prometheus_client import CollectorRegistry, Gauge, generate_latest

REGION = os.environ["HUAWEICLOUD_REGION"]
PROJECT = os.environ["HUAWEICLOUD_PROJECT_ID"]
AK = os.environ["HUAWEICLOUD_ACCESS_KEY"]
SK = os.environ["HUAWEICLOUD_SECRET_KEY"]
LOKI_PUSH_URL = os.environ.get(
    "LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push"
)
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL_SECONDS", "600"))
HISTORY_DAYS = int(os.environ.get("DATAARTS_HISTORY_DAYS", "180"))
MAX_LOG_OBJECTS = int(os.environ.get("MAX_DATAARTS_LOG_OBJECTS", "20000"))
MAX_LOG_FILE_BYTES = int(
    os.environ.get("MAX_DATAARTS_LOG_FILE_BYTES", str(10 * 1024 * 1024))
)
STATE_PATH = Path(os.environ.get("STATE_PATH", "/state/dataarts-log-state.json"))
INGESTION_VERSION = os.environ.get("DATAARTS_LOG_INGESTION_VERSION", "2")
LOG_TIMEZONE_OFFSET_HOURS = int(
    os.environ.get("DATAARTS_LOG_TIMEZONE_OFFSET_HOURS", "0")
)
LOG_TIMEZONE = timezone(timedelta(hours=LOG_TIMEZONE_OFFSET_HOURS))
INSTANCE_MATCH_WINDOW_MS = (
    int(os.environ.get("DATAARTS_INSTANCE_MATCH_WINDOW_SECONDS", "1200"))
    * 1000
)
DOWNLOAD_WORKERS = int(os.environ.get("DATAARTS_LOG_DOWNLOAD_WORKERS", "8"))
LOG_SUFFIXES = {".job", ".log"}
TERMINAL_STATES = {
    "success",
    "forcesuccess",
    "ignoresuccess",
    "fail",
    "running-exception",
    "manual-stop",
}

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

LOCK = threading.Lock()
LATEST = b""
LAST_ERROR = ""
CREDS = BasicCredentials(AK, SK, PROJECT)


def signed_json(
    method: str,
    url: str,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
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
    signed = CREDS.sign_request(sdk_request)
    request = urllib.request.Request(
        url, data=raw, headers=dict(signed.header_params), method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(
            f"{method} {parts.path}: HTTP {exc.code}: {detail}"
        ) from exc


def dataarts_endpoint() -> str:
    return f"https://dayu-dlf.{REGION}.myhuaweicloud.com"


def first(item: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return default


def safe_text(value: Any, limit: int = 4096) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value or "")
    for secret in (AK, SK):
        if secret:
            text = text.replace(secret, "***")
    text = SENSITIVE_JSON_PARAMETER.sub(r"\1***\3", text)
    text = SENSITIVE_PARAMETER.sub(r"\1\2***", text)
    text = SENSITIVE_NEXT_ARGUMENT.sub(r"\1***", text)
    text = text.replace("\x00", "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def list_jobs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = signed_json(
            "GET",
            f"{dataarts_endpoint()}/v1/{PROJECT}/jobs?"
            + urllib.parse.urlencode(
                {"limit": 1000, "offset": offset, "jobType": "BATCH"}
            ),
        )
        current = payload.get("jobs", []) or []
        rows.extend(current)
        total = int(payload.get("total", 0) or 0)
        if not current or len(current) < 1000 or (total and len(rows) >= total):
            return rows
        offset += 1


def list_job_details(
    jobs: list[dict[str, Any]],
) -> tuple[list[tuple[str, str]], dict[str, dict[str, str]]]:
    roots: set[tuple[str, str]] = set()
    definitions: dict[str, dict[str, str]] = {}
    for job in jobs:
        name = str(first(job, "name", "job_name"))
        if not name:
            continue
        owner = safe_text(first(job, "owner"), 256)
        created_by = safe_text(first(job, "createUser", "create_user"), 256)
        definition = {
            "job_name": name,
            "job_type": str(first(job, "jobType", "job_type")),
            "status": str(first(job, "status", "state")),
            "owner": owner,
            "created_by": created_by,
            "parameters": "",
            "log_root": "",
        }
        try:
            encoded_name = urllib.parse.quote(name, safe="")
            detail = signed_json(
                "GET",
                f"{dataarts_endpoint()}/v1/{PROJECT}/jobs/{encoded_name}",
            )
            definition["parameters"] = safe_text(detail.get("params", []))
            log_root = str(detail.get("logPath", "") or "")
            definition["log_root"] = safe_text(log_root, 1024)
            if log_root.startswith("obs://"):
                remainder = log_root[6:]
                bucket, _, prefix = remainder.partition("/")
                if bucket:
                    roots.add((bucket, prefix))
        except Exception:
            pass
        definitions[name] = definition
    return sorted(roots), definitions


def list_instances() -> list[dict[str, Any]]:
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - HISTORY_DAYS * 86_400_000
    result: dict[str, dict[str, Any]] = {}
    window_end = now_ms
    while window_end >= cutoff_ms:
        window_start = max(cutoff_ms, window_end - 7 * 86_400_000 + 1)
        offset = 0
        while True:
            query = urllib.parse.urlencode(
                {
                    "minPlanTime": window_start,
                    "maxPlanTime": window_end,
                    "limit": 1000,
                    "offset": offset,
                }
            )
            payload = signed_json(
                "GET",
                f"{dataarts_endpoint()}/v1/{PROJECT}/jobs/instances/detail?"
                f"{query}",
            )
            current = payload.get("instances", []) or []
            for row in current:
                instance_id = str(row.get("instanceId", "") or "")
                if instance_id:
                    result[instance_id] = row
            total = int(payload.get("total", 0) or 0)
            if not current or len(current) < 1000 or (total and (offset + 1) * 1000 >= total):
                break
            offset += 1
        window_end = window_start - 1
    return list(result.values())


def index_instances(
    instances: list[dict[str, Any]], definitions: dict[str, dict[str, str]]
) -> dict[str, list[tuple[int, dict[str, str]]]]:
    index: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for row in instances:
        job_name = str(row.get("jobName", "") or "")
        definition = definitions.get(job_name, {})
        item = {
            "instance_id": str(row.get("instanceId", "") or ""),
            "status": str(row.get("status", "") or ""),
            "executed_by": definition.get("owner")
            or definition.get("created_by")
            or "",
        }
        for field in ("planTime", "startTime", "submitTime"):
            try:
                millis = int(row.get(field) or 0)
            except (TypeError, ValueError):
                millis = 0
            if millis:
                index[job_name].append((millis, item))
    for values in index.values():
        values.sort(key=lambda entry: entry[0])
    return index


def execution_timestamp_ms(execution_time: str) -> int:
    try:
        dt = datetime.strptime(
            execution_time, "%Y-%m-%d_%H_%M_%S.%f"
        ).replace(tzinfo=LOG_TIMEZONE)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


def nearest_instance(
    instance_index: dict[str, list[tuple[int, dict[str, str]]]],
    job_name: str,
    execution_time: str,
) -> dict[str, str]:
    target = execution_timestamp_ms(execution_time)
    candidates = instance_index.get(job_name, [])
    if not target or not candidates:
        return {}
    timestamps = [entry[0] for entry in candidates]
    position = bisect_left(timestamps, target)
    nearby = [
        candidates[index]
        for index in (position - 1, position, position + 1)
        if 0 <= index < len(candidates)
    ]
    if not nearby:
        return {}
    timestamp, item = min(nearby, key=lambda entry: abs(entry[0] - target))
    return item if abs(timestamp - target) <= INSTANCE_MATCH_WINDOW_MS else {}


def list_log_objects(
    obs: ObsClient, roots: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    objects: dict[tuple[str, str], dict[str, Any]] = {}
    for bucket, prefix in roots:
        marker: str | None = None
        while len(objects) < MAX_LOG_OBJECTS:
            response = obs.listObjects(
                bucket,
                prefix=prefix,
                marker=marker,
                max_keys=min(1000, MAX_LOG_OBJECTS - len(objects)),
            )
            if int(response.status or 500) >= 300:
                raise RuntimeError(
                    f"OBS list failed for configured DataArts log root: "
                    f"HTTP {response.status}"
                )
            contents = getattr(response.body, "contents", []) or []
            for item in contents:
                key = str(getattr(item, "key", "") or "")
                suffix = PurePosixPath(key).suffix.lower()
                size = int(getattr(item, "size", 0) or 0)
                if suffix not in LOG_SUFFIXES or size <= 0:
                    continue
                objects[(bucket, key)] = {
                    "bucket": bucket,
                    "key": key,
                    "size": size,
                    "etag": str(getattr(item, "etag", "") or ""),
                    "last_modified": str(
                        getattr(item, "lastModified", "") or ""
                    ),
                }
                if len(objects) >= MAX_LOG_OBJECTS:
                    break
            if (
                len(objects) >= MAX_LOG_OBJECTS
                or not getattr(response.body, "is_truncated", False)
            ):
                break
            marker = getattr(response.body, "next_marker", None)
            if not marker and contents:
                marker = str(getattr(contents[-1], "key", "") or "")
            if not marker:
                break
    return sorted(objects.values(), key=lambda item: (item["bucket"], item["key"]))


def parse_log_identity(
    item: dict[str, Any],
    instance_index: dict[str, list[tuple[int, dict[str, str]]]],
    definitions: dict[str, dict[str, str]],
) -> dict[str, str]:
    parts = [part for part in str(item["key"]).split("/") if part]
    start = 1 if parts and parts[0] == PROJECT else 0
    job_name = parts[start] if len(parts) > start else "unknown"
    execution_time = parts[start + 1] if len(parts) > start + 1 else ""
    node_name = parts[start + 2] if len(parts) > start + 2 else ""
    filename = parts[-1] if parts else ""
    instance = nearest_instance(
        instance_index, job_name, execution_time
    )
    definition = definitions.get(job_name, {})
    return {
        "job_name": safe_text(job_name, 256),
        "execution_time": safe_text(execution_time, 64),
        "node_name": safe_text(node_name, 256),
        "file_type": PurePosixPath(filename).suffix.lower().lstrip("."),
        "filename": safe_text(filename, 256),
        "status": safe_text(instance.get("status", "unknown"), 64),
        "instance_id": safe_text(instance.get("instance_id", ""), 64),
        "executed_by": safe_text(
            instance.get("executed_by")
            or definition.get("owner")
            or definition.get("created_by")
            or "",
            256,
        ),
        "log_path": safe_text(f"obs://{item['bucket']}/{item['key']}", 2048),
    }


def load_state() -> dict[str, Any]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("objects"), dict):
            return payload
    except Exception:
        pass
    return {"objects": {}, "lines_ingested": 0}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def object_signature(item: dict[str, Any]) -> str:
    material = "|".join(
        [
            INGESTION_VERSION,
            str(item.get("etag", "")),
            str(item.get("size", "")),
            str(item.get("last_modified", "")),
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()


def parse_base_timestamp(execution_time: str, last_modified: str) -> int:
    try:
        dt = datetime.strptime(
            execution_time, "%Y-%m-%d_%H_%M_%S.%f"
        ).replace(tzinfo=LOG_TIMEZONE)
        return int(dt.timestamp() * 1_000_000_000)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(
            last_modified, "%Y/%m/%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except ValueError:
        return time.time_ns()


def download_log(
    obs: ObsClient, item: dict[str, Any], identity: dict[str, str]
) -> tuple[dict[str, str], list[list[str]]]:
    if int(item["size"]) > MAX_LOG_FILE_BYTES:
        raise RuntimeError(
            f"DataArts log object exceeds configured safety limit: "
            f"{item['size']} bytes"
        )
    response = obs.getObject(
        item["bucket"], item["key"], loadStreamInMemory=True
    )
    if int(response.status or 500) >= 300:
        raise RuntimeError(
            f"OBS log read failed: HTTP {response.status}"
        )
    body = getattr(response, "body", None)
    raw = getattr(body, "buffer", b"") if body else b""
    if isinstance(raw, str):
        text = raw
    else:
        text = bytes(raw or b"").decode("utf-8", errors="replace")
    lines = text.splitlines() or [""]
    base = parse_base_timestamp(
        identity["execution_time"], str(item.get("last_modified", ""))
    )
    values = [
        [str(base + index), safe_text(line, 65_536)]
        for index, line in enumerate(lines)
    ]
    labels = {
        "source": "dataarts",
        "service": "DataArts_Factory",
        "job_name": identity["job_name"] or "unknown",
        "execution_time": identity["execution_time"] or "unknown",
        "node_name": identity["node_name"] or "unknown",
        "status": identity["status"] or "unknown",
        "instance_id": identity["instance_id"] or "unknown",
        "executed_by": identity["executed_by"] or "unknown",
        "file_type": identity["file_type"] or "unknown",
        "ingestion_version": INGESTION_VERSION,
    }
    return labels, values


def push_loki(streams: list[dict[str, Any]]) -> None:
    payload = json.dumps({"streams": streams}, ensure_ascii=False).encode()
    request = urllib.request.Request(
        LOKI_PUSH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status not in {200, 204}:
                raise RuntimeError(f"Loki push returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(
            f"Loki push returned HTTP {exc.code}: {detail}"
        ) from exc


def flush_loki() -> None:
    flush_url = urllib.parse.urljoin(LOKI_PUSH_URL, "/flush")
    request = urllib.request.Request(
        flush_url, data=b"", method="POST"
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status not in {200, 204}:
            raise RuntimeError(
                f"Loki flush returned HTTP {response.status}"
            )


def build_metrics(
    catalog: list[dict[str, str]],
    definitions: dict[str, dict[str, str]],
    files_total: int,
    bytes_total: int,
    lines_total: int,
    skipped_total: int,
    success: bool,
) -> bytes:
    registry = CollectorRegistry()
    object_info = Gauge(
        "huawei_dataarts_log_object_info",
        "DataArts OBS log object catalog",
        [
            "job_name",
            "execution_time",
            "node_name",
            "file_type",
            "status",
            "instance_id",
            "executed_by",
            "log_path",
        ],
        registry=registry,
    )
    execution_files = Gauge(
        "huawei_dataarts_execution_log_files",
        "Number of DataArts log files for an execution",
        [
            "job_name",
            "execution_time",
            "status",
            "instance_id",
            "executed_by",
        ],
        registry=registry,
    )
    definition_info = Gauge(
        "huawei_dataarts_job_definition_info",
        "DataArts job definition, ownership, parameters, and log root",
        [
            "job_name",
            "job_type",
            "status",
            "owner",
            "created_by",
            "parameters",
            "log_root",
        ],
        registry=registry,
    )
    files_metric = Gauge(
        "huawei_dataarts_log_files_total",
        "DataArts log files found in OBS",
        registry=registry,
    )
    bytes_metric = Gauge(
        "huawei_dataarts_log_bytes_total",
        "Bytes in DataArts log files found in OBS",
        registry=registry,
    )
    lines_metric = Gauge(
        "huawei_dataarts_log_lines_ingested_total",
        "DataArts log lines pushed to Loki",
        registry=registry,
    )
    skipped_metric = Gauge(
        "huawei_dataarts_log_files_skipped_total",
        "DataArts log files skipped because of read or size errors",
        registry=registry,
    )
    success_metric = Gauge(
        "huawei_dataarts_log_sync_success",
        "Whether the latest DataArts-to-Loki synchronization succeeded",
        registry=registry,
    )
    sync_time = Gauge(
        "huawei_dataarts_log_last_sync_timestamp_seconds",
        "Last DataArts log synchronization timestamp",
        registry=registry,
    )

    execution_counts: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for item in catalog:
        object_info.labels(
            item["job_name"],
            item["execution_time"],
            item["node_name"],
            item["file_type"],
            item["status"],
            item["instance_id"],
            item["executed_by"],
            item["log_path"],
        ).set(1)
        execution_counts[
            (
                item["job_name"],
                item["execution_time"],
                item["status"],
                item["instance_id"],
                item["executed_by"],
            )
        ] += 1
    for labels, count in execution_counts.items():
        execution_files.labels(*labels).set(count)
    for item in definitions.values():
        definition_info.labels(
            item["job_name"],
            item["job_type"],
            item["status"],
            item["owner"],
            item["created_by"],
            item["parameters"],
            item["log_root"],
        ).set(1)
    files_metric.set(files_total)
    bytes_metric.set(bytes_total)
    lines_metric.set(lines_total)
    skipped_metric.set(skipped_total)
    success_metric.set(1 if success else 0)
    sync_time.set(time.time())
    return generate_latest(registry)


def sync_once() -> bytes:
    jobs = list_jobs()
    roots, definitions = list_job_details(jobs)
    if not roots:
        raise RuntimeError("No DataArts OBS log roots were returned by the API.")
    instances = list_instances()
    instance_index = index_instances(instances, definitions)
    obs = ObsClient(
        access_key_id=AK,
        secret_access_key=SK,
        server=f"https://obs.{REGION}.myhuaweicloud.com",
    )
    state = load_state()
    known: dict[str, str] = state.setdefault("objects", {})
    catalog: list[dict[str, str]] = []
    changed: list[tuple[dict[str, Any], dict[str, str], str, str]] = []
    skipped = 0
    try:
        objects = list_log_objects(obs, roots)
        for item in objects:
            identity = parse_log_identity(
                item, instance_index, definitions
            )
            catalog.append(identity)
            state_key = f"{item['bucket']}/{item['key']}"
            signature = object_signature(item)
            if known.get(state_key) != signature:
                changed.append((item, identity, state_key, signature))

        def prepare_stream(
            entry: tuple[dict[str, Any], dict[str, str], str, str]
        ) -> tuple[dict[str, Any], str, str, int] | None:
            item, identity, state_key, signature = entry
            worker_obs = ObsClient(
                access_key_id=AK,
                secret_access_key=SK,
                server=f"https://obs.{REGION}.myhuaweicloud.com",
            )
            try:
                labels, values = download_log(
                    worker_obs, item, identity
                )
                return (
                    {"stream": labels, "values": values},
                    state_key,
                    signature,
                    len(values),
                )
            except Exception:
                return None
            finally:
                worker_obs.close()

        for start in range(0, len(changed), 40):
            streams: list[dict[str, Any]] = []
            completed: list[tuple[str, str, int]] = []
            batch = changed[start : start + 40]
            with ThreadPoolExecutor(
                max_workers=max(1, DOWNLOAD_WORKERS)
            ) as executor:
                for prepared in executor.map(prepare_stream, batch):
                    if prepared is None:
                        skipped += 1
                        continue
                    stream, state_key, signature, line_count = prepared
                    streams.append(stream)
                    completed.append(
                        (state_key, signature, line_count)
                    )
            if streams:
                push_loki(streams)
                for state_key, signature, line_count in completed:
                    known[state_key] = signature
                    state["lines_ingested"] = int(
                        state.get("lines_ingested", 0)
                    ) + line_count
                save_state(state)
    finally:
        obs.close()

    if changed:
        flush_loki()

    return build_metrics(
        catalog=catalog,
        definitions=definitions,
        files_total=len(catalog),
        bytes_total=sum(
            int(item.get("size", 0))
            for item in objects
        ),
        lines_total=int(state.get("lines_ingested", 0)),
        skipped_total=skipped,
        success=True,
    )


def collect_loop() -> None:
    global LATEST, LAST_ERROR
    while True:
        try:
            rendered = sync_once()
            with LOCK:
                LATEST = rendered
                LAST_ERROR = ""
        except Exception as exc:
            with LOCK:
                LAST_ERROR = safe_text(str(exc), 1000)
        time.sleep(SYNC_INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        with LOCK:
            payload = LATEST
            error = LAST_ERROR
        if self.path == "/health":
            body = json.dumps(
                {"ok": bool(payload) and not error, "error": error}
            ).encode()
            self.send_response(200 if payload and not error else 503)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/metrics":
            body = payload or b"# DataArts log collection is starting\n"
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/plain; version=0.0.4"
            )
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
    ThreadingHTTPServer(("0.0.0.0", 9110), Handler).serve_forever()
