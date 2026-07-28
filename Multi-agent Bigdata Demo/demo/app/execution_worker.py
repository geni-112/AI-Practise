from __future__ import annotations

import argparse
import os
import re
import socket
import time
from typing import Any

from .huawei_execution import cancel, poll, submit
from .production_control import get_production_store
from .security import cloud_execution_enabled


SENSITIVE_VALUE = re.compile(
    r"(?i)(access[_-]?key|secret[_-]?key|password|passwd|token|authorization)"
    r"\s*[:=]\s*[^,\s;]+"
)


def safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return SENSITIVE_VALUE.sub(r"\1=<redacted>", text)[:2000]


def run_once(worker_id: str | None = None) -> dict[str, Any] | None:
    if not cloud_execution_enabled():
        raise RuntimeError(
            "Cloud execution is disabled. Set SAT_PRODUCTION_MODE=true and "
            "SAT_CLOUD_EXECUTION_ENABLED=true only on the protected worker."
        )

    store = get_production_store()
    worker = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    request = store.claim_next_execution(worker)
    if request is None:
        return None

    request_id = request["request_id"]
    target = request["target"]
    parameters = request["parameters"]
    poll_seconds = max(2, int(os.getenv("SAT_EXECUTION_POLL_SECONDS", "10")))
    timeout_seconds = max(30, int(os.getenv("SAT_EXECUTION_TIMEOUT_SECONDS", "3600")))
    started = time.monotonic()
    try:
        submission = submit(target, parameters, request_id)
        cloud_job_id = str(submission["cloud_job_id"])
        store.update_execution(
            request_id,
            status="running",
            actor=worker,
            cloud_job_id=cloud_job_id,
            evidence={"submission": submission},
        )
        while True:
            latest = store.execution_request(request_id)
            if latest and latest["status"] == "cancel_requested":
                cancellation = cancel(target, parameters, cloud_job_id)
                return store.update_execution(
                    request_id,
                    status="cancelled",
                    actor=worker,
                    cloud_job_id=cloud_job_id,
                    evidence={
                        "submission": submission,
                        "cancellation": cancellation,
                    },
                )
            if time.monotonic() - started > timeout_seconds:
                return store.update_execution(
                    request_id,
                    status="failed",
                    actor=worker,
                    cloud_job_id=cloud_job_id,
                    evidence={"submission": submission, "timeout_seconds": timeout_seconds},
                    error_message="Execution exceeded the configured timeout.",
                )

            result = poll(target, parameters, cloud_job_id, submission)
            if result.get("terminal"):
                return store.update_execution(
                    request_id,
                    status="succeeded" if result.get("succeeded") else "failed",
                    actor=worker,
                    cloud_job_id=cloud_job_id,
                    evidence={
                        "submission": submission,
                        "terminal": result,
                    },
                    error_message="" if result.get("succeeded") else "Cloud job failed.",
                )
            store.update_execution(
                request_id,
                status="running",
                actor=worker,
                cloud_job_id=cloud_job_id,
                evidence={
                    "submission": submission,
                    "latest_poll": result,
                },
            )
            time.sleep(poll_seconds)
    except Exception as exc:
        return store.update_execution(
            request_id,
            status="failed",
            actor=worker,
            error_message=safe_error(exc),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="SAT production cloud execution worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued request.")
    parser.add_argument("--idle-seconds", type=int, default=5)
    args = parser.parse_args()

    if args.once:
        run_once()
        return 0

    while True:
        result = run_once()
        if result is None:
            time.sleep(max(1, args.idle_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
