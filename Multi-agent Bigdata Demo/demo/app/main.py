from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent_graph import run_agent_workflow, run_agent_workflow_events
from .chatbi import (
    build_chatbi_response,
    is_chatbi_prompt,
    is_explicit_engineering_prompt,
    normalize_maas_intent,
    redact_prompt_for_maas,
    semantic_catalog,
)
from .artifact_store import (
    GENERATED_ROOT,
    create_cloud_binding_simulation,
    create_cloud_resource_probe,
    create_dataarts_standardization,
    create_import_review,
    create_release_package,
    get_cloud_binding_status,
    get_cloud_resource_probe_status,
    get_dataarts_standardization_status,
    get_import_review_status,
    get_release_package_status,
    read_json,
    read_optional_json,
    resolve_existing_run_dir,
    save_artifact_review,
)
from .evaluation import (
    EVALUATIONS_ROOT,
    create_pre_execution_readiness,
    get_pre_execution_readiness,
    list_failure_samples,
    replay_failure_samples,
    run_ab_comparison,
    run_evaluation,
)
from .maas_client import list_maas_prompt_strategies, maas_status
from .maas_client import MaaSClient
from .metadata_center import build_metadata_center
from .models import (
    ArtifactReviewRequest,
    ArtifactReviewResponse,
    CloudBindingRequest,
    CloudBindingResponse,
    CloudResourceProbeRequest,
    CloudResourceProbeResponse,
    ChatBIRequest,
    ChatBIResponse,
    ComparisonRunRequest,
    ComparisonRunResponse,
    DataArtsStandardizationResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
    ExecutionApprovalRequest,
    ExecutionCancelRequest,
    ExecutionRequestCreate,
    ExecutionRequestResponse,
    FailureReplayRequest,
    FailureReplayResponse,
    HealthResponse,
    ImportReviewRequest,
    ImportReviewResponse,
    MaaSTestRequest,
    MaaSTestResponse,
    PromptTemplate,
    PromptTemplateRenderRequest,
    PromptTemplateRenderResponse,
    PreExecutionReadinessResponse,
    ReleasePackageResponse,
    RunRequest,
)
from .production_control import (
    canonical_release_hash,
    get_production_store,
    public_execution_profiles,
    resolve_execution_profile,
)
from .prompt_templates import list_templates, render_template
from .security import (
    Principal,
    auth_summary,
    cloud_execution_enabled,
    env_flag,
    require_roles,
)
from .synthetic_data import make_synthetic_rows

APP_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = APP_ROOT / "static"
PUBLIC_EVIDENCE_ROOT = APP_ROOT / "cloud_real_bigdata" / "public_evidence"
RUNTIME_STATUS_ROOT = APP_ROOT / "cloud_real_bigdata" / "runtime_status"
LATEST_CLOUD_E2E_EVIDENCE = PUBLIC_EVIDENCE_ROOT / "latest_e2e_result.json"
CLOUD_WORK_ROOT = APP_ROOT / ".cloud_real_bigdata_work"

app = FastAPI(title="Agentic Tax Bigdata Demo", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8788", "http://localhost:8788"],
    allow_methods=["*"],
    allow_headers=["*"],
)
GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
EVALUATIONS_ROOT.mkdir(parents=True, exist_ok=True)
PUBLIC_EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.mount("/generated", StaticFiles(directory=GENERATED_ROOT), name="generated")
app.mount("/evaluations", StaticFiles(directory=EVALUATIONS_ROOT), name="evaluations")
app.mount("/cloud-evidence", StaticFiles(directory=PUBLIC_EVIDENCE_ROOT), name="cloud-evidence")

APP_SHELL_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html", headers=APP_SHELL_HEADERS)


@app.get("/metadata", include_in_schema=False)
async def metadata_page() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html", headers=APP_SHELL_HEADERS)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    status = maas_status()
    cloud_evidence = read_cloud_e2e_evidence()
    return HealthResponse(
        ok=True,
        service="agentic-tax-bigdata-demo",
        langgraph_available=importlib.util.find_spec("langgraph") is not None,
        maas_configured=bool(status["configured"]),
        maas_model=str(status["model"]),
        code_server_found=shutil.which("code-server") is not None,
        bigdata_deployed=bool(cloud_evidence.get("available")),
    )


@app.get("/api/auth/me")
async def auth_me(request: Request) -> dict[str, object]:
    return auth_summary(request)


def read_cloud_e2e_evidence() -> dict[str, object]:
    if not LATEST_CLOUD_E2E_EVIDENCE.exists():
        return {
            "available": False,
            "status": "not_run",
            "message": "No real Huawei Cloud E2E evidence has been published yet.",
            "evidence_path": str(LATEST_CLOUD_E2E_EVIDENCE),
            "gold_preview_rows": [],
        }
    try:
        evidence = json.loads(LATEST_CLOUD_E2E_EVIDENCE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "status": "invalid",
            "message": f"Cloud E2E evidence is not valid JSON: {exc}",
            "evidence_path": str(LATEST_CLOUD_E2E_EVIDENCE),
            "gold_preview_rows": [],
        }
    return {
        "available": True,
        "status": evidence.get("job", {}).get("terminal_status", "unknown"),
        "message": "Latest real Huawei Cloud E2E evidence is available.",
        "evidence_path": str(LATEST_CLOUD_E2E_EVIDENCE),
        "run_id": evidence.get("run_id", ""),
        "generated_at": evidence.get("generated_at", ""),
        "region": evidence.get("region", ""),
        "bucket": evidence.get("bucket", ""),
        "cluster_id": evidence.get("cluster_id", ""),
        "mrs": evidence.get("mrs", {}),
        "dataarts": evidence.get("dataarts", {}),
        "iceberg": evidence.get("iceberg", {}),
        "gold_prefix": evidence.get("gold_prefix", ""),
        "gold_row_count": evidence.get("gold_row_count", 0),
        "direct_rfc_exposed": evidence.get("direct_rfc_exposed", True),
        "duckdb_used": evidence.get("duckdb_used", True),
        "job": evidence.get("job", {}),
        "prompt_to_artifact": evidence.get("prompt_to_artifact", False),
        "agent_run_id": evidence.get("agent_run_id", ""),
        "agent_release_prefix": evidence.get("agent_release_prefix", ""),
        "customer_report_url": "/cloud-evidence/customer_demo_report.html"
        if (PUBLIC_EVIDENCE_ROOT / "customer_demo_report.html").exists()
        else "",
        "gold_preview_rows": evidence.get("gold_preview_rows", [])[:20],
    }


