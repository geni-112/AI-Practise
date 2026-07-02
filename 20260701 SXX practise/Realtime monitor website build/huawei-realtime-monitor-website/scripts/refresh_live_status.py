#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obs import ObsClient, PutObjectHeader

from deploy_obs_static_site import DEFAULT_REGION, default_bucket, ensure_ok, get_obs_auth

ROOT = Path(__file__).resolve().parents[1]
MONITOR_DATA = ROOT / "monitor" / "data"
EXPORTS = ROOT / "exports"
LOGS = ROOT / "logs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tail(value: str, limit: int = 2400) -> str:
    cleaned = value.replace("\\", "/")
    return cleaned[-limit:] if len(cleaned) > limit else cleaned


def display_command(args: list[str]) -> list[str]:
    display = []
    for item in args:
        text = str(item)
        if text.lower().endswith(".py"):
            display.append(Path(text).name)
        else:
            display.append(text)
    return display


def run_step(name: str, args: list[str], timeout: int) -> dict[str, Any]:
    started = time.time()
    completed = subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "name": name,
        "command": display_command(args),
        "returncode": completed.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout": tail(completed.stdout),
        "stderr": tail(completed.stderr),
    }


def upload_status(region: str, bucket: str, status_path: Path) -> dict[str, Any]:
    obs_auth = get_obs_auth(region)
    client_kwargs = {
        "access_key_id": obs_auth["access"],
        "secret_access_key": obs_auth["secret"],
        "server": f"https://obs.{region}.myhuaweicloud.com",
    }
    if obs_auth.get("securitytoken"):
        client_kwargs["security_token"] = obs_auth["securitytoken"]
    client = ObsClient(**client_kwargs)
    try:
        headers = PutObjectHeader(contentType="application/json; charset=utf-8")
        response = client.putFile(bucket, "data/status.json", str(status_path), headers=headers)
        ensure_ok(response, "upload live data/status.json")
    finally:
        client.close()
    return {"bucket": bucket, "key": "data/status.json", "uploaded_at": utc_now()}


def write_state(payload: dict[str, Any]) -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    (EXPORTS / "sat_live_refresh_state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (LOGS / "sat_live_refresh.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def refresh_once(region: str, bucket: str, timeout: int) -> dict[str, Any]:
    started = time.time()
    state: dict[str, Any] = {
        "started_at": utc_now(),
        "region": region,
        "bucket": bucket,
        "ok": False,
        "steps": [],
    }
    try:
        inventory = run_step(
            "inventory",
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "huawei_inventory.py"), "--region", region],
            timeout,
        )
        state["steps"].append(inventory)
        if inventory["returncode"] != 0:
            return state

        assessment = run_step(
            "assessment",
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "analyze_bigdata_assets.py")],
            timeout,
        )
        state["steps"].append(assessment)
        if assessment["returncode"] != 0:
            return state

        status_path = MONITOR_DATA / "status.json"
        state["upload"] = upload_status(region, bucket, status_path)
        state["status_generated_at"] = json.loads(status_path.read_text(encoding="utf-8")).get("generated_at")
        state["ok"] = True
        return state
    except Exception as exc:
        state["error"] = str(exc)
        return state
    finally:
        state["finished_at"] = utc_now()
        state["duration_ms"] = int((time.time() - started) * 1000)
        write_state(state)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh SAT monitor status from live Huawei Cloud APIs and upload status.json to OBS.")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--bucket", default="")
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    obs_auth = get_obs_auth(args.region)
    bucket = args.bucket or default_bucket(obs_auth.get("project_id", ""))

    exit_code = 0
    while True:
        state = refresh_once(args.region, bucket, args.timeout)
        print(json.dumps({k: state.get(k) for k in ("ok", "started_at", "finished_at", "duration_ms", "status_generated_at", "error")}, ensure_ascii=False))
        if not state.get("ok"):
            exit_code = 1
        if not args.loop:
            return exit_code
        sleep_for = max(1, args.interval - int((state.get("duration_ms") or 0) / 1000))
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
