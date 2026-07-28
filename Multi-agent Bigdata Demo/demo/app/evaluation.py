from __future__ import annotations

import json
import re
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_graph import run_agent_workflow
from .artifact_store import (
    APP_ROOT,
    GENERATED_ROOT,
    create_cloud_binding_simulation,
    create_import_review,
    create_release_package,
    get_cloud_binding_status,
    get_import_review_status,
    get_release_package_status,
    read_json,
    read_optional_json,
    resolve_existing_run_dir,
    save_artifact_review,
    write_json,
)
from .maas_client import maas_status
from .models import (
    ArtifactReviewRequest,
    CloudBindingRequest,
    ComparisonRunRequest,
    EvaluationRunRequest,
    FailureReplayRequest,
    ImportReviewRequest,
    RunRequest,
)

EVALUATIONS_ROOT = APP_ROOT / "evaluations"
FAILURES_ROOT = EVALUATIONS_ROOT / "failures"
REPLAY_ROOT_PREFIX = "replay"
PRE_EXECUTION_DIR_NAME = "pre_execution"
PRE_EXECUTION_STATUS_NAME = "pre_execution_readiness.json"


EVAL_CASES = [
    {
        "id": "annual_base_default",
        "name": "Annual taxpayer base",
        "scenario": "tax_taxpayer_annual_base",
        "prompt": (
            "Build a governed Tax taxpayer annual base for tax year 2025. Use source data from "
            "local://landing/taxpayer_registry.csv and restrict local validation to CDMX, Jalisco, "
            "Nuevo Leon, Puebla, and Yucatan. Mask direct RFC, keep rfc_hash and masked_rfc only, "
            "aggregate by year, region, regime, and RESICO flag, then produce PySpark, SQL, "
            "DataArts DAG, quality rules, security review, and lineage evidence. Keep production "
            "execution blocked until PySpark, SQL, and DAG are reviewed."
        ),
    },
    {
        "id": "annual_base_south_region",
        "name": "Regional annual base",
        "scenario": "tax_taxpayer_annual_base",
        "prompt": (
            "Create a Tax annual taxpayer base for a regional validation run covering CDMX, Puebla, "
            "and Yucatan. Use local://landing/taxpayer_registry.csv. The output must aggregate "
            "active taxpayers and declared amount by tax year, region, regime, and RESICO flag. "
            "Drop direct RFC after deriving rfc_hash and masked_rfc, generate PySpark, SQL, "
            "DataArts DAG, quality evidence, security review, and lineage. Production execution "
            "must stay blocked until the executable artifacts are approved."
        ),
    },
    {
        "id": "resico_governed_control",
        "name": "RESICO governed control",
        "scenario": "tax_resico_control",
        "prompt": (
            "Build a governed Tax RESICO control view for tax year 2025 using "
            "local://landing/taxpayer_registry.csv. Focus on active RESICO taxpayers and regime "
            "classification evidence, but keep the supported aggregate grain as year, region, "
            "regime, and RESICO flag. Use masked/hash identifiers only in local previews. Produce "
            "PySpark, SQL, DataArts DAG, local dry-run evidence, quality rules, security review, "
            "and lineage. Keep cloud execution blocked until human review."
        ),
    },
    {
        "id": "regime_reconciliation_preview",
        "name": "Regime reconciliation preview",
        "scenario": "tax_regime_reconciliation",
        "prompt": (
            "Build a Tax taxpayer regime reconciliation preview using local synthetic snapshots. "
            "Use local://landing/taxpayer_registry.csv as the current governed source and preserve "
            "the supported aggregate grain of year, region, regime, and RESICO flag. Produce "
            "PySpark, SQL, DataArts DAG, metric reconciliation evidence, security review, quality "
            "rules, and lineage. Do not expose direct RFC and keep DataArts, MRS, OBS, and DWS "
            "execution blocked until review."
        ),
    },
    {
        "id": "security_first_base",
        "name": "Security-first annual base",
        "scenario": "tax_taxpayer_annual_base",
        "prompt": (
            "Generate a security-first Tax taxpayer annual base. Source is "
            "local://landing/taxpayer_registry.csv. Validate that direct RFC never leaves the "
            "local synthetic layer, that rfc_hash and masked_rfc are the only identifier previews, "
            "and that gold outputs aggregate by year, region, regime, and RESICO flag. Produce "
            "PySpark, SQL, DataArts DAG, security review, quality gates, lineage, and local run "
            "evidence. Keep production execution blocked until review."
        ),
    },
]


async def run_evaluation(request: EvaluationRunRequest) -> dict[str, Any]:
    eval_id = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    eval_dir = EVALUATIONS_ROOT / eval_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    cases = EVAL_CASES[: request.max_cases]
    started_at = now_iso()
    case_results = []

    for index, case in enumerate(cases, start=1):
        case_results.append(await run_eval_case(case, index=index, use_maas=request.use_maas))

    summary = build_eval_summary(eval_id=eval_id, started_at=started_at, cases=case_results, request=request)
    write_json(eval_dir / "case_results.json", case_results)
    write_json(eval_dir / "summary.json", summary)
    (eval_dir / "scorecard.md").write_text(render_scorecard(summary, case_results), encoding="utf-8")

    files = [
        evaluation_file_entry(eval_id, "summary.json", "Machine-readable evaluation summary."),
        evaluation_file_entry(eval_id, "scorecard.md", "Human-readable evaluation scorecard."),
        evaluation_file_entry(eval_id, "case_results.json", "Per-case checks and generated run references."),
    ]
    summary["files"] = files
    write_json(eval_dir / "summary.json", summary)
    return evaluation_response(summary, case_results, files)


async def run_ab_comparison(request: ComparisonRunRequest) -> dict[str, Any]:
    comparison_id = f"compare-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    comparison_dir = EVALUATIONS_ROOT / comparison_id
    comparison_dir.mkdir(parents=True, exist_ok=True)
    (comparison_dir / "local").mkdir(exist_ok=True)
    (comparison_dir / "maas").mkdir(exist_ok=True)

    status = maas_status()
    local_result = await run_evaluation(EvaluationRunRequest(use_maas=False, max_cases=request.max_cases))
    write_json(comparison_dir / "local" / "summary.json", local_result)

    maas_result: dict[str, Any]
    maas_ran = bool(status.get("configured"))
    if maas_ran:
        maas_result = await run_evaluation(EvaluationRunRequest(use_maas=True, max_cases=request.max_cases))
        write_json(comparison_dir / "maas" / "summary.json", maas_result)
    else:
        maas_result = skipped_maas_result(request.max_cases, status)
        write_json(comparison_dir / "maas" / "skipped.json", maas_result)

    artifact_diff = build_artifact_diff(local_result, maas_result) if maas_ran else []
    case_comparisons = build_case_comparisons(local_result, maas_result, maas_ran=maas_ran)
    metrics = build_comparison_metrics(local_result, maas_result, case_comparisons, maas_ran=maas_ran)
    verdict = build_comparison_verdict(local_result, maas_result, metrics, maas_ran=maas_ran)
    files = [
        comparison_file_entry(comparison_id, "summary.json", "Machine-readable A/B comparison summary."),
        comparison_file_entry(comparison_id, "comparison_report.md", "Human-readable Local vs MaaS comparison report."),
        comparison_file_entry(comparison_id, "artifact_diff.json", "Per-case artifact size and hash comparison."),
        comparison_file_entry(comparison_id, "local/summary.json", "Local fallback evaluation response."),
        comparison_file_entry(
            comparison_id,
            "maas/summary.json" if maas_ran else "maas/skipped.json",
            "MaaS evaluation response or skipped reason.",
        ),
    ]
    summary = {
        "comparison_id": comparison_id,
        "status": verdict["status"],
        "passed": verdict["passed"],
        "summary": verdict["summary"],
        "recommendation": verdict["recommendation"],
        "started_at": local_result.get("cases", [{}])[0].get("started_at") if local_result.get("cases") else now_iso(),
        "completed_at": now_iso(),
        "maas_configured": bool(status.get("configured")),
        "maas_model": status.get("model", ""),
        "local": comparison_eval_summary(local_result),
        "maas": comparison_eval_summary(maas_result),
        "metrics": metrics,
        "cases": case_comparisons,
        "files": files,
    }
    failure_samples = capture_failure_samples(
        comparison_id=comparison_id,
        summary=summary,
        local_result=local_result,
        maas_result=maas_result,
        artifact_diff=artifact_diff,
    )
    summary["failure_samples"] = failure_samples
    write_json(comparison_dir / "artifact_diff.json", artifact_diff)
    write_json(comparison_dir / "summary.json", summary)
    (comparison_dir / "comparison_report.md").write_text(
        render_comparison_report(summary, local_result, maas_result, artifact_diff),
        encoding="utf-8",
    )
    return comparison_response(summary)