@app.get("/api/cloud/e2e-evidence")
async def cloud_e2e_evidence() -> dict[str, object]:
    return read_cloud_e2e_evidence()


@app.get("/api/metadata/catalog")
async def metadata_catalog() -> dict[str, object]:
    return build_metadata_center(read_cloud_e2e_evidence())


def _first_row_value(row: dict[str, object], *names: str) -> object:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return ""


def _text_value(value: object) -> str:
    return str(value).strip()


def _bool_filter_matches(value: object, expected: str) -> bool:
    expected_normalized = expected.strip().lower()
    if not expected_normalized or expected_normalized == "all":
        return True
    value_normalized = str(value).strip().lower()
    truthy = {"true", "1", "yes", "y", "si", "sí"}
    falsy = {"false", "0", "no", "n"}
    if expected_normalized in truthy:
        return value_normalized in truthy
    if expected_normalized in falsy:
        return value_normalized in falsy
    return value_normalized == expected_normalized


def _float_value(value: object) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _distinct_sorted(rows: list[dict[str, object]], *names: str) -> list[str]:
    values = {
        _text_value(_first_row_value(row, *names))
        for row in rows
        if _text_value(_first_row_value(row, *names))
    }
    return sorted(values)


def _summarize_gold_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    taxpayer_total = 0
    income_total = 0.0
    for row in rows:
        taxpayer_total += _int_value(_first_row_value(row, "taxpayer_count", "active_taxpayers"))
        income_total += _float_value(_first_row_value(row, "annual_income_total", "total_declared_amount"))
    return {
        "group_count": len(rows),
        "taxpayer_count": taxpayer_total,
        "income_total": round(income_total, 2),
        "income_avg_per_taxpayer": round(income_total / taxpayer_total, 2) if taxpayer_total else 0,
    }


@app.get("/api/cloud/gold-query")
async def cloud_gold_query(
    year: str = "",
    region: str = "",
    regime: str = "",
    resico: str = "",
    limit: int = 50,
) -> dict[str, object]:
    evidence = read_cloud_e2e_evidence()
    raw_rows = evidence.get("gold_preview_rows") if isinstance(evidence.get("gold_preview_rows"), list) else []
    rows = [row for row in raw_rows if isinstance(row, dict)]
    bounded_limit = max(1, min(int(limit or 50), 200))

    filtered = []
    for row in rows:
        row_year = _text_value(_first_row_value(row, "year", "ejercicio_analisis"))
        row_region = _text_value(_first_row_value(row, "region"))
        row_regime = _text_value(_first_row_value(row, "regime", "cve_regimen"))
        row_resico = _first_row_value(row, "resico_flag", "is_resico")
        if year and row_year != year:
            continue
        if region and row_region != region:
            continue
        if regime and row_regime != regime:
            continue
        if not _bool_filter_matches(row_resico, resico):
            continue
        filtered.append(row)

    return {
        "available": bool(evidence.get("available")),
        "status": evidence.get("status", "not_run"),
        "message": evidence.get("message", ""),
        "source": evidence.get("evidence_path", ""),
        "run_id": evidence.get("run_id", ""),
        "gold_prefix": evidence.get("gold_prefix", ""),
        "filters": {
            "year": year,
            "region": region,
            "regime": regime,
            "resico": resico,
            "limit": bounded_limit,
        },
        "dimensions": {
            "years": _distinct_sorted(rows, "year", "ejercicio_analisis"),
            "regions": _distinct_sorted(rows, "region"),
            "regimes": _distinct_sorted(rows, "regime", "cve_regimen"),
            "resico": _distinct_sorted(rows, "resico_flag", "is_resico"),
        },
        "row_count": len(rows),
        "filtered_count": len(filtered),
        "summary": _summarize_gold_rows(filtered),
        "rows": filtered[:bounded_limit],
    }


def _safe_chatbi_history(history: list[dict[str, object]]) -> list[dict[str, object]]:
    allowed_contract_keys = {
        "year",
        "region",
        "regime",
        "resico",
        "group_by",
        "metrics",
        "primary_metric",
        "limit",
        "ascending",
    }
    safe_history = []
    for item in history[-4:]:
        prompt, _redacted = redact_prompt_for_maas(str(item.get("prompt", ""))[:500])
        raw_contract = item.get("contract") if isinstance(item.get("contract"), dict) else {}
        contract = {
            key: value
            for key, value in raw_contract.items()
            if key in allowed_contract_keys
        }
        safe_history.append({"prompt": prompt, "contract": contract})
    return safe_history


