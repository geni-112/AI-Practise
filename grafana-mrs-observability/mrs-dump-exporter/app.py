from __future__ import annotations

import glob
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.environ.get("MRS_DUMP_PATH", "/data/mrs-dump")
SAFE = re.compile(r"[^a-zA-Z0-9_:]")


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render() -> bytes:
    newest: dict[tuple[str, ...], tuple[str, str]] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "**", "metric_*.log"), recursive=True))[-50:]:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    parts = line.rstrip("\n").split("|")
                    if len(parts) < 10:
                        continue
                    cluster_id, cluster_name, display, service, metric_id = parts[:5]
                    collected_at, host, unit, value = parts[5], parts[6], parts[-2], parts[-1]
                    try:
                        float(value)
                    except ValueError:
                        continue
                    key = (cluster_id, cluster_name, display, service, metric_id, host, unit)
                    if key not in newest or collected_at > newest[key][0]:
                        newest[key] = (collected_at, value)
        except OSError:
            continue
    lines = [
        "# HELP huawei_mrs_manager_metric FusionInsight Manager component metric",
        "# TYPE huawei_mrs_manager_metric gauge",
    ]
    for key, (_, value) in newest.items():
        cluster_id, cluster_name, display, service, metric_id, host, unit = key
        labels = {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "display_name": display,
            "service": service,
            "metric_id": metric_id,
            "host": host,
            "unit": unit,
        }
        label_text = ",".join(f'{name}="{esc(text)}"' for name, text in labels.items())
        lines.append(f"huawei_mrs_manager_metric{{{label_text}}} {value}")
    lines.append(f"huawei_mrs_manager_series_count {len(newest)}")
    return ("\n".join(lines) + "\n").encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = render() if self.path == "/metrics" else b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9109), Handler).serve_forever()