async def run_eval_case(case: dict[str, str], *, index: int, use_maas: bool) -> dict[str, Any]:
    started_at = now_iso()
    run_id = ""
    error = ""
    execution_mode = ""
    maas_used = False
    maas_error = ""
    try:
        run_obj = await run_agent_workflow(
            RunRequest(
                prompt=case["prompt"],
                scenario=case["scenario"],
                use_maas=use_maas,
                template_id=f"eval:{case['id']}",
                template_variables={"source_uri": "local://landing/taxpayer_registry.csv"},
            )
        )
        run = run_obj.model_dump() if hasattr(run_obj, "model_dump") else run_obj
        run_id = run["run_id"]
        execution_mode = run.get("execution_mode", "")
        maas_used = bool(run.get("maas", {}).get("used"))
        maas_error = str(run.get("maas", {}).get("error") or "")
        approve_reviewable_artifacts(run)
        release = create_release_package(run_id)
        binding = create_cloud_binding_simulation(run_id, CloudBindingRequest())
        import_review = create_import_review(
            run_id,
            ImportReviewRequest(reviewer="evaluation_harness", note=f"Automated evaluation case {case['id']}."),
        )
        checks = evaluate_run_outputs(
            run=run,
            release=release,
            binding=binding,
            import_review=import_review,
        )
    except Exception as exc:  # noqa: BLE001 - keep evaluation running and report the failed case.
        error = f"{type(exc).__name__}: {exc}"
        checks = [eval_check("EVAL-000", "Case completed without exception", False, error)]

    passed_checks = [item for item in checks if item["status"] == "passed"]
    failed_checks = [item for item in checks if item["status"] == "failed"]
    return {
        "index": index,
        "case_id": case["id"],
        "name": case["name"],
        "scenario": case["scenario"],
        "run_id": run_id,
        "run_url": f"/generated/{run_id}/run_manifest.json" if run_id else "",
        "execution_mode": execution_mode,
        "maas_requested": use_maas,
        "maas_used": maas_used,
        "maas_error": maas_error,
        "status": "passed" if not failed_checks else "failed",
        "score": len(passed_checks),
        "max_score": len(checks),
        "pass_rate": round(len(passed_checks) / len(checks), 4) if checks else 0,
        "started_at": started_at,
        "completed_at": now_iso(),
        "error": error,
        "checks": checks,
    }


def approve_reviewable_artifacts(run: dict[str, Any]) -> None:
    for artifact in run.get("artifacts", []):
        if artifact.get("review_required"):
            save_artifact_review(
                run["run_id"],
                artifact["name"],
                ArtifactReviewRequest(
                    status="approved",
                    reviewer="evaluation_harness",
                    note="Automatically approved for local evaluation only.",
                ),
            )


def evaluate_run_outputs(
    *,
    run: dict[str, Any],
    release: dict[str, Any],
    binding: dict[str, Any],
    import_review: dict[str, Any],
) -> list[dict[str, str]]:
    run_id = run["run_id"]
    artifacts = {artifact["name"]: artifact for artifact in run.get("artifacts", [])}
    required_artifacts = [
        "business_contract.yaml",
        "contract_audit.json",
        "mrs_transform.py",
        "dws_serving.sql",
        "dataarts_dag.yaml",
        "execution_report.json",
        "local_run_output.json",
        "metric_reconciliation.json",
        "security_review.md",
    ]
    run_dir = APP_ROOT / "generated" / run_id
    release_dir = run_dir / "release"
    release_manifest = read_optional_eval_json(release_dir / "release_manifest.json")
    binding_status = read_optional_eval_json(run_dir / "cloud_binding_status.json")
    import_status = read_optional_eval_json(run_dir / "import_review_status.json")
    resolved_package = read_optional_eval_json(release_dir / "resolved_dataarts_import_package.json")
    generated_files = [
        release_dir / "cloud_import_review.json",
        release_dir / "operator_handoff.md",
        release_dir / "final_import_manifest.json",
    ]
    quality_gates = run.get("quality_gates", [])
    artifact_text = "\n".join(str(artifact.get("content", "")) for artifact in run.get("artifacts", []))
    release_text = json.dumps(release_manifest, ensure_ascii=False)
    binding_text = json.dumps(binding_status, ensure_ascii=False)
    import_text = json.dumps(import_status, ensure_ascii=False)

    return [
        eval_check(
            "EVAL-001",
            "All required artifacts were generated",
            all(name in artifacts for name in required_artifacts),
            f"missing={[name for name in required_artifacts if name not in artifacts]}",
        ),
        eval_check(
            "EVAL-002",
            "Contract audit passed",
            run.get("contract_audit", {}).get("status") == "passed",
            run.get("contract_audit", {}).get("summary", ""),
        ),
        eval_check(
            "EVAL-003",
            "No quality gate failed",
            not [gate for gate in quality_gates if gate.get("status") == "failed"],
            f"failed={[gate.get('id') for gate in quality_gates if gate.get('status') == 'failed']}",
        ),
        eval_check(
            "EVAL-004",
            "Generated artifacts do not expose direct RFC",
            not contains_plain_rfc(artifact_text),
            "Checks generated artifact text for unmasked RFC-shaped identifiers.",
        ),
        eval_check(
            "EVAL-005",
            "Local dry-run reconciliation passed",
            run.get("local_execution", {}).get("status") == "passed",
            run.get("local_execution", {}).get("metric_reconciliation", {}).get("summary", ""),
        ),
        eval_check(
            "EVAL-006",
            "Release package generated",
            release.get("status") == "generated" and release.get("ready") is True,
            release.get("message", ""),
        ),
        eval_check(
            "EVAL-007",
            "Cloud binding simulation passed",
            binding.get("status") == "simulated_ready" and binding.get("ready_for_import_review") is True,
            binding.get("message", ""),
        ),
        eval_check(
            "EVAL-008",
            "Import review reached operator handoff",
            import_review.get("status") == "operator_handoff_ready"
            and import_review.get("ready_for_operator_handoff") is True,
            import_review.get("message", ""),
        ),
        eval_check(
            "EVAL-009",
            "Cloud execution stayed blocked",
            all("blocked" in text.lower() for text in [release_text, binding_text, import_text])
            and run.get("bigdata_execution", {}).get("state") == "blocked",
            "Release, binding, import review, and run decision all preserve the execution lock.",
        ),
        eval_check(
            "EVAL-010",
            "Resolved import package has no placeholders",
            not has_unresolved_placeholder(resolved_package),
            "No ${...}, <...>, or > tokens remain after local binding simulation.",
        ),
        eval_check(
            "EVAL-011",
            "Evaluation handoff files exist",
            all(path.exists() for path in generated_files),
            f"files={[path.name for path in generated_files]}",
        ),
    ]