@app.get("/api/chatbi/catalog")
async def chatbi_catalog() -> dict[str, object]:
    return semantic_catalog(read_cloud_e2e_evidence())


@app.post("/api/chatbi/query", response_model=ChatBIResponse)
async def chatbi_query(request: ChatBIRequest) -> ChatBIResponse:
    evidence = read_cloud_e2e_evidence()
    maas = MaaSClient()
    base_trace = {
        "mode": "deterministic",
        "requested": False,
        "configured": maas.configured,
        "used": False,
        "model": maas.model if maas.configured else "",
        "fallback": False,
        "prompt_redacted": False,
    }

    if is_explicit_engineering_prompt(request.prompt) or is_chatbi_prompt(request.prompt):
        return ChatBIResponse(
            **build_chatbi_response(
                request.prompt,
                evidence,
                parser_trace=base_trace,
                locale=request.locale,
            )
        )

    if not maas.configured:
        clarification = {
            "intent": "clarification",
            "clarification": (
                "This request did not match the local semantic rules, and MaaS is unavailable. "
                "Add a year, region, tax regime, and the taxpayer or income metric you need."
                if request.locale == "en"
                else "这个表达还没有命中本地语义规则，并且 MaaS 当前不可用。"
                "请补充年份、地区、税制以及要查看的数量或收入指标。"
            ),
        }
        base_trace.update({"mode": "local_fallback", "fallback": True})
        return ChatBIResponse(
            **build_chatbi_response(
                request.prompt,
                evidence,
                intent_contract=clarification,
                parser_trace=base_trace,
                locale=request.locale,
            )
        )

    safe_prompt, prompt_redacted = redact_prompt_for_maas(request.prompt)
    trace = {
        **base_trace,
        "mode": "maas",
        "requested": True,
        "prompt_redacted": prompt_redacted,
    }
    try:
        raw_intent = await maas.parse_chatbi_intent(
            safe_prompt,
            semantic_catalog(evidence),
            _safe_chatbi_history(request.history),
        )
        intent = normalize_maas_intent(raw_intent, evidence)
        trace["used"] = True
    except Exception as exc:  # noqa: BLE001 - failure is converted to a safe local clarification.
        trace.update(
            {
                "mode": "local_fallback",
                "fallback": True,
                "error_type": type(exc).__name__,
            }
        )
        intent = {
            "intent": "clarification",
            "clarification": (
                "I could not safely map that request to the Tax metric catalog. Try again, "
                "or add a year, region, tax regime, and the taxpayer or income metric you need."
                if request.locale == "en"
                else "我暂时没能把这句话安全映射到 Tax 指标目录。你可以重试，"
                "或补充年份、地区、税制以及要查看的数量或收入指标。"
            ),
        }

    return ChatBIResponse(
        **build_chatbi_response(
            request.prompt,
            evidence,
            intent_contract=intent,
            parser_trace=trace,
            locale=request.locale,
        )
    )


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(APP_ROOT))
    except ValueError:
        return str(path)


def _read_report(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "status": "not_run",
            "available": False,
            "path": _relative_path(path),
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "available": False,
            "path": _relative_path(path),
            "detail": f"Invalid JSON: {exc}",
        }
    report["available"] = True
    report["path"] = _relative_path(path)
    return report


def _read_runtime_report(path: Path, snapshot_name: str) -> dict[str, object]:
    report = _read_report(path)
    if report.get("available"):
        return report
    return _read_report(RUNTIME_STATUS_ROOT / snapshot_name)


def _command_value(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, str):
        return value
    return ""


def _readiness_gate(
    *,
    gate_id: str,
    label: str,
    report: dict[str, object],
    status: str,
    detail: str,
    blocking: bool,
) -> dict[str, object]:
    return {
        "id": gate_id,
        "label": label,
        "status": status,
        "raw_status": report.get("status", "not_run"),
        "blocking": blocking,
        "detail": detail,
        "path": report.get("path", ""),
        "generated_at": report.get("generated_at", ""),
        "next_action": report.get("next_action", ""),
    }


