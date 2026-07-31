from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_EVIDENCE_ROOT = APP_ROOT / "cloud_real_bigdata" / "public_evidence"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Cloud E2E evidence not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cloud E2E evidence is invalid JSON: {exc}") from exc


def require_success(evidence: dict[str, Any]) -> None:
    job_status = str((evidence.get("job") or {}).get("terminal_status") or "").lower()
    if job_status != "success":
        raise SystemExit(f"Cloud E2E evidence is not successful: job_status={job_status or 'missing'}")
    if int(evidence.get("gold_row_count") or 0) <= 0:
        raise SystemExit("Cloud E2E evidence has no gold rows.")
    if bool(evidence.get("direct_rfc_exposed", True)):
        raise SystemExit("Cloud E2E evidence reports direct RFC exposure.")
    if bool(evidence.get("duckdb_used", True)):
        raise SystemExit("Cloud E2E evidence reports DuckDB usage.")


def first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_agent_context(evidence: dict[str, Any]) -> dict[str, Any]:
    run_id = first_text(evidence.get("agent_run_id"), evidence.get("run_id"))
    if not run_id:
        return {}
    run_dir = APP_ROOT / "generated" / run_id
    result: dict[str, Any] = {
        "agent_run_id": run_id,
        "generated_dir": str(run_dir),
    }
    manifest_path = run_dir / "run_manifest.json"
    request_path = run_dir / "request.json"
    prompt_path = run_dir / "prompt.txt"
    if manifest_path.exists():
        result["run_manifest"] = read_json(manifest_path)
    if request_path.exists():
        result["request"] = read_json(request_path)
    if prompt_path.exists():
        result["prompt"] = prompt_path.read_text(encoding="utf-8").strip()
    return result


def build_summary(evidence: dict[str, Any], agent: dict[str, Any], base_url: str) -> dict[str, Any]:
    job = evidence.get("job") or {}
    gold_rows = evidence.get("gold_preview_rows") or []
    manifest = agent.get("run_manifest") or {}
    artifacts = manifest.get("artifacts") or []
    return {
        "status": "ready_for_customer_demo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url.rstrip("/"),
        "customer_report_url": f"{base_url.rstrip('/')}/cloud-evidence/customer_demo_report.html" if base_url else "",
        "api_evidence_url": f"{base_url.rstrip('/')}/api/cloud/e2e-evidence" if base_url else "",
        "run_id": evidence.get("run_id", ""),
        "agent_run_id": evidence.get("agent_run_id", ""),
        "region": evidence.get("region", ""),
        "bucket": evidence.get("bucket", ""),
        "cluster_id": evidence.get("cluster_id", ""),
        "job_status": job.get("terminal_status", ""),
        "job_id": job.get("job_id", ""),
        "job_name": job.get("job_name", ""),
        "gold_prefix": evidence.get("gold_prefix", ""),
        "gold_row_count": evidence.get("gold_row_count", 0),
        "direct_rfc_exposed": evidence.get("direct_rfc_exposed", True),
        "duckdb_used": evidence.get("duckdb_used", True),
        "agent_release_prefix": evidence.get("agent_release_prefix", ""),
        "artifact_count": len(artifacts),
        "review_required_artifacts": [
            item.get("name", "") for item in artifacts if item.get("review_required")
        ],
        "gold_preview_rows": gold_rows[:20],
        "checks": [
            {"name": "MRS Spark job finished", "status": "passed"},
            {"name": "Gold output is non-empty", "status": "passed"},
            {"name": "Direct RFC is not exposed", "status": "passed"},
            {"name": "DuckDB was not used", "status": "passed"},
            {"name": "Prompt-derived agent package linked", "status": "passed" if evidence.get("agent_run_id") else "warning"},
        ],
    }


def markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No rows were included in the preview._"
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows[:20]:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any], evidence: dict[str, Any], agent: dict[str, Any]) -> str:
    prompt = first_text(agent.get("prompt"), "Prompt was not available in the deployed package.")
    checks = "\n".join(f"- {item['status']}: {item['name']}" for item in summary["checks"])
    return f"""# SAT Agentic Real Huawei Cloud E2E Demo Report

## Executive Summary

- Status: {summary["status"]}
- Business run id: {summary["run_id"]}
- Agent run id: {summary["agent_run_id"] or "not linked"}
- Region: {summary["region"]}
- Huawei Cloud execution layer: OBS + MRS Spark
- Website report: {summary["customer_report_url"] or "local file"}
- API evidence: {summary["api_evidence_url"] or "local file"}

## Business Prompt

{prompt}

## Cloud Execution Evidence

- OBS bucket: {summary["bucket"]}
- MRS cluster id: {summary["cluster_id"]}
- MRS job: {summary["job_name"] or summary["job_id"]}
- MRS job status: {summary["job_status"]}
- Gold output: {summary["gold_prefix"]}
- Gold row count: {summary["gold_row_count"]}
- Agent release package: {summary["agent_release_prefix"] or "not linked"}

## Governance Checks

{checks}

## Gold Preview

{markdown_table(summary["gold_preview_rows"])}

## Operator Notes

- Direct RFC is not exposed in the gold evidence.
- DuckDB is not used as the execution layer.
- Generated agent artifacts are preserved as release evidence.
- Keep Terraform state and OBS audit evidence for customer review before cleanup.
- Cleanup command after the demo: `.\\cloud_real_bigdata\\scripts\\04_destroy.ps1 -ConfirmDestroy`
"""


def markdown_to_html(markdown: str, summary: dict[str, Any]) -> str:
    escaped_lines = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            escaped_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            escaped_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            escaped_lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("| "):
            escaped_lines.append(f"<pre>{html.escape(line)}</pre>")
        elif line.strip():
            escaped_lines.append(f"<p>{html.escape(line)}</p>")
        else:
            escaped_lines.append("")
    body = "\n".join(escaped_lines)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SAT Agentic E2E Demo Report</title>
  <style>
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 24px 72px; }}
    h1 {{ font-size: 34px; line-height: 1.15; margin: 0 0 24px; }}
    h2 {{ font-size: 20px; margin: 32px 0 12px; }}
    p, li {{ font-size: 15px; line-height: 1.65; color: #374151; }}
    li {{ margin: 4px 0; }}
    pre {{ overflow-x: auto; background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; padding: 8px 10px; margin: 0; font-size: 13px; }}
    .status {{ display: inline-flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: 999px; background: #dcfce7; color: #166534; font-weight: 700; margin-bottom: 20px; }}
    .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 24px; }}
    .meta div {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; padding: 12px; }}
    .meta span {{ display: block; color: #64748b; font-size: 12px; margin-bottom: 4px; }}
  </style>
</head>
<body>
  <main>
    <div class="status">Ready for customer demo</div>
    <div class="meta">
      <div><span>Run</span>{html.escape(str(summary["run_id"]))}</div>
      <div><span>Job</span>{html.escape(str(summary["job_status"]))}</div>
      <div><span>Gold rows</span>{html.escape(str(summary["gold_row_count"]))}</div>
      <div><span>RFC</span>{'masked' if not summary["direct_rfc_exposed"] else 'exposed'}</div>
    </div>
    {body}
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export customer-facing demo evidence from a successful real Huawei Cloud E2E run.")
    parser.add_argument("--evidence", default=str(PUBLIC_EVIDENCE_ROOT / "latest_e2e_result.json"))
    parser.add_argument("--output-dir", default=str(PUBLIC_EVIDENCE_ROOT))
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()

    evidence = read_json(Path(args.evidence))
    require_success(evidence)
    agent = load_agent_context(evidence)
    summary = build_summary(evidence, agent, args.base_url)
    markdown = render_markdown(summary, evidence, agent)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "customer_demo_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "customer_demo_report.md").write_text(markdown, encoding="utf-8")
    (output_dir / "customer_demo_report.html").write_text(
        markdown_to_html(markdown, summary),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
