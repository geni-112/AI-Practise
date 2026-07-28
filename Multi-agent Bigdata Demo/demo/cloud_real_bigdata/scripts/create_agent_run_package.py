from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.agent_graph import run_agent_workflow  # noqa: E402
from app.models import RunRequest  # noqa: E402


DEFAULT_PROMPT = (
    "Build a governed SAT taxpayer annual base for tax year 2025. "
    "Use source data from local://landing/taxpayer_registry.csv and restrict local validation to "
    "CDMX, Jalisco, Nuevo Leon, Puebla, and Yucatan. Mask direct RFC, keep rfc_hash and masked_rfc "
    "only, aggregate by year, region, regime, and RESICO flag, then produce PySpark, SQL, DataArts "
    "DAG, quality rules, security review, and lineage evidence. Keep production execution blocked "
    "until PySpark, SQL, and DAG are reviewed."
)


TOP_LEVEL_PACKAGE_FILES = [
    "prompt.txt",
    "request.json",
    "run_manifest.json",
    "review_status.json",
    "synthetic_rows.json",
    "gold_preview.json",
    "contract_audit.json",
    "local_execution.json",
    "quality_gates.json",
    "lineage_manifest.json",
    "maas_trace.json",
]


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    return DEFAULT_PROMPT


def package_file_entries(generated_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in TOP_LEVEL_PACKAGE_FILES:
        path = generated_dir / name
        if path.exists() and path.is_file():
            entries.append(file_entry(generated_dir, path, category="package"))

    artifacts_dir = generated_dir / "artifacts"
    if artifacts_dir.exists():
        for path in sorted(artifacts_dir.iterdir(), key=lambda item: item.name):
            if path.is_file():
                entries.append(file_entry(generated_dir, path, category="artifact"))
    return entries


def file_entry(root: Path, path: Path, category: str) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    return {
        "name": path.name,
        "category": category,
        "relative_path": relative,
        "bytes": path.stat().st_size,
    }


def build_summary(response: Any) -> dict[str, Any]:
    generated_dir = Path(response.generated_dir).resolve()
    return {
        "run_id": response.run_id,
        "status": response.status,
        "execution_mode": response.execution_mode,
        "generated_dir": str(generated_dir),
        "generated_dir_relative": f"generated/{response.run_id}",
        "generated_url": response.generated_url,
        "maas": response.maas,
        "business_contract_status": response.contract_audit.get("status", "missing"),
        "local_execution_status": response.local_execution.get("status", "missing"),
        "synthetic_row_count": len(response.synthetic_rows),
        "gold_preview_row_count": len(response.gold_rows),
        "review_required_artifacts": [
            artifact.name for artifact in response.artifacts if artifact.review_required
        ],
        "artifacts": [
            {
                "name": artifact.name,
                "kind": artifact.kind,
                "path": artifact.path,
                "review_required": artifact.review_required,
                "review_status": artifact.review_status,
            }
            for artifact in response.artifacts
        ],
        "files": package_file_entries(generated_dir),
    }


def write_summary(summary: dict[str, Any], output: str | None) -> Path:
    output_path = Path(output) if output else APP_ROOT / ".cloud_real_bigdata_work" / summary["run_id"] / "agent_run_package.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


async def generate_package(args: argparse.Namespace) -> dict[str, Any]:
    request = RunRequest(
        prompt=read_prompt(args),
        scenario=args.scenario,
        use_maas=args.use_maas,
        template_id=args.template_id or None,
        template_variables={},
    )
    response = await run_agent_workflow(request)
    summary = build_summary(response)
    summary_path = write_summary(summary, args.output).resolve()
    summary["summary_path"] = str(summary_path)
    summary["summary_path_relative"] = f".cloud_real_bigdata_work/{summary['run_id']}/agent_run_package.json"
    summary["cloud_execution"] = "not_started"
    summary["next_action"] = "Upload agent package to OBS release path, then run reviewed MRS smoke job."
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local agent run package from a business prompt.")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--scenario", default="sat_padron_base_anual")
    parser.add_argument("--template-id", default="")
    parser.add_argument("--use-maas", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    summary = asyncio.run(generate_package(args))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