def _read_cloud_readiness() -> dict[str, object]:
    credential = _read_runtime_report(CLOUD_WORK_ROOT / "credential_status" / "credential_status_latest.json", "credential_status.json")
    apply_safety = _read_runtime_report(CLOUD_WORK_ROOT / "apply_safety" / "apply_safety_latest.json", "apply_safety.json")
    lifecycle = _read_runtime_report(CLOUD_WORK_ROOT / "lifecycle_guard" / "lifecycle_guard_latest.json", "lifecycle_guard.json")
    resource_plan = _read_runtime_report(CLOUD_WORK_ROOT / "minimal_cost_quota_plan" / "minimal_cost_quota_plan_latest.json", "minimal_cost_quota_plan.json")
    readonly_probe = _read_runtime_report(CLOUD_WORK_ROOT / "readonly_probe" / "readonly_probe_latest.json", "readonly_probe.json")
    pre_apply = _read_runtime_report(CLOUD_WORK_ROOT / "pre_apply_readiness" / "pre_apply_readiness_latest.json", "pre_apply_readiness.json")
    operator_bootstrap = _read_runtime_report(CLOUD_WORK_ROOT / "operator_bootstrap" / "operator_bootstrap_latest.json", "operator_bootstrap.json")
    customer_handoff = _read_runtime_report(CLOUD_WORK_ROOT / "customer_handoff" / "customer_handoff_latest.json", "customer_handoff.json")
    customer_commercial = _read_runtime_report(CLOUD_WORK_ROOT / "customer_commercial_readiness" / "customer_commercial_readiness_latest.json", "customer_commercial_readiness.json")
    preflight = _read_runtime_report(CLOUD_WORK_ROOT / "real_cloud_preflight" / "real_cloud_preflight_latest.json", "real_cloud_preflight.json")
    audit = _read_runtime_report(CLOUD_WORK_ROOT / "acceptance_audit" / "final_acceptance_audit.json", "final_acceptance_audit.json")
    web_diag = _read_runtime_report(CLOUD_WORK_ROOT / "web_diagnostics" / "web_diagnostics_latest.json", "web_diagnostics.json")
    if not web_diag.get("available"):
        web_diag = _read_report(CLOUD_WORK_ROOT / "web_diagnostics_smoke" / "web_diagnostics_latest.json")
    evidence = read_cloud_e2e_evidence()

    missing_required_raw = credential.get("missing_required") or []
    missing_required = [
        item for item in missing_required_raw if item is not None and str(item).strip()
    ]
    credential_blocking = bool(missing_required)
    credential_detail = (
        f"Missing required environment variables: {', '.join(str(item) for item in missing_required)}"
        if missing_required
        else "Credential variables are present. Values are not exposed by the API."
    )

    apply_checks = apply_safety.get("checks") if isinstance(apply_safety.get("checks"), list) else []
    apply_blocking = any(bool(item.get("blocking")) for item in apply_checks if isinstance(item, dict))
    apply_detail = str(apply_safety.get("next_action") or apply_safety.get("status") or "not_run")

    lifecycle_checks = lifecycle.get("checks") if isinstance(lifecycle.get("checks"), list) else []
    lifecycle_blocking = any(bool(item.get("blocking")) for item in lifecycle_checks if isinstance(item, dict))
    lifecycle_detail = str(lifecycle.get("next_action") or lifecycle.get("status") or "not_run")

    resource_plan_status = str(resource_plan.get("status", "not_run"))
    resource_plan_blocking = resource_plan_status in {"not_run", "failed", "invalid"}
    resource_plan_detail = str(
        resource_plan.get("next_action")
        or resource_plan.get("customer_demo_boundary", {}).get("reason", "")
        or resource_plan_status
    )

    pre_apply_gates = pre_apply.get("gates") if isinstance(pre_apply.get("gates"), list) else []
    pre_apply_blocking = any(bool(item.get("blocking")) for item in pre_apply_gates if isinstance(item, dict))
    pre_apply_detail = str(pre_apply.get("next_action") or pre_apply.get("status") or "not_run")

    customer_commercial_status = str(customer_commercial.get("status", "not_run"))
    customer_commercial_detail = str(
        customer_commercial.get("next_action")
        or f"demo_ready={customer_commercial.get('demo_ready', False)}, commercial_ready={customer_commercial.get('commercial_ready', False)}"
    )

    readonly_status = str(readonly_probe.get("status", "not_run"))
    readonly_blocking = readonly_status in {"missing_credentials", "failed", "invalid"}
    readonly_detail = str(
        readonly_probe.get("reason")
        or readonly_probe.get("next_action")
        or f"network_calls={readonly_probe.get('network_calls', 0)}, write_calls={readonly_probe.get('write_calls', 0)}"
    )

    preflight_status = str(preflight.get("status", "not_run"))
    preflight_blocking = preflight_status in {"failed", "invalid"}
    preflight_detail = str(preflight.get("message") or preflight.get("next_action") or preflight_status)

    audit_status = str(audit.get("status", "not_run"))
    audit_blocking = audit_status in {"failed", "invalid"}
    audit_detail = str(audit.get("next_action") or audit.get("summary") or audit_status)

    web_status = str(web_diag.get("status", "not_run"))
    web_blocking = bool(web_diag.get("failed_critical_count", 0))
    web_detail = str(web_diag.get("next_action") or web_status)

    evidence_available = bool(evidence.get("available"))
    evidence_success = evidence_available and str(evidence.get("status", "")).lower() in {"success", "succeeded", "finished"}
    evidence_detail = (
        f"Real run {evidence.get('run_id', '')} has {evidence.get('gold_row_count', 0)} gold rows."
        if evidence_available
        else str(evidence.get("message", "No real Huawei Cloud E2E evidence has been published yet."))
    )

    gates = [
        _readiness_gate(
            gate_id="credentials",
            label="Credential source",
            report=credential,
            status="blocked" if credential_blocking else "ready",
            detail=credential_detail,
            blocking=credential_blocking,
        ),
        _readiness_gate(
            gate_id="apply_safety",
            label="Network safety",
            report=apply_safety,
            status="blocked" if apply_blocking else ("ready" if apply_safety.get("available") else "not_run"),
            detail=apply_detail,
            blocking=apply_blocking,
        ),
        _readiness_gate(
            gate_id="lifecycle_guard",
            label="Lifecycle guard",
            report=lifecycle,
            status="blocked" if lifecycle_blocking else ("ready" if lifecycle.get("available") else "not_run"),
            detail=lifecycle_detail,
            blocking=lifecycle_blocking,
        ),
        _readiness_gate(
            gate_id="minimal_cost_quota_plan",
            label="Minimal resource plan",
            report=resource_plan,
            status="blocked"
            if resource_plan_blocking
            else ("warning" if resource_plan_status == "review_required" else "ready"),
            detail=resource_plan_detail,
            blocking=resource_plan_blocking,
        ),
        _readiness_gate(
            gate_id="pre_apply_readiness",
            label="Pre-apply readiness",
            report=pre_apply,
            status="blocked" if pre_apply_blocking else ("ready" if pre_apply.get("status") in {"ready", "ready_for_apply"} else str(pre_apply.get("status", "not_run"))),
            detail=pre_apply_detail,
            blocking=pre_apply_blocking,
        ),
        _readiness_gate(
            gate_id="operator_bootstrap",
            label="Operator bootstrap",
            report=operator_bootstrap,
            status=str(operator_bootstrap.get("status", "not_run")),
            detail=str(operator_bootstrap.get("next_action") or "Run the bootstrap script to configure local guards and refresh readiness."),
            blocking=False,
        ),
        _readiness_gate(
            gate_id="customer_handoff",
            label="Customer handoff",
            report=customer_handoff,
            status="ready" if customer_handoff.get("status") == "ready_for_customer_handoff" else str(customer_handoff.get("status", "not_run")),
            detail=str(customer_handoff.get("next_action") or customer_handoff.get("status") or "Export customer handoff after real E2E evidence and strict audit pass."),
            blocking=False,
        ),
        _readiness_gate(
            gate_id="customer_commercial_readiness",
            label="Customer/commercial readiness",
            report=customer_commercial,
            status="ready"
            if customer_commercial_status in {"ready_for_customer_demo", "ready_for_commercial_pilot"}
            else ("blocked" if customer_commercial_status == "failed" else customer_commercial_status),
            detail=customer_commercial_detail,
            blocking=False,
        ),
        _readiness_gate(
            gate_id="readonly_probe",
            label="Read-only cloud probe",
            report=readonly_probe,
            status="blocked" if readonly_blocking else ("ready" if readonly_status in {"passed", "ready", "success"} else readonly_status),
            detail=readonly_detail,
            blocking=readonly_blocking,
        ),
        _readiness_gate(
            gate_id="terraform_preflight",
            label="Terraform preflight",
            report=preflight,
            status="blocked" if preflight_blocking else ("ready" if preflight_status in {"passed", "success", "ready"} else preflight_status),
            detail=preflight_detail,
            blocking=preflight_blocking,
        ),
        _readiness_gate(
            gate_id="final_audit",
            label="Final acceptance audit",
            report=audit,
            status="blocked" if audit_blocking else ("ready" if audit_status in {"passed", "success", "complete"} else audit_status),
            detail=audit_detail,
            blocking=audit_blocking,
        ),
        _readiness_gate(
            gate_id="web_diagnostics",
            label="Website diagnostics",
            report=web_diag,
            status="blocked" if web_blocking else ("ready" if web_diag.get("available") else "not_run"),
            detail=web_detail,
            blocking=web_blocking,
        ),
        {
            "id": "cloud_evidence",
            "label": "Real cloud E2E evidence",
            "status": "ready" if evidence_success else ("pending" if evidence_available else "not_run"),
            "raw_status": evidence.get("status", "not_run"),
            "blocking": False,
            "detail": evidence_detail,
            "path": _relative_path(LATEST_CLOUD_E2E_EVIDENCE),
            "generated_at": evidence.get("generated_at", ""),
            "next_action": "Run the real MRS E2E flow, then publish cloud evidence."
            if not evidence_available
            else "",
        },
    ]

    blocking_count = sum(1 for gate in gates if gate.get("blocking"))
    if evidence_success:
        status = "cloud_e2e_verified"
        message = "真实云上 E2E 证据已经发布，可以给客户查看处理后的 gold 数据。"
    elif blocking_count:
        status = "blocked"
        message = f"还不能创建真实资源：有 {blocking_count} 个阻塞门禁。"
    elif preflight_status in {"passed", "success", "ready"}:
        status = "ready_for_apply"
        message = "本地门禁已通过，可以由操作员显式执行真实云上 apply。"
    else:
        status = "pending_cloud_preflight"
        message = "本地门禁未发现阻塞项，但还需要完成只读探测和 Terraform 预检。"

    operator_bootstrap_command = ".\\cloud_real_bigdata\\scripts\\18_bootstrap_operator_session.ps1 -ConfigureCredentials -PersistUserEnv -SetGuardDefaults -DetectAdminCidr -EnableWebEcs -RunTerraformPreflight"
    minimal_plan_command = ".\\cloud_real_bigdata\\scripts\\21_export_minimal_cost_quota_plan.ps1 -EnableWebEcs"
    customer_commercial_command = ".\\cloud_real_bigdata\\scripts\\22_validate_customer_commercial_readiness.ps1 -BaseUrl \"http://<customer-demo-url>\""
    customer_demo_command = ".\\cloud_real_bigdata\\scripts\\19_run_customer_demo_once.ps1 -EnableWebEcs -SshKeyPath \"<path-to-private-key.pem>\" -Apply -ConfirmPaidResources"
    customer_handoff_command = ".\\cloud_real_bigdata\\scripts\\20_export_customer_handoff.ps1 -BaseUrl \"http://<customer-demo-url>\" -RequireCloudSuccess -PublishToEvidence"
    commands = {
        "minimal_cost_quota_plan": minimal_plan_command,
        "customer_commercial_readiness": customer_commercial_command,
        "customer_demo_once": customer_demo_command,
        "customer_handoff": customer_handoff_command,
        "operator_bootstrap": operator_bootstrap_command,
    } if status == "ready_for_apply" else {
        "minimal_cost_quota_plan": minimal_plan_command,
        "customer_commercial_readiness": customer_commercial_command,
        "operator_bootstrap": operator_bootstrap_command,
        "customer_demo_once": customer_demo_command,
        "customer_handoff": customer_handoff_command,
    }
    if isinstance(pre_apply.get("commands"), dict):
        commands.update({str(key): _command_value(value) for key, value in pre_apply["commands"].items()})
    if preflight.get("command"):
        commands.setdefault("preflight", _command_value(preflight.get("command")))
    commands.setdefault(
        "credential_status",
        ".\\cloud_real_bigdata\\scripts\\12_configure_cloud_credentials.ps1 -PersistUserEnv",
    )
    commands.setdefault(
        "pre_apply_readiness",
        ".\\cloud_real_bigdata\\scripts\\15_pre_apply_readiness.ps1 -EnableWebEcs -RunReadonlyCloudProbe -RunTerraformPreflight",
    )

    latest_next_action = commands["operator_bootstrap"] if blocking_count else ""
    if not latest_next_action and status == "ready_for_apply":
        latest_next_action = commands["customer_demo_once"]
    if not latest_next_action:
        latest_next_action = next((str(gate.get("next_action")) for gate in gates if gate.get("blocking") and gate.get("next_action")), "")
    if not latest_next_action:
        latest_next_action = str(pre_apply.get("next_action") or preflight.get("next_action") or "")

    return {
        "status": status,
        "message": message,
        "generated_at": pre_apply.get("generated_at") or resource_plan.get("generated_at") or credential.get("generated_at") or "",
        "values_printed": False,
        "creates_resources": False,
        "uploads_obs_objects": False,
        "submits_mrs_job": False,
        "source_policy": credential.get(
            "source_policy",
            "Use environment variables, ignored .env.local, or cloud secret service. Do not read secrets from skills, chat, screenshots, cookies, or saved browser sessions.",
        ),
        "blocking_count": blocking_count,
        "gates": gates,
        "commands": commands,
        "next_action": latest_next_action,
    }