def eval_check(check_id: str, name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def build_eval_summary(
    *,
    eval_id: str,
    started_at: str,
    cases: list[dict[str, Any]],
    request: EvaluationRunRequest,
) -> dict[str, Any]:
    score = sum(case["score"] for case in cases)
    max_score = sum(case["max_score"] for case in cases)
    failed_cases = [case for case in cases if case["status"] != "passed"]
    passed = not failed_cases and max_score > 0
    return {
        "eval_id": eval_id,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "score": score,
        "max_score": max_score,
        "pass_rate": round(score / max_score, 4) if max_score else 0,
        "case_count": len(cases),
        "failed_case_count": len(failed_cases),
        "started_at": started_at,
        "completed_at": now_iso(),
        "use_maas": request.use_maas,
        "maas_requested": request.use_maas,
        "maas_used_case_count": sum(1 for case in cases if case.get("maas_used")),
        "summary": f"{len(cases) - len(failed_cases)}/{len(cases)} cases passed; {score}/{max_score} checks passed.",
    }


def evaluation_response(summary: dict[str, Any], cases: list[dict[str, Any]], files: list[dict[str, str]]) -> dict[str, Any]:
    eval_id = summary["eval_id"]
    return {
        "eval_id": eval_id,
        "status": summary["status"],
        "passed": summary["passed"],
        "score": summary["score"],
        "max_score": summary["max_score"],
        "pass_rate": summary["pass_rate"],
        "case_count": summary["case_count"],
        "summary": summary["summary"],
        "eval_dir": str(EVALUATIONS_ROOT / eval_id),
        "eval_url": f"/evaluations/{eval_id}/scorecard.md",
        "files": files,
        "cases": cases,
    }


def skipped_maas_result(max_cases: int, status: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_id": "",
        "status": "skipped",
        "passed": False,
        "score": 0,
        "max_score": 0,
        "pass_rate": 0,
        "case_count": max_cases,
        "summary": "MaaS branch was not run because Huawei MaaS is not configured.",
        "eval_dir": "",
        "eval_url": "",
        "maas_status": status,
        "files": [],
        "cases": [],
    }


def build_case_comparisons(
    local_result: dict[str, Any],
    maas_result: dict[str, Any],
    *,
    maas_ran: bool,
) -> list[dict[str, Any]]:
    maas_by_case = {case.get("case_id"): case for case in maas_result.get("cases", [])}
    comparisons = []
    for local_case in local_result.get("cases", []):
        case_id = local_case.get("case_id", "")
        maas_case = maas_by_case.get(case_id, {})
        maas_used = bool(maas_case.get("maas_used"))
        maas_status_value = maas_case.get("status", "skipped" if not maas_ran else "missing")
        score_delta = int(maas_case.get("score", 0)) - int(local_case.get("score", 0))
        local_passed = local_case.get("status") == "passed"
        maas_passed = maas_status_value == "passed"
        if not maas_ran:
            recommendation = "Configure MaaS, then rerun this case."
            status = "skipped"
        elif not maas_used:
            recommendation = "MaaS branch fell back locally; fix MaaS connectivity before judging model quality."
            status = "failed"
        elif local_passed and maas_passed and score_delta >= 0:
            recommendation = "MaaS output is acceptable for drafting under the current gates."
            status = "passed"
        elif maas_passed:
            recommendation = "MaaS output passed but scored lower; inspect artifact differences before adopting."
            status = "warning"
        else:
            recommendation = "Keep local fallback for this case until MaaS output passes the gates."
            status = "failed"
        comparisons.append({
            "case_id": case_id,
            "name": local_case.get("name", case_id),
            "status": status,
            "local": {
                "run_id": local_case.get("run_id", ""),
                "status": local_case.get("status", "unknown"),
                "score": local_case.get("score", 0),
                "max_score": local_case.get("max_score", 0),
                "run_url": local_case.get("run_url", ""),
            },
            "maas": {
                "run_id": maas_case.get("run_id", ""),
                "status": maas_status_value,
                "score": maas_case.get("score", 0),
                "max_score": maas_case.get("max_score", 0),
                "run_url": maas_case.get("run_url", ""),
                "maas_used": maas_used,
                "maas_error": maas_case.get("maas_error", ""),
            },
            "score_delta": score_delta,
            "recommendation": recommendation,
        })
    return comparisons


def build_comparison_metrics(
    local_result: dict[str, Any],
    maas_result: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    maas_ran: bool,
) -> dict[str, Any]:
    maas_cases = maas_result.get("cases", [])
    maas_used_count = sum(1 for case in maas_cases if case.get("maas_used"))
    passed_cases = sum(1 for case in cases if case["status"] == "passed")
    failed_cases = sum(1 for case in cases if case["status"] == "failed")
    warning_cases = sum(1 for case in cases if case["status"] == "warning")
    return {
        "case_count": len(cases),
        "local_score": local_result.get("score", 0),
        "local_max_score": local_result.get("max_score", 0),
        "maas_score": maas_result.get("score", 0),
        "maas_max_score": maas_result.get("max_score", 0),
        "score_delta": int(maas_result.get("score", 0)) - int(local_result.get("score", 0)),
        "maas_ran": maas_ran,
        "maas_used_case_count": maas_used_count,
        "maas_expected_case_count": len(maas_cases) if maas_ran else 0,
        "comparison_passed_cases": passed_cases,
        "comparison_warning_cases": warning_cases,
        "comparison_failed_cases": failed_cases,
        "cloud_execution_blocked": all(
            case.get("local", {}).get("status") in {"passed", "failed"}
            and case.get("maas", {}).get("status") in {"passed", "failed", "missing", "skipped"}
            for case in cases
        ),
    }


def build_comparison_verdict(
    local_result: dict[str, Any],
    maas_result: dict[str, Any],
    metrics: dict[str, Any],
    *,
    maas_ran: bool,
) -> dict[str, Any]:
    local_passed = local_result.get("status") == "passed"
    maas_passed = maas_result.get("status") == "passed"
    maas_used_all = (
        maas_ran
        and metrics["maas_expected_case_count"] > 0
        and metrics["maas_used_case_count"] == metrics["maas_expected_case_count"]
    )
    if not local_passed:
        return {
            "status": "failed",
            "passed": False,
            "summary": f"Local baseline failed: {local_result.get('summary', '')}",
            "recommendation": "Fix the local agent workflow before judging MaaS output.",
        }
    if not maas_ran:
        return {
            "status": "needs_maas",
            "passed": False,
            "summary": "Local baseline passed, but MaaS was not configured so the GLM-5.2 branch was skipped.",
            "recommendation": "Configure HUAWEI_MAAS_API_KEY and rerun the comparison.",
        }
    if not maas_used_all:
        return {
            "status": "maas_unavailable",
            "passed": False,
            "summary": (
                f"Local baseline passed, but MaaS was only used in {metrics['maas_used_case_count']}/"
                f"{metrics['maas_expected_case_count']} cases."
            ),
            "recommendation": "Check MaaS endpoint, API key, model name, and network connectivity before adopting MaaS output.",
        }
    if maas_passed and metrics["score_delta"] >= 0:
        return {
            "status": "passed",
            "passed": True,
            "summary": (
                f"Both branches passed. MaaS score {metrics['maas_score']}/{metrics['maas_max_score']} "
                f"vs local {metrics['local_score']}/{metrics['local_max_score']}."
            ),
            "recommendation": "MaaS can be used as the business-contract drafting branch, with existing review gates retained.",
        }
    if maas_passed:
        return {
            "status": "review_needed",
            "passed": False,
            "summary": "MaaS branch passed but scored lower than local fallback.",
            "recommendation": "Inspect artifact differences and tighten MaaS prompts before switching default generation.",
        }
    return {
        "status": "failed",
        "passed": False,
        "summary": f"MaaS branch did not pass: {maas_result.get('summary', '')}",
        "recommendation": "Keep local fallback as default until MaaS cases pass the evaluation suite.",
    }


def build_artifact_diff(local_result: dict[str, Any], maas_result: dict[str, Any]) -> list[dict[str, Any]]:
    maas_by_case = {case.get("case_id"): case for case in maas_result.get("cases", [])}
    diffs = []
    for local_case in local_result.get("cases", []):
        maas_case = maas_by_case.get(local_case.get("case_id"))
        if not maas_case:
            continue
        local_run_id = local_case.get("run_id", "")
        maas_run_id = maas_case.get("run_id", "")
        artifact_names = sorted(set(run_artifact_names(local_run_id)) | set(run_artifact_names(maas_run_id)))
        artifact_rows = []
        for name in artifact_names:
            local_text = read_artifact_text(local_run_id, name)
            maas_text = read_artifact_text(maas_run_id, name)
            artifact_rows.append({
                "name": name,
                "same_hash": hash_text(local_text) == hash_text(maas_text),
                "local_bytes": len(local_text.encode("utf-8")),
                "maas_bytes": len(maas_text.encode("utf-8")),
                "local_lines": line_count(local_text),
                "maas_lines": line_count(maas_text),
                "byte_delta": len(maas_text.encode("utf-8")) - len(local_text.encode("utf-8")),
                "line_delta": line_count(maas_text) - line_count(local_text),
            })
        diffs.append({
            "case_id": local_case.get("case_id", ""),
            "local_run_id": local_run_id,
            "maas_run_id": maas_run_id,
            "artifacts": artifact_rows,
        })
    return diffs


def run_artifact_names(run_id: str) -> list[str]:
    if not run_id:
        return []
    manifest_path = APP_ROOT / "generated" / run_id / "run_manifest.json"
    if not manifest_path.exists():
        return []
    manifest = read_json(manifest_path)
    return [artifact.get("name", "") for artifact in manifest.get("artifacts", []) if artifact.get("name")]


def read_artifact_text(run_id: str, name: str) -> str:
    if not run_id or not name:
        return ""
    path = APP_ROOT / "generated" / run_id / "artifacts" / Path(name).name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def comparison_eval_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_id": result.get("eval_id", ""),
        "status": result.get("status", "unknown"),
        "passed": bool(result.get("passed")),
        "score": result.get("score", 0),
        "max_score": result.get("max_score", 0),
        "pass_rate": result.get("pass_rate", 0),
        "case_count": result.get("case_count", 0),
        "summary": result.get("summary", ""),
        "eval_url": result.get("eval_url", ""),
    }


def comparison_response(summary: dict[str, Any]) -> dict[str, Any]:
    comparison_id = summary["comparison_id"]
    return {
        "comparison_id": comparison_id,
        "status": summary["status"],
        "passed": summary["passed"],
        "summary": summary["summary"],
        "recommendation": summary["recommendation"],
        "comparison_dir": str(EVALUATIONS_ROOT / comparison_id),
        "comparison_url": f"/evaluations/{comparison_id}/comparison_report.md",
        "local": summary["local"],
        "maas": summary["maas"],
        "metrics": summary["metrics"],
        "files": summary["files"],
        "cases": summary["cases"],
    }


def comparison_file_entry(comparison_id: str, name: str, description: str) -> dict[str, str]:
    path = EVALUATIONS_ROOT / comparison_id / name
    url_name = name.replace("\\", "/")
    return {
        "name": name,
        "description": description,
        "path": str(path.relative_to(APP_ROOT)).replace("\\", "/"),
        "url": f"/evaluations/{comparison_id}/{url_name}",
    }


