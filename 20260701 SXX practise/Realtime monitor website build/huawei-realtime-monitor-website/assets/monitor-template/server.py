#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOST = "127.0.0.1"
PORT = 8787


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "generated_at": utc_now(),
            "refresh_seconds": 5,
            "summary": {"healthy_services": 0, "total_services": 0, "resource_count": 0, "catalog_count": 0, "job_count": 0, "risk_count": 1},
            "topology": {"stages": []},
            "services": {},
            "catalog": [],
            "jobs": [],
            "risks": [f"{name} JSON parse failed: {exc}"],
            "recommendations": [],
        }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return

    def send_json(self, status: int, payload: dict) -> None:
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
            payload = load_json("status.json")
            if not payload:
                payload = load_json("sample_status.json")
            self.send_json(200, payload)
            return
        if path == "/api/inventory":
            self.send_json(200, load_json("inventory.json"))
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/refresh":
            self.send_json(404, {"error": "not found"})
            return
        command_path = DATA / "refresh_command.txt"
        if not command_path.exists():
            self.send_json(202, {"accepted": True, "mode": "reload-only"})
            return
        command = command_path.read_text(encoding="utf-8").strip()
        if not command:
            self.send_json(202, {"accepted": True, "mode": "reload-only"})
            return
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT.parents[0]),
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.send_json(
                202,
                {
                    "accepted": True,
                    "mode": "command",
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                },
            )
        except Exception as exc:
            self.send_json(500, {"accepted": False, "error": str(exc)})


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SAT Mexico Huawei Cloud monitor: http://{HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