@app.get("/api/cloud/readiness")
async def cloud_readiness() -> dict[str, object]:
    return _read_cloud_readiness()


@app.get("/api/sample-data")
async def sample_data(scenario: str = "tax_taxpayer_annual_base") -> dict[str, object]:
    rows = make_synthetic_rows(scenario)
    return {"scenario": scenario, "rows": rows[:8], "row_count": len(rows)}


@app.get("/api/maas/status")
async def get_maas_status() -> dict[str, object]:
    return maas_status()


@app.get("/api/maas/strategies")
async def get_maas_strategies() -> dict[str, object]:
    return {"strategies": list_maas_prompt_strategies()}


@app.post("/api/maas/test", response_model=MaaSTestResponse)
async def test_maas(
    request: MaaSTestRequest,
    _principal: Principal = Depends(require_roles("developer")),
) -> MaaSTestResponse:
    client = MaaSClient()
    result = await client.test_connection(request.prompt[:1200])
    return MaaSTestResponse(**result, status=maas_status())


@app.get("/api/prompt-templates", response_model=list[PromptTemplate])
async def prompt_templates() -> list[PromptTemplate]:
    return list_templates()


@app.get("/api/evaluations")
async def list_evaluations() -> dict[str, object]:
    items = []
    for path in sorted(EVALUATIONS_ROOT.glob("eval-*"), reverse=True):
        summary_path = path / "summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append({
            "eval_id": summary.get("eval_id", path.name),
            "status": summary.get("status", "unknown"),
            "score": summary.get("score", 0),
            "max_score": summary.get("max_score", 0),
            "pass_rate": summary.get("pass_rate", 0),
            "case_count": summary.get("case_count", 0),
            "summary": summary.get("summary", ""),
            "scorecard_url": f"/evaluations/{path.name}/scorecard.md",
        })
    return {"evaluations": items[:10]}