def render_comparison_report(
    summary: dict[str, Any],
    local_result: dict[str, Any],
    maas_result: dict[str, Any],
    artifact_diff: list[dict[str, Any]],
) -> str:
    lines = [
        "# Local vs MaaS Evaluation Comparison",
        "",
        f"- comparison_id: {summary['comparison_id']}",
        f"- status: {summary['status']}",
        f"- passed: {summary['passed']}",
        f"- maas_model: {summary.get('maas_model', '')}",
        f"- summary: {summary['summary']}",
        f"- recommendation: {summary['recommendation']}",
        "",
        "## Branch Scores",
        "",
        "| Branch | Status | Score | Cases | Source |",
        "|---|---|---:|---:|---|",
        (
            f"| Local fallback | {local_result.get('status', 'unknown')} | "
            f"{local_result.get('score', 0)}/{local_result.get('max_score', 0)} | "
            f"{local_result.get('case_count', 0)} | {local_result.get('eval_url', '')} |"
        ),
        (
            f"| GLM-5.2 MaaS | {maas_result.get('status', 'unknown')} | "
            f"{maas_result.get('score', 0)}/{maas_result.get('max_score', 0)} | "
            f"{maas_result.get('case_count', 0)} | {maas_result.get('eval_url', '')} |"
        ),
        "",
        "## Case Comparison",
        "",
        "| Case | Status | Local | MaaS | Delta | Recommendation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for case in summary["cases"]:
        lines.append(
            "| "
            + " | ".join([
                str(case["name"]).replace("|", "\\|"),
                case["status"],
                f"{case['local']['score']}/{case['local']['max_score']}",
                f"{case['maas']['score']}/{case['maas']['max_score']}",
                str(case["score_delta"]),
                str(case["recommendation"]).replace("|", "\\|"),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## Artifact Differences",
        "",
    ])
    if not artifact_diff:
        lines.append("No MaaS artifact diff was generated because the MaaS branch did not run.")
    else:
        for item in artifact_diff:
            lines.extend([
                f"### {item['case_id']}",
                "",
                "| Artifact | Same Hash | Local Bytes | MaaS Bytes | Byte Delta |",
                "|---|---|---:|---:|---:|",
            ])
            for artifact in item["artifacts"]:
                lines.append(
                    f"| {artifact['name']} | {artifact['same_hash']} | "
                    f"{artifact['local_bytes']} | {artifact['maas_bytes']} | {artifact['byte_delta']} |"
                )
            lines.append("")
    lines.extend([
        "",
        "## Controls",
        "",
        "- DataArts, MRS, OBS, and DWS execution remain blocked.",
        "- MaaS credentials are read only from environment or ignored local env files.",
        "- Review gates remain mandatory even when MaaS output passes.",
    ])
    return "\n".join(lines)


def capture_failure_samples(
    *,
    comparison_id: str,
    summary: dict[str, Any],
    local_result: dict[str, Any],
    maas_result: dict[str, Any],
    artifact_diff: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failed_cases = [case for case in summary.get("cases", []) if case.get("status") != "passed"]
    if not failed_cases:
        return []

    FAILURES_ROOT.mkdir(parents=True, exist_ok=True)
    local_by_case = {case.get("case_id"): case for case in local_result.get("cases", [])}
    maas_by_case = {case.get("case_id"): case for case in maas_result.get("cases", [])}
    diff_by_case = {item.get("case_id"): item for item in artifact_diff}
    samples = []
    for case in failed_cases:
        case_id = case.get("case_id", "unknown_case")
        failure_id = f"{comparison_id}-{case_id}"
        case_dir = FAILURES_ROOT / safe_eval_name(case_id) / safe_eval_name(failure_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        local_case = local_by_case.get(case_id, {})
        maas_case = maas_by_case.get(case_id, {})
        prompt_case = eval_case_by_id(case_id)
        local_run_id = local_case.get("run_id", "")
        maas_run_id = maas_case.get("run_id", "")
        payload = {
            "failure_id": failure_id,
            "source_comparison_id": comparison_id,
            "case_id": case_id,
            "name": case.get("name", case_id),
            "scenario": prompt_case.get("scenario", case.get("scenario", "")),
            "prompt": prompt_case.get("prompt", ""),
            "captured_at": now_iso(),
            "local": case.get("local", {}),
            "maas": case.get("maas", {}),
            "comparison_status": summary.get("status"),
            "score_delta": case.get("score_delta", 0),
            "recommendation": case.get("recommendation", ""),
            "local_failed_checks": failed_check_details(local_case),
            "maas_failed_checks": failed_check_details(maas_case),
            "artifact_diff": diff_by_case.get(case_id, {}),
            "diagnosis": diagnose_failure(case, local_case, maas_case),
        }
        write_json(case_dir / "failure.json", payload)
        (case_dir / "local_business_contract.yaml").write_text(
            read_artifact_text(local_run_id, "business_contract.yaml"),
            encoding="utf-8",
        )
        (case_dir / "maas_business_contract.yaml").write_text(
            read_artifact_text(maas_run_id, "business_contract.yaml"),
            encoding="utf-8",
        )
        (case_dir / "diagnosis.md").write_text(render_failure_diagnosis(payload), encoding="utf-8")
        samples.append(failure_sample_entry(case_id, failure_id, payload))
    return samples


def list_failure_samples() -> list[dict[str, Any]]:
    ensure_failure_samples_from_existing_comparisons()
    items = []
    for path in sorted(FAILURES_ROOT.glob("*/*/failure.json"), reverse=True):
        try:
            payload = read_json(path)
        except json.JSONDecodeError:
            continue
        items.append(failure_sample_entry(
            payload.get("case_id", path.parent.parent.name),
            payload.get("failure_id", path.parent.name),
            payload,
        ))
    return items


def ensure_failure_samples_from_existing_comparisons() -> None:
    for summary_path in sorted(EVALUATIONS_ROOT.glob("compare-*/summary.json")):
        try:
            summary = read_json(summary_path)
        except json.JSONDecodeError:
            continue
        if summary.get("status") == "passed":
            continue
        comparison_id = summary.get("comparison_id", summary_path.parent.name)
        failed_cases = [case for case in summary.get("cases", []) if case.get("status") != "passed"]
        missing = [
            case
            for case in failed_cases
            if not (FAILURES_ROOT / safe_eval_name(case.get("case_id", "unknown_case")) / safe_eval_name(f"{comparison_id}-{case.get('case_id', 'unknown_case')}") / "failure.json").exists()
        ]
        if not missing:
            continue
        local_path = summary_path.parent / "local" / "summary.json"
        maas_path = summary_path.parent / "maas" / "summary.json"
        diff_path = summary_path.parent / "artifact_diff.json"
        if not local_path.exists() or not maas_path.exists() or not diff_path.exists():
            continue
        capture_failure_samples(
            comparison_id=comparison_id,
            summary=summary,
            local_result=read_json(local_path),
            maas_result=read_json(maas_path),
            artifact_diff=read_json(diff_path),
        )


async def replay_failure_samples(request: FailureReplayRequest) -> dict[str, Any]:
    samples = list_failure_samples()[: request.max_failures]
    replay_id = f"replay-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    replay_dir = EVALUATIONS_ROOT / replay_id
    replay_dir.mkdir(parents=True, exist_ok=True)
    if not samples:
        summary = {
            "replay_id": replay_id,
            "status": "skipped",
            "passed": False,
            "summary": "No failure samples are available for replay.",
            "case_count": 0,
            "cases": [],
            "files": [],
        }
        write_json(replay_dir / "case_results.json", [])
        write_json(replay_dir / "summary.json", summary)
        (replay_dir / "replay_report.md").write_text(render_replay_report(summary), encoding="utf-8")
        summary["files"] = replay_files(replay_id)
        write_json(replay_dir / "summary.json", summary)
        return replay_response(summary)

    replay_cases = []
    for index, sample in enumerate(samples, start=1):
        sample_payload = read_json(APP_ROOT / sample["path"])
        case = {
            "id": sample_payload["case_id"],
            "name": sample_payload.get("name", sample_payload["case_id"]),
            "scenario": sample_payload["scenario"],
            "prompt": sample_payload["prompt"],
        }
        result = await run_eval_case(case, index=index, use_maas=True)
        replay_cases.append({
            **result,
            "failure_id": sample_payload["failure_id"],
            "source_comparison_id": sample_payload.get("source_comparison_id", ""),
            "previous_status": sample_payload.get("comparison_status", ""),
            "previous_recommendation": sample_payload.get("recommendation", ""),
        })

    failed = [case for case in replay_cases if case["status"] != "passed"]
    score = sum(case["score"] for case in replay_cases)
    max_score = sum(case["max_score"] for case in replay_cases)
    summary = {
        "replay_id": replay_id,
        "status": "passed" if not failed else "failed",
        "passed": not failed,
        "summary": f"{len(replay_cases) - len(failed)}/{len(replay_cases)} failure samples replayed successfully; {score}/{max_score} checks passed.",
        "case_count": len(replay_cases),
        "score": score,
        "max_score": max_score,
        "started_at": replay_cases[0].get("started_at") if replay_cases else now_iso(),
        "completed_at": now_iso(),
        "cases": replay_cases,
        "files": replay_files(replay_id),
    }
    write_json(replay_dir / "case_results.json", replay_cases)
    write_json(replay_dir / "summary.json", summary)
    (replay_dir / "replay_report.md").write_text(render_replay_report(summary), encoding="utf-8")
    return replay_response(summary)


def replay_response(summary: dict[str, Any]) -> dict[str, Any]:
    replay_id = summary["replay_id"]
    return {
        "replay_id": replay_id,
        "status": summary["status"],
        "passed": summary["passed"],
        "summary": summary["summary"],
        "replay_dir": str(EVALUATIONS_ROOT / replay_id),
        "replay_url": f"/evaluations/{replay_id}/replay_report.md",
        "files": summary.get("files", replay_files(replay_id)),
        "cases": summary.get("cases", []),
    }


def replay_files(replay_id: str) -> list[dict[str, str]]:
    return [
        evaluation_file_entry(replay_id, "summary.json", "Machine-readable failure replay summary."),
        evaluation_file_entry(replay_id, "replay_report.md", "Human-readable failure replay report."),
        evaluation_file_entry(replay_id, "case_results.json", "Per-case replay results."),
    ]


def render_replay_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Failure Replay Report",
        "",
        f"- replay_id: {summary['replay_id']}",
        f"- status: {summary['status']}",
        f"- summary: {summary['summary']}",
        "",
        "| Failure | Case | Status | Score | MaaS Used |",
        "|---|---|---|---:|---|",
    ]
    for case in summary.get("cases", []):
        lines.append(
            f"| {case.get('failure_id', '')} | {case.get('name', case.get('case_id', ''))} | "
            f"{case.get('status', '')} | {case.get('score', 0)}/{case.get('max_score', 0)} | "
            f"{case.get('maas_used', False)} |"
        )
    lines.extend([
        "",
        "## Controls",
        "",
        "- Replays use MaaS only for local contract generation validation.",
        "- DataArts, MRS, OBS, and DWS execution remain blocked.",
    ])
    return "\n".join(lines)


def get_pre_execution_readiness(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    status = read_optional_json(run_dir / PRE_EXECUTION_DIR_NAME / PRE_EXECUTION_STATUS_NAME)
    if status:
        return pre_execution_response(run_id, status)
    return build_pre_execution_readiness(run_id, persist=False)


def create_pre_execution_readiness(run_id: str) -> dict[str, Any]:
    return build_pre_execution_readiness(run_id, persist=True)


def build_pre_execution_readiness(run_id: str, *, persist: bool) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    report_dir = run_dir / PRE_EXECUTION_DIR_NAME
    if persist:
        report_dir.mkdir(parents=True, exist_ok=True)

    context = build_resource_creation_context(run_id, run_dir)
    artifacts = build_resource_creation_artifacts(run_id, context)
    gates = build_resource_creation_gates(context)
    if persist:
        for name, payload in artifacts["json"].items():
            write_json(report_dir / name, payload)
        for name, text in artifacts["markdown"].items():
            (report_dir / name).write_text(text, encoding="utf-8")

    ready = all(gate["ready"] for gate in gates)
    passed_count = sum(1 for gate in gates if gate["ready"])
    summary = (
        f"{passed_count}/8 real-resource-creation preparation gates passed. "
        + (
            "Next step: create real Huawei Cloud resources after explicit operator approval."
            if ready
            else "Resolve blocked preparation gates before creating real Huawei Cloud resources."
        )
    )
    payload = {
        "run_id": run_id,
        "status": "ready_for_real_resource_creation" if ready else "blocked",
        "ready_for_execution_layer": ready,
        "cloud_execution": "blocked",
        "summary": summary,
        "generated_at": now_iso(),
        "gates": gates,
        "files": pre_execution_files(run_id) if persist else [],
        "next_action": (
            "Create real Huawei Cloud resources. This still requires an explicit operator approval and cloud credentials at action time."
            if ready
            else "Resolve blocked preparation gates before moving to resource creation."
        ),
        "resource_creation": {
            "ready": ready,
            "mode": "create_new_resources",
            "cloud_resource_creation": "blocked_until_explicit_operator_approval",
            "next_step_when_approved": "create_real_huawei_cloud_resources",
        },
    }
    if persist:
        write_json(report_dir / PRE_EXECUTION_STATUS_NAME, payload)
        (report_dir / "pre_execution_report.md").write_text(render_pre_execution_report(payload), encoding="utf-8")
        payload["files"] = pre_execution_files(run_id)
        write_json(report_dir / PRE_EXECUTION_STATUS_NAME, payload)
    return pre_execution_response(run_id, payload)


def build_resource_creation_context(run_id: str, run_dir: Path) -> dict[str, Any]:
    release = get_release_package_status(run_id)
    release_dir = run_dir / "release"
    release_manifest = read_optional_json(release_dir / "release_manifest.json") or {}
    deployment_preflight = read_optional_json(release_dir / "deployment_preflight.json") or {}
    cloud_probe = read_optional_json(run_dir / "cloud_resource_probe_status.json") or release_manifest.get("cloud_resource_probe", {})
    standardization = read_optional_json(run_dir / "dataarts_standard_status.json") or release_manifest.get("dataarts_standardization", {})
    run_manifest = read_optional_json(run_dir / "run_manifest.json") or {}
    request = read_optional_json(run_dir / "request.json") or {}
    environment = release_manifest.get("environment", {})
    cloud_parameters = environment.get("cloud_parameters", {})
    approved_artifacts = release_manifest.get("approved_artifacts", release.get("release", {}).get("approved_artifacts", []))
    preflight_failed = int(deployment_preflight.get("failed", 0) or 0)
    release_ready = release.get("status") == "generated" and bool(release.get("ready"))
    standard_ready = bool(standardization.get("ready_for_cloud_probe")) or standardization.get("status") == "standardized"
    validation_ready = bool(cloud_probe.get("ready_for_operator_execution_request"))
    base_ready = release_ready and standard_ready and validation_ready and preflight_failed == 0
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "release_dir": release_dir,
        "release": release,
        "release_manifest": release_manifest,
        "deployment_preflight": deployment_preflight,
        "cloud_probe": cloud_probe,
        "standardization": standardization,
        "run_manifest": run_manifest,
        "request": request,
        "environment": environment,
        "cloud_parameters": cloud_parameters,
        "approved_artifacts": approved_artifacts,
        "base_ready": base_ready,
        "base_blockers": resource_creation_base_blockers(release_ready, standard_ready, validation_ready, preflight_failed),
        "generated_at": now_iso(),
    }


def resource_creation_base_blockers(
    release_ready: bool,
    standard_ready: bool,
    validation_ready: bool,
    preflight_failed: int,
) -> list[str]:
    blockers = []
    if not release_ready:
        blockers.append("release package is not generated or approvals are incomplete")
    if not standard_ready:
        blockers.append("DataArts standard package is not ready")
    if not validation_ready:
        blockers.append("existing-resource read-only validation package is not ready for operator review")
    if preflight_failed:
        blockers.append(f"deployment preflight has {preflight_failed} failed checks")
    return blockers


def build_resource_creation_artifacts(run_id: str, context: dict[str, Any]) -> dict[str, dict[str, Any] | dict[str, str]]:
    environment = context["environment"]
    cloud_parameters = context["cloud_parameters"]
    generated_at = context["generated_at"]
    region = environment.get("region", "la-south-2")
    storage_layers = environment.get("storage_layers", ["raw", "silver", "gold", "release", "audit"])
    missing = context["base_blockers"]

    mode_decision = {
        "schema": "tax.agentic.environment_mode_decision.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "selected_mode": "create_new_resources",
        "available_modes": ["bind_existing_resources", "create_new_resources"],
        "decision_reason": "The remaining path before real execution is to create a governed Huawei Cloud POC environment.",
        "not_selected": {
            "bind_existing_resources": "The app already has a read-only validation path for existing resources. This package prepares the new-resource path.",
        },
        "cloud_resource_creation": "blocked_until_explicit_operator_approval",
        "base_blockers": missing,
    }

    target_environment = {
        "schema": "tax.agentic.target_environment_definition.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "account_scope": {
            "environment_type": "poc",
            "region": region,
            "project_id": "<fill-HUAWEICLOUD_PROJECT_ID>",
            "isolation": "dedicated VPC and private subnet for the Agentic Tax Bigdata Demo",
        },
        "network_boundary": {
            "vpc": "create dedicated VPC unless an approved shared VPC is supplied",
            "subnet": "private subnet for MRS, DWS, DataArts access paths",
            "public_ingress": "disabled for big-data services",
            "security_groups": "deny public MRS/DWS ports; allow only approved operator and managed-service paths",
        },
        "naming_and_tags": {
            "prefix": f"agentic-tax-{run_id}",
            "tags": {
                "project": "agentic-tax-bigdata-demo",
                "run_id": run_id,
                "owner": "cloud_operator",
                "lifecycle": "poc",
            },
        },
    }

    data_compliance = {
        "schema": "tax.agentic.data_compliance_classification.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "data_domain": "Tax taxpayer analytics",
        "classification": "sensitive regulated data with taxpayer identifiers in raw processing scope",
        "pii_controls": [
            "direct RFC must not leave raw processing scope",
            "gold, DWS, UI, and generated artifacts use aggregate metrics, masked identifiers, or hashes only",
            "sample data remains synthetic until a separate data-ingestion approval exists",
        ],
        "encryption": {
            "obs": "DEW/KMS encryption required",
            "dws": "encrypted storage required",
            "kms_key": cloud_parameters.get("KMS_KEY_ID", "<fill-KMS_KEY_ID>"),
        },
        "retention": {
            "raw": "archive or purge after validation window",
            "audit": "retain for governance review",
            "release": "retain generated package evidence",
        },
        "audit_evidence": [
            "lineage_manifest.json",
            "security_review.md",
            "cloud_readonly_verification_checklist.md",
            "real_resource_creation_approval_request.md",
        ],
    }

    blueprint = {
        "schema": "tax.agentic.cloud_provisioning_blueprint.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "region": region,
        "resource_mode": "create_new_resources",
        "resources": {
            "vpc": {"action": "create", "shape": "one VPC, one private subnet, restrictive security groups"},
            "obs": {
                "action": "create",
                "storage_class": "Standard",
                "layers": storage_layers,
                "encryption": "DEW_KMS",
                "lifecycle": "raw archive after validation; audit retained",
            },
            "mrs": {"action": "create", "engine": "Spark/Hive", "size": "small POC cluster; exact flavor verified in console"},
            "dws": {"action": "create", "size": "smallest region-supported POC shape; not production sizing"},
            "dataarts": {"action": "create_or_select_workspace", "schedules": "disabled until execution window approval"},
            "kms": {"action": "create_or_select_key", "usage": "OBS/DWS encryption and audit evidence"},
            "monitoring": {"action": "configure", "signals": ["obs_bytes", "mrs_cleaned_rows", "dws_loaded_rows", "error_count"]},
        },
        "artifacts_to_deploy_after_creation": context["approved_artifacts"],
        "cloud_resource_creation": "blocked_until_explicit_operator_approval",
    }

    cost_quota = {
        "schema": "tax.agentic.cost_quota_review.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "policy": "POC pay-per-use only unless operator approves another billing mode",
        "quota_checks_before_apply": [
            "VPC/subnet/security group quotas in target project",
            "OBS bucket quota and KMS availability",
            "MRS cluster quota and exact POC flavor availability",
            "DWS cluster quota and minimum node shape availability",
            "DataArts workspace availability in target region",
        ],
        "cost_controls": [
            "smallest POC shapes",
            "lifecycle destroy plan required before creation",
            "budget owner must approve estimated daily cost",
            "no production-sized cluster without a separate production sizing document",
        ],
        "manual_console_verification_required": True,
    }

    iam_strategy = {
        "schema": "tax.agentic.iam_key_strategy.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "principles": ["least privilege", "separate read-only validation role from resource creation role", "no secrets in generated files"],
        "roles": {
            "readonly_validator": ["VPC list/show", "OBS metadata/list", "MRS show", "DWS list/show", "KMS list", "DataArts list"],
            "resource_creator": ["create tagged POC resources only after approval", "attach approved KMS key", "configure restrictive security groups"],
            "execution_operator": ["submit MRS/DataArts/DWS work only during approved execution window"],
        },
        "credential_handling": {
            "ak_sk": "operator shell or secret manager only",
            "database_passwords": "operator shell or cloud secret service only",
            "generated_files": "must contain no credential values",
        },
    }

    iac_state = {
        "schema": "tax.agentic.iac_state_management_plan.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "iac_tool": "Terraform or Huawei Cloud CLI wrapper",
        "state_policy": {
            "backend": "operator-approved remote state or encrypted local state for POC",
            "lock": "single operator lock before apply",
            "naming_prefix": f"agentic-tax-{run_id}",
            "tags_required": True,
        },
        "files_to_generate_next": [
            "terraform/main.tf",
            "terraform/variables.tf",
            "terraform/outputs.tf",
            "scripts/create_resources.ps1",
            "scripts/destroy_resources.ps1",
        ],
        "destroy_required_before_create": True,
    }

    dry_run = {
        "schema": "tax.agentic.iac_dry_run_plan.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "dry_run_status": "planned_locally",
        "commands_allowed_before_approval": ["terraform fmt", "terraform validate", "terraform plan -out planfile"],
        "commands_blocked_until_approval": ["terraform apply", "resource creation API calls", "DataArts import", "MRS submit", "DWS SQL execution"],
        "plan_preview": [
            "create VPC and private subnet",
            "create OBS bucket/layer prefixes with KMS encryption",
            "create or select KMS key",
            "create small MRS Spark/Hive POC cluster",
            "create small DWS POC cluster",
            "create or select DataArts workspace and disabled jobs",
            "write monitoring and audit destinations",
        ],
        "ready_to_request_creation": context["base_ready"],
        "base_blockers": missing,
    }

    approval_text = render_real_resource_creation_approval_request(
        run_id=run_id,
        generated_at=generated_at,
        ready=context["base_ready"],
        blockers=missing,
    )
    destroy_text = render_destroy_plan(run_id, generated_at, blueprint)

    return {
        "json": {
            "environment_mode_decision.json": mode_decision,
            "target_environment_definition.json": target_environment,
            "data_compliance_classification.json": data_compliance,
            "cloud_provisioning_blueprint.json": blueprint,
            "cost_quota_iam_review.json": cost_quota,
            "iam_key_strategy.json": iam_strategy,
            "iac_state_management_plan.json": iac_state,
            "iac_dry_run_plan.json": dry_run,
        },
        "markdown": {
            "destroy_plan.md": destroy_text,
            "real_resource_creation_approval_request.md": approval_text,
        },
    }


def build_resource_creation_gates(context: dict[str, Any]) -> list[dict[str, Any]]:
    base_ready = bool(context["base_ready"])
    blockers = context["base_blockers"]

    def gate(step: int, gate_id: str, name: str, summary: str, file_name: str) -> dict[str, Any]:
        return {
            "id": gate_id,
            "step": step,
            "name": name,
            "status": "passed" if base_ready else "blocked",
            "ready": base_ready,
            "summary": summary if base_ready else f"Blocked by: {', '.join(blockers)}",
            "evidence": {
                "file": f"/generated/{context['run_id']}/{PRE_EXECUTION_DIR_NAME}/{file_name}",
                "cloud_resource_creation": "blocked_until_explicit_operator_approval",
            },
        }

    return [
        gate(1, "RC-001", "Environment mode decision", "Mode selected: create new governed Huawei Cloud POC resources.", "environment_mode_decision.json"),
        gate(2, "RC-002", "Target environment definition", "Target account, region, network boundary, naming, and tags are defined.", "target_environment_definition.json"),
        gate(3, "RC-003", "Data and compliance classification", "Tax taxpayer data controls, RFC masking, encryption, retention, and audit rules are defined.", "data_compliance_classification.json"),
        gate(4, "RC-004", "Cloud resource blueprint", "OBS, MRS, DWS, DataArts, KMS, network, and monitoring blueprint is ready.", "cloud_provisioning_blueprint.json"),
        gate(5, "RC-005", "Cost, quota, and sizing review", "POC cost guardrails, quota checks, and small-shape policy are packaged.", "cost_quota_iam_review.json"),
        gate(6, "RC-006", "IAM and key strategy", "Read-only, creator, and execution roles are separated; secrets stay outside generated files.", "iam_key_strategy.json"),
        gate(7, "RC-007", "IaC and state management", "IaC state, naming, tagging, lock, and destroy requirements are defined.", "iac_state_management_plan.json"),
        gate(8, "RC-008", "IaC dry-run and creation approval", "Dry-run plan, blocked apply commands, destroy plan, and creation approval request are ready.", "iac_dry_run_plan.json"),
    ]


def render_real_resource_creation_approval_request(
    *,
    run_id: str,
    generated_at: str,
    ready: bool,
    blockers: list[str],
) -> str:
    blocker_text = "\n".join(f"- {item}" for item in blockers) or "- None"
    decision = (
        "Preparation complete. The next step is to create real Huawei Cloud resources after explicit operator approval."
        if ready
        else "Do not create resources until blockers are resolved."
    )
    return f"""# Real Huawei Cloud Resource Creation Approval Request

- run_id: {run_id}
- generated_at: {generated_at}
- ready_for_real_resource_creation: {str(ready).lower()}
- cloud_resource_creation: blocked_until_explicit_operator_approval
- cloud_execution: blocked

## Decision

{decision}

## Scope To Create

- Dedicated POC VPC, private subnet, and restrictive security groups.
- OBS bucket or approved bucket paths for raw, silver, gold, release, and audit layers.
- DEW/KMS key or approved key binding.
- Small POC MRS Spark/Hive cluster.
- Small POC DWS cluster.
- DataArts workspace or approved workspace with schedules disabled.
- Monitoring and audit evidence destinations.

## Explicitly Not Approved Here

- No DataArts import execution.
- No MRS job submission.
- No DWS SQL execution.
- No production data ingestion.
- No public exposure of big-data service ports.
- No credential values in generated files.

## Blockers

{blocker_text}

## Required Approval

A named cloud operator must approve the resource creation window, budget owner, quota confirmation, IAM role, rollback owner, and destroy deadline before any `terraform apply`, CLI create call, or cloud-console resource creation.
"""


def render_destroy_plan(run_id: str, generated_at: str, blueprint: dict[str, Any]) -> str:
    resources = "\n".join(f"- {name}: {spec.get('action')} {spec.get('shape', spec.get('size', spec.get('usage', '')))}" for name, spec in blueprint.get("resources", {}).items())
    return f"""# Destroy Plan

- run_id: {run_id}
- generated_at: {generated_at}
- applies_to: real Huawei Cloud POC resources created from `cloud_provisioning_blueprint.json`

## Resources Covered

{resources}

## Required Before Creation

1. Record the owner responsible for cleanup.
2. Record the maximum POC lifetime.
3. Confirm audit evidence paths are preserved before deleting compute resources.
4. Confirm OBS raw/gold/audit retention policy before deleting buckets or prefixes.
5. Keep IaC state available until all resources are verified destroyed.

## Destroy Order

1. Disable DataArts schedules and imports.
2. Stop or delete MRS jobs and clusters.
3. Unload or snapshot DWS evidence if needed, then delete DWS POC resources.
4. Archive or delete OBS layer prefixes according to retention policy.
5. Remove security groups, private subnet, and VPC after dependent resources are gone.
6. Retire KMS keys only according to the approved key lifecycle.
"""


def build_maas_reliability_gate() -> dict[str, Any]:
    status = maas_status()
    comparison = latest_summary("compare-*")
    replay = latest_summary("replay-*")
    metrics = comparison.get("metrics", {})
    expected = int(metrics.get("maas_expected_case_count") or comparison.get("case_count") or 0)
    used = int(metrics.get("maas_used_case_count") or 0)
    comparison_passed = bool(comparison.get("passed")) and expected > 0 and used == expected
    replay_passed = bool(replay.get("passed"))

    if not status.get("configured"):
        gate_status = "blocked"
        summary = "MaaS is not configured. Set MaaS environment variables before judging agent output."
    elif comparison_passed:
        gate_status = "passed"
        summary = f"Latest Local vs MaaS comparison passed and used MaaS in {used}/{expected} cases."
    elif replay_passed:
        gate_status = "warning"
        summary = (
            "Failure replay passed, but the latest full Local vs MaaS comparison is not clean. "
            "Rerun the comparison before real execution."
        )
    else:
        gate_status = "blocked"
        summary = "No clean Local vs MaaS comparison is available."

    return {
        "id": "maas_reliability_judge",
        "step": 1,
        "name": "MaaS Agent reliability judge",
        "status": gate_status,
        "ready": comparison_passed,
        "summary": summary,
        "evidence": {
            "maas_configured": bool(status.get("configured")),
            "model": status.get("model"),
            "comparison_id": comparison.get("comparison_id", ""),
            "comparison_status": comparison.get("status", ""),
            "comparison_url": f"/evaluations/{comparison.get('comparison_id')}/comparison_report.md" if comparison.get("comparison_id") else "",
            "maas_used_cases": used,
            "maas_expected_cases": expected,
            "replay_id": replay.get("replay_id", ""),
            "replay_status": replay.get("status", ""),
            "replay_url": f"/evaluations/{replay.get('replay_id')}/replay_report.md" if replay.get("replay_id") else "",
        },
    }


def build_business_contract_freeze_gate(
    run_id: str,
    run_dir: Path,
    report_dir: Path,
    *,
    persist: bool,
) -> dict[str, Any]:
    release = get_release_package_status(run_id)
    manifest = read_json(run_dir / "run_manifest.json")
    review = read_json(run_dir / "review_status.json")
    artifacts = manifest.get("artifacts", [])
    artifact_hashes = [
        {
            "name": artifact["name"],
            "kind": artifact["kind"],
            "sha256": file_sha256(APP_ROOT / artifact["path"]),
        }
        for artifact in artifacts
    ]
    contract_hash = next((item["sha256"] for item in artifact_hashes if item["name"] == "business_contract.yaml"), "")
    ready = release.get("status") == "generated" and bool(release.get("ready"))
    freeze = {
        "run_id": run_id,
        "status": "frozen" if ready else "blocked",
        "freeze_id": sha256(f"{run_id}:{contract_hash}:{review.get('updated_at', '')}".encode("utf-8")).hexdigest()[:16],
        "generated_at": now_iso(),
        "contract_hash": contract_hash,
        "artifact_hashes": artifact_hashes,
        "review_updated_at": review.get("updated_at"),
        "approved_artifacts": release.get("release", {}).get("approved_artifacts", []),
        "missing_approvals": release.get("missing_approvals", []),
        "failed_gates": release.get("failed_gates", []),
        "cloud_execution": "blocked",
    }
    if persist:
        write_json(report_dir / "business_contract_freeze.json", freeze)
    return {
        "id": "business_contract_freeze",
        "step": 2,
        "name": "Business contract freeze",
        "status": "passed" if ready else "blocked",
        "ready": ready,
        "summary": (
            f"Contract frozen with freeze_id {freeze['freeze_id']}."
            if ready
            else "Release package is not generated or approvals are incomplete."
        ),
        "evidence": {
            "freeze_id": freeze["freeze_id"],
            "contract_hash": contract_hash,
            "release_status": release.get("status"),
            "file": f"/generated/{run_id}/{PRE_EXECUTION_DIR_NAME}/business_contract_freeze.json" if persist else "",
        },
    }


def build_execution_sandbox_gate(
    run_id: str,
    run_dir: Path,
    report_dir: Path,
    *,
    persist: bool,
) -> dict[str, Any]:
    local_execution = read_optional_json(run_dir / "local_execution.json") or {}
    quality_gates = read_optional_json(run_dir / "quality_gates.json") or []
    failed_gates = [gate for gate in quality_gates if gate.get("status") == "failed"]
    execution_status = local_execution.get("status", "missing")
    metric = local_execution.get("metric_reconciliation", {})
    ready = execution_status == "passed" and not failed_gates
    sandbox = {
        "run_id": run_id,
        "status": "passed" if ready else "blocked",
        "generated_at": now_iso(),
        "local_execution_status": execution_status,
        "metric_reconciliation": metric,
        "execution_report": local_execution.get("execution_report", {}),
        "failed_gates": failed_gates,
        "cloud_execution": "blocked",
    }
    if persist:
        write_json(report_dir / "execution_sandbox_summary.json", sandbox)
    return {
        "id": "execution_sandbox",
        "step": 3,
        "name": "Execution sandbox",
        "status": "passed" if ready else "blocked",
        "ready": ready,
        "summary": (
            metric.get("summary") or "Local dry-run and metric reconciliation passed."
            if ready
            else "Local dry-run or quality gates are not clean."
        ),
        "evidence": {
            "local_execution_status": execution_status,
            "failed_gate_count": len(failed_gates),
            "file": f"/generated/{run_id}/{PRE_EXECUTION_DIR_NAME}/execution_sandbox_summary.json" if persist else "",
        },
    }


def build_cloud_import_dry_run_gate(run_id: str, report_dir: Path, *, persist: bool) -> dict[str, Any]:
    release = get_release_package_status(run_id)
    binding = get_cloud_binding_status(run_id)
    review = get_import_review_status(run_id)
    ready = bool(binding.get("ready_for_import_review")) and bool(review.get("ready_for_operator_handoff"))
    dry_run = {
        "run_id": run_id,
        "status": "passed" if ready else "blocked",
        "generated_at": now_iso(),
        "release_status": release.get("status"),
        "cloud_binding_status": binding.get("status"),
        "import_review_status": review.get("status"),
        "ready_for_operator_handoff": review.get("ready_for_operator_handoff"),
        "cloud_execution": "blocked",
        "binding": binding.get("binding", {}),
        "import_review": review.get("review", {}),
    }
    if persist:
        write_json(report_dir / "cloud_import_dry_run.json", dry_run)
    return {
        "id": "cloud_import_dry_run",
        "step": 4,
        "name": "Cloud import dry-run handoff",
        "status": "passed" if ready else "blocked",
        "ready": ready,
        "summary": (
            "DataArts import handoff is ready; cloud execution remains locked."
            if ready
            else "Generate release, cloud binding simulation, and import review before cloud handoff."
        ),
        "evidence": {
            "release_status": release.get("status"),
            "cloud_binding_status": binding.get("status"),
            "import_review_status": review.get("status"),
            "file": f"/generated/{run_id}/{PRE_EXECUTION_DIR_NAME}/cloud_import_dry_run.json" if persist else "",
        },
    }


def pre_execution_response(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": payload.get("status", "blocked"),
        "ready_for_execution_layer": bool(payload.get("ready_for_execution_layer")),
        "cloud_execution": payload.get("cloud_execution", "blocked"),
        "summary": payload.get("summary", ""),
        "report_dir": str(resolve_existing_run_dir(run_id) / PRE_EXECUTION_DIR_NAME),
        "report_url": f"/generated/{run_id}/{PRE_EXECUTION_DIR_NAME}/pre_execution_report.md",
        "files": payload.get("files", pre_execution_files(run_id)),
        "gates": payload.get("gates", []),
    }


def pre_execution_files(run_id: str) -> list[dict[str, str]]:
    names = [
        ("pre_execution_readiness.json", "Machine-readable real-resource-creation preparation result."),
        ("pre_execution_report.md", "Human-readable real-resource-creation preparation report."),
        ("environment_mode_decision.json", "Step 1: choose existing-resource binding or new-resource creation mode."),
        ("target_environment_definition.json", "Step 2: target account, region, project, network boundary, naming, and tags."),
        ("data_compliance_classification.json", "Step 3: Tax data sensitivity, RFC controls, encryption, retention, and audit evidence."),
        ("cloud_provisioning_blueprint.json", "Step 4: OBS, MRS, DWS, DataArts, KMS, network, and monitoring blueprint."),
        ("cost_quota_iam_review.json", "Step 5: POC cost guardrails, quota checks, and sizing policy."),
        ("iam_key_strategy.json", "Step 6: IAM separation and key/secret handling strategy."),
        ("iac_state_management_plan.json", "Step 7: IaC state, tags, naming, lock, and destroy policy."),
        ("iac_dry_run_plan.json", "Step 8: dry-run plan and apply boundary."),
        ("destroy_plan.md", "Destroy and cleanup plan required before creation."),
        ("real_resource_creation_approval_request.md", "Final approval request before creating real Huawei Cloud resources."),
    ]
    return [pre_execution_file_entry(run_id, name, description) for name, description in names]


def pre_execution_file_entry(run_id: str, name: str, description: str) -> dict[str, str]:
    path = resolve_existing_run_dir(run_id) / PRE_EXECUTION_DIR_NAME / name
    return {
        "name": name,
        "description": description,
        "path": str(path.relative_to(APP_ROOT)).replace("\\", "/"),
        "url": f"/generated/{run_id}/{PRE_EXECUTION_DIR_NAME}/{name}",
    }


def latest_summary(pattern: str) -> dict[str, Any]:
    for path in sorted(EVALUATIONS_ROOT.glob(f"{pattern}/summary.json"), reverse=True):
        try:
            return read_json(path)
        except json.JSONDecodeError:
            continue
    return {}


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return sha256(path.read_bytes()).hexdigest()


def render_pre_execution_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Real Resource Creation Preparation Report",
        "",
        f"- run_id: {payload['run_id']}",
        f"- status: {payload['status']}",
        f"- ready_for_real_resource_creation: {payload['ready_for_execution_layer']}",
        f"- cloud_execution: {payload['cloud_execution']}",
        f"- summary: {payload['summary']}",
        f"- next_action: {payload.get('next_action', '')}",
        "",
        "| Step | Gate | Status | Ready | Summary |",
        "|---:|---|---|---|---|",
    ]
    for gate in payload.get("gates", []):
        summary = str(gate.get("summary", "")).replace("|", "\\|")
        lines.append(
            f"| {gate.get('step')} | {gate.get('name')} | {gate.get('status')} | "
            f"{gate.get('ready')} | {summary} |"
        )
    lines.extend([
        "",
        "## Control Boundary",
        "",
        "- This report does not create Huawei Cloud resources by itself.",
        "- This report does not submit DataArts, MRS, OBS, or DWS jobs.",
        "- Huawei Cloud credentials, quotas, budget, and creation window must be approved at action time.",
        "- Cloud execution remains blocked even when all eight preparation gates pass.",
        "- When all gates pass, the next step is real Huawei Cloud resource creation under explicit operator approval.",
    ])
    return "\n".join(lines)


def failure_sample_entry(case_id: str, failure_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = FAILURES_ROOT / safe_eval_name(case_id) / safe_eval_name(failure_id) / "failure.json"
    return {
        "failure_id": failure_id,
        "case_id": case_id,
        "name": payload.get("name", case_id),
        "status": payload.get("comparison_status", "failed"),
        "recommendation": payload.get("recommendation", ""),
        "diagnosis": payload.get("diagnosis", ""),
        "captured_at": payload.get("captured_at", ""),
        "path": str(path.relative_to(APP_ROOT)).replace("\\", "/"),
        "url": f"/evaluations/failures/{safe_eval_name(case_id)}/{safe_eval_name(failure_id)}/failure.json",
        "diagnosis_url": f"/evaluations/failures/{safe_eval_name(case_id)}/{safe_eval_name(failure_id)}/diagnosis.md",
    }


def failed_check_details(case: dict[str, Any]) -> list[dict[str, str]]:
    return [check for check in case.get("checks", []) if check.get("status") == "failed"]


def diagnose_failure(case: dict[str, Any], local_case: dict[str, Any], maas_case: dict[str, Any]) -> str:
    maas_failed = failed_check_details(maas_case)
    if not maas_case.get("maas_used"):
        return "MaaS was requested but not used. Check MaaS configuration and network connectivity."
    if any(check.get("id") == "EVAL-002" for check in maas_failed):
        return "MaaS contract did not satisfy the contract audit. Compare business_contract.yaml against local fallback and adjust prompt strategy or audit rules."
    if any(check.get("id") == "EVAL-005" for check in maas_failed):
        return "MaaS contract generated artifacts that passed syntax packaging but failed local dry-run reconciliation."
    if any(check.get("id") == "EVAL-009" for check in maas_failed):
        return "Execution-lock evidence was incomplete. Keep cloud execution blocked and inspect release, binding, and import review status."
    if local_case.get("status") == "passed" and maas_case.get("status") != "passed":
        return "Local fallback passed but MaaS failed. Keep local fallback as default for this case until replay passes."
    return case.get("recommendation", "Inspect failed checks and artifact differences.")


def render_failure_diagnosis(payload: dict[str, Any]) -> str:
    failed = payload.get("maas_failed_checks", [])
    failed_lines = "\n".join(f"- {item.get('id')}: {item.get('name')} - {item.get('detail')}" for item in failed) or "- None"
    return f"""# Failure Diagnosis

- failure_id: {payload['failure_id']}
- case_id: {payload['case_id']}
- source_comparison_id: {payload['source_comparison_id']}
- score_delta: {payload['score_delta']}

## Diagnosis

{payload['diagnosis']}

## Failed MaaS Checks

{failed_lines}

## Replay Guidance

Run the failure replay after changing MaaS prompt strategies, contract audit rules, or local adapter behavior. Cloud execution remains blocked during replay.
"""


def eval_case_by_id(case_id: str) -> dict[str, str]:
    return next((case for case in EVAL_CASES if case["id"] == case_id), {"id": case_id, "name": case_id, "scenario": "", "prompt": ""})


def safe_eval_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "unknown").strip("._") or "unknown"


def render_scorecard(summary: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        "# Agent Evaluation Scorecard",
        "",
        f"- eval_id: {summary['eval_id']}",
        f"- status: {summary['status']}",
        f"- score: {summary['score']}/{summary['max_score']}",
        f"- pass_rate: {summary['pass_rate']}",
        f"- use_maas: {summary['use_maas']}",
        "",
        "## Cases",
        "",
    ]
    for case in cases:
        lines.extend([
            f"### {case['index']}. {case['name']}",
            "",
            f"- case_id: {case['case_id']}",
            f"- scenario: {case['scenario']}",
            f"- run_id: {case.get('run_id', '')}",
            f"- status: {case['status']}",
            f"- score: {case['score']}/{case['max_score']}",
            "",
            "| Check | Status | Detail |",
            "|---|---|---|",
        ])
        for check in case["checks"]:
            detail = str(check.get("detail", "")).replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {check['id']} {check['name']} | {check['status']} | {detail} |")
        lines.append("")
    return "\n".join(lines)


def evaluation_file_entry(eval_id: str, name: str, description: str) -> dict[str, str]:
    path = EVALUATIONS_ROOT / eval_id / name
    return {
        "name": name,
        "description": description,
        "path": str(path.relative_to(APP_ROOT)).replace("\\", "/"),
        "url": f"/evaluations/{eval_id}/{name}",
    }


def read_optional_eval_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return read_json(path)


def has_unresolved_placeholder(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return "${" in text or "<" in text or ">" in text


def contains_plain_rfc(text: str) -> bool:
    return re.search(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b", text.upper()) is not None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
