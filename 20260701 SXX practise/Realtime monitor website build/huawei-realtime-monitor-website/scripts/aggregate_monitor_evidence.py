#!/usr/bin/env python3
"""Create a concise delivery evidence report for a Huawei realtime monitor site."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "assets" / "monitor-template" / "data" / "sample_status.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_status(url: str) -> tuple[int | None, str]:
    if not url:
        return None, "not requested"
    req = Request(url.rstrip("/") + "/data/status.json", headers={"User-Agent": "codex-monitor-evidence/1.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read(500_000).decode("utf-8", errors="replace")
            return int(resp.status), body
    except URLError as exc:
        return None, f"fetch failed: {exc}"


def service_counts(status: dict[str, Any]) -> dict[str, int]:
    resources = status.get("resources") or []
    counts: dict[str, int] = {}
    for item in resources:
        service = str(item.get("service") or item.get("type") or "unknown")
        counts[service] = counts.get(service, 0) + 1
    return dict(sorted(counts.items()))


def render_report(status: dict[str, Any], site_url: str, http_status: int | None, source: str) -> str:
    summary = status.get("summary") or {}
    counts = service_counts(status)
    lines = [
        "# Realtime Monitor Delivery Evidence",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Site URL: {site_url or 'not provided'}",
        f"- Remote status endpoint: {http_status or source}",
        f"- Dataset timestamp: {status.get('generated_at') or summary.get('generated_at') or 'unknown'}",
        f"- Resource records: {summary.get('resource_count', len(status.get('resources') or []))}",
        f"- Pipeline health: {summary.get('pipeline_health', 'unknown')}",
        "",
        "## Service Counts",
    ]
    if counts:
        lines.extend(f"- {service}: {count}" for service, count in counts.items())
    else:
        lines.append("- No resource records in status payload.")
    notes = status.get("notes") or []
    if notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in notes[:12])
    lines.extend(
        [
            "",
            "## Handoff Checks",
            "- Confirm the browser opens the HTTPS URL without unsafe-site warnings.",
            "- Confirm `/data/status.json` returns HTTP 200 and updates on the expected schedule.",
            "- Confirm resource counts separate core big-data assets from web/infrastructure records.",
            "- Confirm no credentials or raw inventory exports are included in the published site.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-json", type=Path, default=DEFAULT_STATUS, help="Local status JSON to summarize")
    parser.add_argument("--site-url", default="", help="Published HTTPS monitor URL")
    parser.add_argument("--output", type=Path, default=ROOT / "monitor_evidence.md", help="Report output path")
    args = parser.parse_args()

    status = load_json(args.status_json)
    http_status, remote_body = fetch_status(args.site_url)
    source = "local status"
    if http_status == 200:
        try:
            status = json.loads(remote_body)
            source = "remote status"
        except json.JSONDecodeError:
            source = "remote status was not JSON; used local status"
    elif not status:
        status = {"summary": {"resource_count": 0, "pipeline_health": "unknown"}, "notes": [remote_body]}
        source = remote_body

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(status, args.site_url, http_status, source), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