@app.get("/api/evaluations/comparisons")
async def list_evaluation_comparisons() -> dict[str, object]:
    items = []
    for path in sorted(EVALUATIONS_ROOT.glob("compare-*"), reverse=True):
        summary_path = path / "summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append({
            "comparison_id": summary.get("comparison_id", path.name),
            "status": summary.get("status", "unknown"),
            "passed": summary.get("passed", False),
            "summary": summary.get("summary", ""),
            "recommendation": summary.get("recommendation", ""),
            "metrics": summary.get("metrics", {}),
            "comparison_url": f"/evaluations/{path.name}/comparison_report.md",
        })
    return {"comparisons": items[:10]}


@app.post("/api/evaluations", response_model=EvaluationRunResponse)
async def create_evaluation(
    request: EvaluationRunRequest,
    _principal: Principal = Depends(require_roles("developer", "artifact_reviewer")),
) -> EvaluationRunResponse:
    return EvaluationRunResponse(**await run_evaluation(request))


@app.post("/api/evaluations/compare", response_model=ComparisonRunResponse)
async def create_evaluation_comparison(
    request: ComparisonRunRequest,
    _principal: Principal = Depends(require_roles("developer", "artifact_reviewer")),
) -> ComparisonRunResponse:
    return ComparisonRunResponse(**await run_ab_comparison(request))


@app.get("/api/evaluations/failures")
async def get_failure_samples() -> dict[str, object]:
    return {"failures": list_failure_samples()[:20]}


@app.post("/api/evaluations/failures/replay", response_model=FailureReplayResponse)
async def replay_failures(
    request: FailureReplayRequest,
    _principal: Principal = Depends(require_roles("developer", "artifact_reviewer")),
) -> FailureReplayResponse:
    return FailureReplayResponse(**await replay_failure_samples(request))


@app.post("/api/prompt-templates/{template_id}/render", response_model=PromptTemplateRenderResponse)
async def render_prompt_template(
    template_id: str,
    request: PromptTemplateRenderRequest,
) -> PromptTemplateRenderResponse:
    try:
        return render_template(template_id, request.variables)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found") from exc


@app.post("/api/runs")
async def create_run(
    request: RunRequest,
    _principal: Principal = Depends(require_roles("developer")),
):
    return await run_agent_workflow(request)


@app.post("/api/runs/stream")
async def create_run_stream(
    request: RunRequest,
    _principal: Principal = Depends(require_roles("developer")),
) -> StreamingResponse:
    async def event_stream():
        try:
            async for item in run_agent_workflow_events(request):
                event = item["event"]
                data = json.dumps(item["data"], ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface safe error to local UI.
            data = json.dumps({"message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
            yield f"event: run_error\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/runs/{run_id}/gold-preview")
async def gold_preview(run_id: str) -> dict[str, object]:
    try:
        run_dir = resolve_existing_run_dir(run_id)
        rows = read_json(run_dir / "gold_preview.json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run_id": run_id,
        "rows": rows[:50],
        "row_count": len(rows),
        "source": f"/generated/{run_id}/gold_preview.json",
    }


@app.post("/api/runs/{run_id}/artifacts/{artifact_name}/review", response_model=ArtifactReviewResponse)
async def review_artifact(
    run_id: str,
    artifact_name: str,
    request: ArtifactReviewRequest,
    principal: Principal = Depends(require_roles("artifact_reviewer")),
) -> ArtifactReviewResponse:
    try:
        authenticated_request = request.model_copy(update={"reviewer": principal.subject})
        review = save_artifact_review(run_id, artifact_name, authenticated_request)
        get_production_store().record_artifact_approval(
            run_id=run_id,
            artifact_name=artifact_name,
            artifact_hash=review["artifact_hash"],
            decision=review["status"],
            actor=principal.subject,
            note=review["note"],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ArtifactReviewResponse(**review)


@app.get("/api/runs/{run_id}/release-package", response_model=ReleasePackageResponse)
async def release_package_status(run_id: str) -> ReleasePackageResponse:
    try:
        release = get_release_package_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReleasePackageResponse(**release)


@app.post("/api/runs/{run_id}/release-package", response_model=ReleasePackageResponse)
async def generate_release_package(
    run_id: str,
    principal: Principal = Depends(require_roles("release_manager")),
) -> ReleasePackageResponse:
    try:
        release = create_release_package(run_id)
        if release.get("status") == "generated" and release.get("release"):
            get_production_store().record_release(
                run_id=run_id,
                manifest=release["release"],
                actor=principal.subject,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReleasePackageResponse(**release)


@app.get("/api/runs/{run_id}/cloud-binding", response_model=CloudBindingResponse)
async def cloud_binding_status(run_id: str) -> CloudBindingResponse:
    try:
        binding = get_cloud_binding_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudBindingResponse(**binding)


@app.post("/api/runs/{run_id}/cloud-binding", response_model=CloudBindingResponse)
async def generate_cloud_binding(
    run_id: str,
    request: CloudBindingRequest | None = None,
    principal: Principal = Depends(require_roles("release_manager")),
) -> CloudBindingResponse:
    try:
        effective_request = (request or CloudBindingRequest()).model_copy(
            update={"reviewer": principal.subject}
        )
        binding = create_cloud_binding_simulation(run_id, effective_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudBindingResponse(**binding)


@app.get("/api/runs/{run_id}/import-review", response_model=ImportReviewResponse)
async def import_review_status(run_id: str) -> ImportReviewResponse:
    try:
        review = get_import_review_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportReviewResponse(**review)


@app.post("/api/runs/{run_id}/import-review", response_model=ImportReviewResponse)
async def generate_import_review(
    run_id: str,
    request: ImportReviewRequest | None = None,
    principal: Principal = Depends(require_roles("release_manager", "cloud_operator")),
) -> ImportReviewResponse:
    try:
        effective_request = (request or ImportReviewRequest()).model_copy(
            update={"reviewer": principal.subject}
        )
        review = create_import_review(run_id, effective_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportReviewResponse(**review)


@app.get("/api/runs/{run_id}/dataarts-standardization", response_model=DataArtsStandardizationResponse)
async def dataarts_standardization_status(run_id: str) -> DataArtsStandardizationResponse:
    try:
        result = get_dataarts_standardization_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataArtsStandardizationResponse(**result)


@app.post("/api/runs/{run_id}/dataarts-standardization", response_model=DataArtsStandardizationResponse)
async def generate_dataarts_standardization(
    run_id: str,
    _principal: Principal = Depends(require_roles("release_manager")),
) -> DataArtsStandardizationResponse:
    try:
        result = create_dataarts_standardization(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataArtsStandardizationResponse(**result)


@app.get("/api/runs/{run_id}/cloud-resource-probe", response_model=CloudResourceProbeResponse)
async def cloud_resource_probe_status(run_id: str) -> CloudResourceProbeResponse:
    try:
        result = get_cloud_resource_probe_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudResourceProbeResponse(**result)


@app.post("/api/runs/{run_id}/cloud-resource-probe", response_model=CloudResourceProbeResponse)
async def generate_cloud_resource_probe(
    run_id: str,
    request: CloudResourceProbeRequest | None = None,
    principal: Principal = Depends(require_roles("cloud_operator", "release_manager")),
) -> CloudResourceProbeResponse:
    try:
        effective_request = (request or CloudResourceProbeRequest()).model_copy(
            update={"reviewer": principal.subject}
        )
        result = create_cloud_resource_probe(run_id, effective_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudResourceProbeResponse(**result)


@app.get("/api/runs/{run_id}/pre-execution", response_model=PreExecutionReadinessResponse)
async def pre_execution_status(run_id: str) -> PreExecutionReadinessResponse:
    try:
        readiness = get_pre_execution_readiness(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PreExecutionReadinessResponse(**readiness)


@app.post("/api/runs/{run_id}/pre-execution", response_model=PreExecutionReadinessResponse)
async def generate_pre_execution_readiness(
    run_id: str,
    _principal: Principal = Depends(require_roles("release_manager", "cloud_operator")),
) -> PreExecutionReadinessResponse:
    try:
        readiness = create_pre_execution_readiness(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PreExecutionReadinessResponse(**readiness)


def _execution_release(run_id: str, requested_hash: str) -> tuple[str, dict[str, object]]:
    if not cloud_execution_enabled():
        raise HTTPException(
            status_code=503,
            detail="Production cloud execution is disabled.",
        )
    release = get_release_package_status(run_id)
    if release.get("status") != "generated" or not release.get("ready"):
        raise HTTPException(
            status_code=409,
            detail="A current immutable release package is required.",
        )
    manifest = release.get("release", {})
    release_hash = str(manifest.get("release_hash") or canonical_release_hash(manifest))
    if requested_hash and requested_hash != release_hash:
        raise HTTPException(
            status_code=409,
            detail="The requested release hash is not the current immutable release.",
        )
    stored_release = get_production_store().latest_release(run_id)
    if not stored_release or stored_release["release_hash"] != release_hash:
        raise HTTPException(
            status_code=409,
            detail="The current release has not been recorded by the production control plane.",
        )

    if env_flag("SAT_REQUIRE_REAL_CLOUD_PROBE", True):
        run_dir = resolve_existing_run_dir(run_id)
        probe = read_optional_json(run_dir / "cloud_resource_probe_status.json") or {}
        if not (
            probe.get("ready_for_operator_execution_request")
            and probe.get("real_cloud_verified")
        ):
            raise HTTPException(
                status_code=409,
                detail="A successful read-only verification of the bound cloud resources is required.",
            )
    return release_hash, manifest


@app.get("/api/runs/{run_id}/production-control")
async def production_control_status(
    run_id: str,
    _principal: Principal = Depends(
        require_roles("developer", "artifact_reviewer", "release_manager", "cloud_operator", "auditor")
    ),
) -> dict[str, object]:
    try:
        resolve_existing_run_dir(run_id)
        return get_production_store().run_control_status(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/execution-profiles")
async def list_execution_profiles(
    _principal: Principal = Depends(require_roles("release_manager", "cloud_operator")),
) -> dict[str, object]:
    try:
        return {"profiles": public_execution_profiles()}
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/api/runs/{run_id}/execution-requests",
    response_model=ExecutionRequestResponse,
)
async def create_execution_request(
    run_id: str,
    request: ExecutionRequestCreate,
    principal: Principal = Depends(require_roles("release_manager")),
) -> ExecutionRequestResponse:
    try:
        release_hash, _manifest = _execution_release(run_id, request.release_hash)
        target = request.target
        parameters = request.parameters
        if request.profile_id:
            profile = resolve_execution_profile(request.profile_id)
            if target != profile["target"]:
                raise ValueError("Execution target does not match the selected profile.")
            if parameters:
                raise ValueError("Do not send parameters when using an execution profile.")
            parameters = profile["parameters"]
        elif env_flag("SAT_REQUIRE_EXECUTION_PROFILE", True):
            raise ValueError("A server-managed execution profile is required.")
        result = get_production_store().create_execution_request(
            run_id=run_id,
            release_hash=release_hash,
            target=target,
            parameters=parameters,
            idempotency_key=request.idempotency_key,
            actor=principal.subject,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExecutionRequestResponse(**result)


@app.get(
    "/api/execution-requests/{request_id}",
    response_model=ExecutionRequestResponse,
)
async def execution_request_status(
    request_id: str,
    _principal: Principal = Depends(
        require_roles("release_manager", "cloud_operator", "auditor")
    ),
) -> ExecutionRequestResponse:
    result = get_production_store().execution_request(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution request not found.")
    return ExecutionRequestResponse(**result)


@app.post(
    "/api/execution-requests/{request_id}/approve",
    response_model=ExecutionRequestResponse,
)
async def approve_execution_request(
    request_id: str,
    request: ExecutionApprovalRequest,
    principal: Principal = Depends(require_roles("cloud_operator")),
) -> ExecutionRequestResponse:
    try:
        result = get_production_store().approve_execution(
            request_id,
            principal.subject,
            request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execution request not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExecutionRequestResponse(**result)


@app.post(
    "/api/execution-requests/{request_id}/cancel",
    response_model=ExecutionRequestResponse,
)
async def cancel_execution_request(
    request_id: str,
    request: ExecutionCancelRequest,
    principal: Principal = Depends(require_roles("cloud_operator", "release_manager")),
) -> ExecutionRequestResponse:
    try:
        result = get_production_store().cancel_execution(
            request_id,
            principal.subject,
            request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execution request not found.") from exc
    return ExecutionRequestResponse(**result)
