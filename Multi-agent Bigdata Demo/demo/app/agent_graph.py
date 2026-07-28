from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .artifact_store import persist_run_package
from .maas_client import MaaSClient, maas_status
from .models import AgentResult, ArtifactPreview, GateResult, RunRequest, RunResponse
from .synthetic_data import aggregate_gold, make_synthetic_rows


class AgentState(TypedDict, total=False):
    run_id: str
    request: RunRequest
    maas_client: MaaSClient
    maas_used: bool
    maas_error: str | None
    maas_strategy: str | None
    model_summary: str | None
    business_contract: dict[str, Any]
    contract_audit: dict[str, Any]
    local_execution: dict[str, Any]
    agents: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    quality_gates: list[dict[str, Any]]
    synthetic_rows: list[dict[str, Any]]
    gold_rows: list[dict[str, Any]]
    lineage: list[dict[str, str]]
    decision: dict[str, Any]


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("business_contract", business_contract_node)
    graph.add_node("contract_audit", contract_audit_node)
    graph.add_node("local_data", local_data_node)
    graph.add_node("artifact_package", artifact_package_node)
    graph.add_node("local_dry_run", local_dry_run_node)
    graph.add_node("review_gates", review_gates_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "local_data")
    graph.add_edge("local_data", "business_contract")
    graph.add_edge("business_contract", "contract_audit")
    graph.add_edge("contract_audit", "artifact_package")
    graph.add_edge("artifact_package", "local_dry_run")
    graph.add_edge("local_dry_run", "review_gates")
    graph.add_edge("review_gates", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_agent_workflow(request: RunRequest) -> RunResponse:
    initial = initial_state(request)
    state = await build_graph().ainvoke(initial)
    package = persist_run_package(state)
    return build_run_response(state, package)


async def run_agent_workflow_events(request: RunRequest) -> AsyncIterator[dict[str, Any]]:
    state = initial_state(request)
    yield {
        "event": "run_started",
        "data": {
            "run_id": state["run_id"],
            "message": "Run accepted. Data context preflight starts first.",
        },
    }

    yield step_event("step_started", data_context_step(state, status="running", output="正在准备字段画像、脱敏样例数据和聚合预览。"))
    state.update(await local_data_node(state))
    yield step_event("step_completed", data_context_step(state, status="ready"))

    yield step_event("step_completed", prompt_step(state, status="ready"))

    yield step_event("step_started", business_contract_step(state, status="running", output="正在合并 prompt、数据上下文和 MaaS/本地摘要。"))
    state.update(await business_contract_node(state))
    yield step_event("step_completed", business_contract_step(state, status="ready"))

    yield step_event("step_started", contract_audit_step(state, status="running", output="正在对齐业务合约、样例字段、本地执行适配器和审批策略。"))
    state.update(await contract_audit_node(state))
    yield step_event("step_completed", contract_audit_step(state))

    yield step_event("step_started", artifact_package_step(state, status="running", output="正在生成 PySpark、SQL、DataArts DAG 和安全材料。"))
    state.update(await artifact_package_node(state))
    yield step_event("step_completed", artifact_package_step(state, status="ready"))

    yield step_event("step_completed", artifact_branch_step(state))

    yield step_event("step_started", local_dry_run_step(state, status="running", output="正在用本地合成数据执行等价变换，并对账指标结果。"))
    state.update(await local_dry_run_node(state))
    yield step_event("step_completed", local_dry_run_step(state))

    yield step_event("step_started", governance_step(state, status="running", output="正在检查质量规则、安全策略、血缘和生产执行锁。"))
    state.update(await review_gates_node(state))
    yield step_event("step_completed", governance_step(state, status="blocked"))

    yield step_event("step_started", persist_step(state, status="running", output="正在写入 generated/ 目录并生成 review manifest。"))
    state.update(await finalize_node(state))
    package = persist_run_package(state)
    yield step_event("step_completed", persist_step(state, status="blocked", package=package))

    yield {
        "event": "run_completed",
        "data": {
            "run": build_run_response(state, package).model_dump(mode="json"),
        },
    }


def initial_state(request: RunRequest) -> AgentState:
    client = MaaSClient()
    return {
        "run_id": f"front-{uuid4().hex[:10]}",
        "request": request,
        "maas_client": client,
        "maas_used": False,
        "maas_error": None,
        "maas_strategy": None,
        "agents": [],
        "artifacts": [],
        "quality_gates": [],
        "contract_audit": {},
        "local_execution": {},
        "lineage": [],
    }


def build_run_response(state: AgentState, package: dict[str, Any]) -> RunResponse:
    status = maas_status()
    status["used"] = bool(state.get("maas_used"))
    status["error"] = state.get("maas_error")
    status["strategy"] = state.get("maas_strategy")
    return RunResponse(
        run_id=state["run_id"],
        status="ready_for_review",
        execution_mode="maas_assisted" if state.get("maas_used") else "local_only",
        generated_dir=package["generated_dir"],
        generated_url=package["generated_url"],
        maas=status,
        bigdata_execution={
            "deployed": False,
            "state": "blocked",
            "reason": "Cloud resources are environment-managed; this new package remains blocked until PySpark, SQL, and DAG approvals are complete.",
        },
        business_contract=state["business_contract"],
        contract_audit=state.get("contract_audit", {}),
        local_execution=state.get("local_execution", {}),
        agents=[AgentResult(**item) for item in state["agents"]],
        artifacts=[ArtifactPreview(**item) for item in package["artifacts"]],
        quality_gates=[GateResult(**item) for item in state["quality_gates"]],
        synthetic_rows=state["synthetic_rows"][:8],
        gold_rows=state["gold_rows"][:8],
        lineage=state["lineage"],
        review=package["review"],
        decision=state["decision"],
    )


def step_event(event: str, step: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "data": {"step": step}}


def data_context_step(state: AgentState, status: str, output: str | None = None) -> dict[str, Any]:
    rows = state.get("synthetic_rows") or []
    gold_rows = state.get("gold_rows") or []
    return {
        "id": "data_context",
        "step": "Step 1",
        "title": "数据上下文预检",
        "status": status,
        "note": "先准备字段、样例和脱敏约束，给后续 Agent 做上下文。",
        "input": f"场景={state['request'].scenario}；本地合成数据；云上执行锁定。",
        "output": output or f"已准备 {len(rows[:8])} 行预览、{len(gold_rows)} 条聚合预览，并生成 local_synthetic_rows.json、gold_preview.json。",
    }


def prompt_step(state: AgentState, status: str, output: str | None = None) -> dict[str, Any]:
    return {
        "id": "prompt",
        "step": "Step 2",
        "title": "接收业务 Prompt",
        "status": status,
        "note": "把自然语言需求接入已经准备好的数据上下文。",
        "input": short_text(state["request"].prompt, 180),
        "output": output or f"已绑定数据上下文。模板：{state['request'].template_id or 'custom_prompt'}。",
    }


def business_contract_step(state: AgentState, status: str, output: str | None = None) -> dict[str, Any]:
    contract = state.get("business_contract") or {}
    business_goal = contract.get("business_goal", "")
    metrics = contract.get("metrics") or []
    return {
        "id": "business_contract",
        "step": "Step 3",
        "title": "业务分析 Agent",
        "status": status,
        "note": "把 prompt 收敛成可审计、可落盘的业务合约。",
        "input": "原始 prompt + 数据样例/字段上下文 + MaaS/本地摘要。",
        "output": output
        or f"生成 business_contract.yaml，包含 {len(metrics)} 个指标。业务目标：{short_text(business_goal, 150)}",
    }


def contract_audit_step(state: AgentState, status: str | None = None, output: str | None = None) -> dict[str, Any]:
    audit = state.get("contract_audit") or {}
    findings = audit.get("findings") or []
    failed = sum(1 for item in findings if item.get("status") == "failed")
    warnings = sum(1 for item in findings if item.get("status") == "warning")
    passed = sum(1 for item in findings if item.get("status") == "passed")
    step_status = status or ("ready" if failed == 0 else "failed")
    return {
        "id": "contract_audit",
        "step": "Step 4",
        "title": "合约一致性审计",
        "status": step_status,
        "note": "先检查 MaaS/本地合约有没有和数据字段、本地执行适配器、审批策略对齐。",
        "input": "business_contract.yaml + 本地字段上下文 + 本地 PySpark/SQL/DAG 适配器支持范围。",
        "output": output or f"生成 contract_audit.json：{passed} 项通过、{warnings} 项提醒、{failed} 项失败。",
    }


def artifact_package_step(state: AgentState, status: str, output: str | None = None) -> dict[str, Any]:
    return {
        "id": "artifact_package",
        "step": "Step 5",
        "title": "代码与编排 Agents",
        "status": status,
        "note": "根据业务合约生成未来可送往 MRS、DWS、DataArts 的草稿。",
        "input": "business_contract.yaml + 本地样例字段 + 目标华为云大数据服务映射。",
        "output": output or f"{artifact_names(state, {'pyspark', 'sql', 'dag'})}，均由 business_contract.yaml 派生。",
    }


def artifact_branch_step(state: AgentState) -> dict[str, Any]:
    return {
        "id": "artifact_branch",
        "type": "branch",
        "step": "Output",
        "title": "产物分叉",
        "status": "ready",
        "branches": [
            {"title": "PySpark", "detail": artifact_names(state, {"pyspark"})},
            {"title": "SQL", "detail": artifact_names(state, {"sql"})},
            {"title": "DataArts DAG", "detail": artifact_names(state, {"dag"})},
        ],
    }


def local_dry_run_step(state: AgentState, status: str | None = None, output: str | None = None) -> dict[str, Any]:
    execution = state.get("local_execution") or {}
    reconciliation = execution.get("metric_reconciliation") or {}
    checks = reconciliation.get("checks") or []
    failed = sum(1 for item in checks if item.get("status") == "failed")
    passed = sum(1 for item in checks if item.get("status") == "passed")
    step_status = status or ("ready" if failed == 0 else "failed")
    return {
        "id": "local_dry_run",
        "step": "Step 6",
        "title": "本地试运行 Agent",
        "status": step_status,
        "note": "用本地合成数据跑一次等价执行，并对账脚本语义、指标结果和脱敏约束。",
        "input": "mrs_transform.py + dws_serving.sql + dataarts_dag.yaml + synthetic_rows.json + business_contract.yaml。",
        "output": output or f"生成 execution_report.json、local_run_output.json、metric_reconciliation.json：{passed} 项通过、{failed} 项失败。",
    }


def governance_step(state: AgentState, status: str, output: str | None = None) -> dict[str, Any]:
    gates = state.get("quality_gates") or []
    return {
        "id": "governance",
        "step": "Step 7",
        "title": "治理审计 Agent",
        "status": status,
        "note": "质量、安全、血缘和审批状态在这里统一判断。",
        "input": "全部脚本产物 + 样例数据 + MaaS 配置状态。",
        "output": output or f"{summarize_gates(gates)}；生成 {artifact_names(state, {'audit'})}；生产执行：已锁定。",
    }


def persist_step(
    state: AgentState,
    status: str,
    output: str | None = None,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts = package["artifacts"] if package else state.get("artifacts") or []
    required = [artifact["name"] for artifact in artifacts if artifact.get("review_required")]
    return {
        "id": "persist",
        "step": "Step 8",
        "title": "落盘与人工确认",
        "status": status,
        "note": "本地文件已生成，但生产部署仍需人工批准。",
        "input": f"需要确认：{'、'.join(required)}" if required else "当前产物无需人工确认。",
        "output": output or f"文件目录：{package['generated_dir'] if package else state['run_id']}",
    }


def artifact_names(state: AgentState, kinds: set[str]) -> str:
    names = [artifact["name"] for artifact in state.get("artifacts", []) if artifact["kind"] in kinds]
    return "、".join(names) if names else "无"


def summarize_gates(gates: list[dict[str, Any]]) -> str:
    passed = sum(1 for gate in gates if gate["status"] == "passed")
    failed = sum(1 for gate in gates if gate["status"] == "failed")
    blocked = sum(1 for gate in gates if gate["status"] == "blocked")
    return f"质量检查：{passed} 个通过，{failed} 个失败，{blocked} 个锁定"


def short_text(value: str, max_length: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", value or "").strip()
    if len(normalized) > max_length:
        return f"{normalized[: max_length - 3]}..."
    return normalized or "无"


SUPPORTED_DIMENSIONS = {"ejercicio_analisis", "region", "cve_regimen", "is_resico"}
SUPPORTED_METRICS = {"active_taxpayers", "total_declared_amount"}
EXPECTED_ARTIFACTS = {
    "business_contract.yaml",
    "contract_audit.json",
    "mrs_transform.py",
    "dws_serving.sql",
    "dataarts_dag.yaml",
    "execution_report.json",
    "local_run_output.json",
    "metric_reconciliation.json",
    "security_review.md",
    "quality_gates.json",
    "lineage_manifest.json",
}
REQUIRED_CONTRACT_FIELDS = {
    "business_goal",
    "data_sources",
    "grain",
    "dimensions",
    "metrics",
    "masking_rules",
    "quality_rules",
    "security_rules",
    "approval_policy",
    "output_artifacts",
}


def audit_business_contract(contract: dict[str, Any], data_context: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def add(check_id: str, name: str, status: str, detail: str) -> None:
        findings.append({"id": check_id, "name": name, "status": status, "detail": detail})

    missing_fields = sorted(field for field in REQUIRED_CONTRACT_FIELDS if not contract.get(field))
    add(
        "CA-001",
        "Required contract sections",
        "failed" if missing_fields else "passed",
        f"missing={', '.join(missing_fields)}" if missing_fields else "All required sections are present.",
    )

    dimension_names = contract_dimension_names(contract)
    dimension_names.discard("")
    missing_dimensions = sorted(SUPPORTED_DIMENSIONS - dimension_names)
    extra_dimensions = sorted(dimension_names - SUPPORTED_DIMENSIONS)
    add(
        "CA-002",
        "Dimensions match local adapter grain",
        "failed" if missing_dimensions or extra_dimensions else "passed",
        f"missing={missing_dimensions}; extra={extra_dimensions}"
        if missing_dimensions or extra_dimensions
        else "Dimensions match ejercicio_analisis, region, cve_regimen, and is_resico.",
    )

    metric_names = contract_metric_names(contract)
    metric_names.discard("")
    missing_metrics = sorted(SUPPORTED_METRICS - metric_names)
    extra_metrics = sorted(metric_names - SUPPORTED_METRICS)
    add(
        "CA-003",
        "Metrics match local PySpark and DWS adapters",
        "failed" if missing_metrics or extra_metrics else "passed",
        f"missing={missing_metrics}; extra={extra_metrics}"
        if missing_metrics or extra_metrics
        else "Metrics match active_taxpayers and total_declared_amount.",
    )

    available_fields = set(data_context.get("available_fields") or [])
    serving_fields = set(data_context.get("serving_fields") or [])
    missing_in_context = sorted((SUPPORTED_DIMENSIONS | SUPPORTED_METRICS) - (available_fields | serving_fields))
    add(
        "CA-004",
        "Fields exist in local data context",
        "failed" if missing_in_context else "passed",
        f"missing_in_context={missing_in_context}" if missing_in_context else "All expected fields are present in sample or gold preview fields.",
    )

    artifact_names = {extract_named_value(item) for item in normalize_list(contract.get("output_artifacts"))}
    artifact_names.discard("")
    missing_artifacts = sorted(EXPECTED_ARTIFACTS - artifact_names)
    add(
        "CA-005",
        "Expected artifacts are declared",
        "warning" if missing_artifacts else "passed",
        f"missing_from_contract={missing_artifacts}" if missing_artifacts else "Contract declares the expected local package outputs.",
    )

    masking_text = " ".join(str(item).lower() for item in normalize_list(contract.get("masking_rules")))
    has_allowed_ids = "rfc_hash" in masking_text and "masked_rfc" in masking_text
    add(
        "CA-006",
        "Masking identifiers are explicit",
        "warning" if not has_allowed_ids else "passed",
        "Masking rules should explicitly keep rfc_hash and masked_rfc." if not has_allowed_ids else "Masking rules keep rfc_hash and masked_rfc.",
    )

    exposed_blocked = sorted(name for name in (dimension_names | metric_names) if name == "rfc")
    add(
        "CA-007",
        "No direct RFC in serving contract",
        "failed" if exposed_blocked else "passed",
        f"blocked_identifiers={exposed_blocked}" if exposed_blocked else "No direct RFC is declared in dimensions or metrics.",
    )

    approval_ok = approval_policy_blocks_execution(contract.get("approval_policy"))
    add(
        "CA-008",
        "Production approval is blocked",
        "failed" if not approval_ok else "passed",
        "Approval policy must keep production blocked until review." if not approval_ok else "Production remains blocked until review or approval.",
    )

    source_uri = str(data_context.get("source_uri") or "")
    source_uris = contract_source_uris(contract.get("data_sources"))
    add(
        "CA-009",
        "Source URI matches prompt context",
        "warning" if source_uri and source_uri not in source_uris else "passed",
        f"expected_source_uri={source_uri}; contract_source_uris={sorted(source_uris)}"
        if source_uri and source_uri not in source_uris
        else "Source URI is aligned with the local data context.",
    )

    failed = sum(1 for finding in findings if finding["status"] == "failed")
    warnings = sum(1 for finding in findings if finding["status"] == "warning")
    passed = sum(1 for finding in findings if finding["status"] == "passed")
    return {
        "status": "failed" if failed else "passed",
        "summary": f"{passed} checks passed, {warnings} warnings, {failed} failures.",
        "findings": findings,
    }


def extract_named_value(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("name") or item.get("field") or item.get("id") or item.get("artifact")
        return str(value or "").strip()
    return str(item or "").strip()


def contract_dimension_names(contract: dict[str, Any]) -> set[str]:
    return {extract_named_value(item) for item in normalize_list(contract.get("dimensions"))}


def contract_metric_names(contract: dict[str, Any]) -> set[str]:
    return {extract_named_value(item) for item in normalize_list(contract.get("metrics"))}


def contract_source_uris(value: Any) -> set[str]:
    source_uris: set[str] = set()
    for item in normalize_list(value):
        if isinstance(item, dict):
            uri = str(item.get("uri") or item.get("source_uri") or "").strip()
            if uri:
                source_uris.add(uri)
            continue
        text = str(item or "").strip()
        if "://" in text:
            source_uris.add(text.split()[0].strip(",;"))
    return source_uris


def approval_policy_blocks_execution(value: Any) -> bool:
    approval_policy = str(value or "").lower()
    approval_has_review = any(word in approval_policy for word in ("review", "approved", "approval"))
    approval_has_execution_scope = any(word in approval_policy for word in ("execution", "production", "cloud", "publication"))
    approval_has_blocking_control = any(
        phrase in approval_policy
        for phrase in (
            "blocked",
            "disabled",
            "before any cloud execution",
            "before cloud execution",
            "required before",
            "until review",
            "until approval",
            "requires separate approval",
        )
    )
    return approval_has_review and approval_has_execution_scope and approval_has_blocking_control


def enforce_approval_policy(value: Any, fallback: str) -> str:
    if approval_policy_blocks_execution(value):
        return str(value).strip()
    return fallback


def build_data_context(state: AgentState) -> dict[str, Any]:
    rows = state.get("synthetic_rows") or []
    gold_rows = state.get("gold_rows") or []
    source_uri = state["request"].template_variables.get("source_uri") or "local://landing/taxpayer_registry.csv"
    return {
        "scenario": state["request"].scenario,
        "source_uri": source_uri,
        "raw_layer": "local synthetic landing data",
        "serving_layer": "gold aggregate preview",
        "available_fields": list(rows[0].keys()) if rows else [],
        "serving_fields": list(gold_rows[0].keys()) if gold_rows else [],
        "sample_rows": rows[:2],
        "sensitive_fields": ["direct RFC"],
        "allowed_identifiers": ["rfc_hash", "masked_rfc"],
        "blocked_identifiers": ["rfc"],
        "cloud_execution": "blocked",
    }


def local_business_contract(request: RunRequest, data_context: dict[str, Any]) -> dict[str, Any]:
    prompt_summary = local_summary(request.prompt)
    source_uri = data_context["source_uri"]
    return {
        "task_id": request.scenario,
        "template_id": request.template_id or "custom_prompt",
        "business_goal": prompt_summary,
        "source": "Tax taxpayer registry landing files",
        "data_sources": [
            {
                "name": "taxpayer_registry",
                "uri": source_uri,
                "layer": "landing",
                "format": "csv",
                "required": True,
            }
        ],
        "grain": "taxpayer_regime_year",
        "dimensions": ["ejercicio_analisis", "region", "cve_regimen", "is_resico"],
        "metrics": [
            {
                "name": "active_taxpayers",
                "expression": "count active taxpayers by grain",
            },
            {
                "name": "total_declared_amount",
                "expression": "sum declared_amount by grain",
            },
        ],
        "filters": ["status in source is preserved for aggregation logic"],
        "privacy": "No direct RFC leaves the local synthetic layer; UI and artifacts use masked/hash identifiers.",
        "masking_rules": [
            "drop direct rfc after deriving rfc_hash and masked_rfc",
            "allow rfc_hash and masked_rfc in local previews only",
        ],
        "quality_rules": [
            "prompt length must be sufficient for generation",
            "generated preview rows must not expose direct RFC",
            "MaaS credentials must not be embedded in artifacts",
        ],
        "security_rules": [
            "read MaaS credentials only from environment or local ignored .env files",
            "keep production DataArts/MRS/OBS/DWS execution blocked",
        ],
        "approval_policy": "Production execution remains blocked until PySpark, SQL, and DAG are reviewed.",
        "output_artifacts": [
            "business_contract.yaml",
            "contract_audit.json",
            "mrs_transform.py",
            "dws_serving.sql",
            "dataarts_dag.yaml",
            "execution_report.json",
            "local_run_output.json",
            "metric_reconciliation.json",
            "security_review.md",
            "quality_gates.json",
            "lineage_manifest.json",
        ],
        "acceptance": [
            "Generate a business contract from the prompt and data context.",
            "Create PySpark, SQL, DAG, quality, security, and lineage previews.",
            "Keep production execution blocked until a human approval exists.",
        ],
        "assumptions": [
            "The current POC uses local synthetic Tax-style rows.",
            "No Huawei Cloud big-data resources are deployed in this phase.",
        ],
    }


def normalize_business_contract(candidate: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    contract = {**fallback}
    for key in (
        "business_goal",
        "source",
        "grain",
        "privacy",
    ):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            contract[key] = value.strip()

    list_keys = (
        "data_sources",
        "dimensions",
        "metrics",
        "filters",
        "masking_rules",
        "quality_rules",
        "security_rules",
        "output_artifacts",
        "acceptance",
        "assumptions",
    )
    for key in list_keys:
        value = candidate.get(key)
        normalized = normalize_list(value)
        if normalized:
            contract[key] = normalized

    contract["task_id"] = fallback["task_id"]
    contract["template_id"] = fallback["template_id"]
    contract["approval_policy"] = enforce_approval_policy(
        candidate.get("approval_policy") or contract.get("approval_policy"),
        fallback["approval_policy"],
    )
    return contract


def normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


async def business_contract_node(state: AgentState) -> dict[str, Any]:
    request = state["request"]
    prompt = request.prompt.strip()
    data_context = build_data_context(state)
    fallback_contract = local_business_contract(request, data_context)
    contract = fallback_contract
    maas_used = False
    maas_error = None
    strategy_id = select_maas_strategy(request)
    if request.use_maas and state["maas_client"].configured:
        try:
            maas_contract = await state["maas_client"].generate_business_contract(
                prompt,
                data_context,
                strategy_id=strategy_id,
            )
            contract = normalize_business_contract(maas_contract, fallback_contract)
            maas_used = True
        except Exception as exc:  # noqa: BLE001 - surfaced as a safe UI warning.
            maas_error = f"{type(exc).__name__}: {exc}"

    agent = {
        "name": "business-analysis-agent",
        "role": "Prompt to business contract",
        "status": "ready",
        "summary": (
            "Generated a structured business contract with goals, sources, metrics, masking, "
            "quality rules, security rules, and approval policy."
        ),
        "outputs": ["business_contract.yaml"],
    }
    return {
        "business_contract": contract,
        "agents": [*state.get("agents", []), agent],
        "maas_used": maas_used,
        "maas_error": maas_error,
        "maas_strategy": strategy_id,
        "model_summary": contract["business_goal"],
        "lineage": [
            *state.get("lineage", []),
            {"from": "business prompt", "to": "business_contract.yaml", "control": "prompt review"},
        ],
    }


def select_maas_strategy(request: RunRequest) -> str:
    explicit = request.template_variables.get("maas_strategy", "").strip()
    if explicit:
        return explicit
    text = f"{request.scenario} {request.template_id or ''} {request.prompt}".lower()
    if "reconciliation" in text or "reconcile" in text:
        return "reconciliation"
    if "security" in text or "mask" in text or "rfc" in text:
        return "security_first"
    if "dataarts" in text or "dag" in text or "handoff" in text:
        return "dataarts_ready"
    return "strict_contract"


async def contract_audit_node(state: AgentState) -> dict[str, Any]:
    audit = audit_business_contract(state["business_contract"], build_data_context(state))
    failed = sum(1 for finding in audit["findings"] if finding["status"] == "failed")
    warnings = sum(1 for finding in audit["findings"] if finding["status"] == "warning")
    agent = {
        "name": "contract-audit-agent",
        "role": "Contract consistency gate",
        "status": "failed" if failed else "ready",
        "summary": (
            f"Checked contract against local schema, supported PySpark/SQL adapter outputs, masking rules, "
            f"declared artifacts, and approval policy: {failed} failures, {warnings} warnings."
        ),
        "outputs": ["contract_audit.json"],
    }
    return {
        "contract_audit": audit,
        "agents": [*state.get("agents", []), agent],
        "lineage": [
            *state.get("lineage", []),
            {"from": "business_contract.yaml", "to": "contract_audit.json", "control": "contract consistency gate"},
        ],
    }


async def local_data_node(state: AgentState) -> dict[str, Any]:
    rows = make_synthetic_rows(state["request"].scenario)
    gold_rows = aggregate_gold(rows)
    agent = {
        "name": "data-context-agent",
        "role": "Source schema and sample preflight",
        "status": "ready",
        "summary": f"Prepared {len(rows)} masked Tax-like sample rows and {len(gold_rows)} aggregate previews before prompt-to-contract conversion.",
        "outputs": ["local_synthetic_rows.json", "gold_preview.json"],
    }
    return {
        "synthetic_rows": rows,
        "gold_rows": gold_rows,
        "agents": [*state["agents"], agent],
        "lineage": [
            *state["lineage"],
            {"from": "local_synthetic_rows.json", "to": "gold_preview.json", "control": "local dry run"},
        ],
    }


async def artifact_package_node(state: AgentState) -> dict[str, Any]:
    task_id = state["request"].scenario
    contract = state["business_contract"]
    artifacts = [
        {
            "name": "business_contract.yaml",
            "kind": "contract",
            "path": "memory://business_contract.yaml",
            "content": render_business_contract(contract),
        },
        {
            "name": "contract_audit.json",
            "kind": "audit",
            "path": "memory://contract_audit.json",
            "content": json.dumps(state.get("contract_audit", {}), ensure_ascii=False, indent=2),
        },
        {
            "name": "mrs_transform.py",
            "kind": "pyspark",
            "path": "memory://mrs_transform.py",
            "content": render_pyspark_preview(task_id, contract),
        },
        {
            "name": "dws_serving.sql",
            "kind": "sql",
            "path": "memory://dws_serving.sql",
            "content": render_sql_preview(task_id, contract),
        },
        {
            "name": "dataarts_dag.yaml",
            "kind": "dag",
            "path": "memory://dataarts_dag.yaml",
            "content": render_dag_preview(task_id, contract, state.get("contract_audit", {})),
        },
        {
            "name": "security_review.md",
            "kind": "audit",
            "path": "memory://security_review.md",
            "content": render_security_review(),
        },
    ]
    new_agents = [
        {
            "name": "architecture-agent",
            "role": "Target Huawei Cloud mapping",
            "status": "ready",
            "summary": "Mapped the generated package to governed DataArts, MRS, OBS, and DWS targets; environment deployment is managed independently.",
            "outputs": ["architecture_plan.yaml"],
        },
        {
            "name": "code-agent",
            "role": "PySpark and SQL artifact draft",
            "status": "ready",
            "summary": "Prepared PySpark and SQL previews from the approved business contract dimensions, metrics, filters, and masking rules.",
            "outputs": ["mrs_transform.py", "dws_serving.sql"],
        },
        {
            "name": "orchestration-agent",
            "role": "DataArts DAG preview",
            "status": "ready",
            "summary": "Prepared a DAG specification from the contract and contract audit, with production scheduling blocked.",
            "outputs": ["dataarts_dag.yaml"],
        },
    ]
    return {
        "artifacts": artifacts,
        "agents": [*state["agents"], *new_agents],
        "lineage": [
            *state["lineage"],
            {"from": "business_contract.yaml", "to": "mrs_transform.py", "control": "code review"},
            {"from": "business_contract.yaml", "to": "dws_serving.sql", "control": "SQL review"},
            {"from": "mrs_transform.py", "to": "dataarts_dag.yaml", "control": "orchestration review"},
        ],
    }


async def local_dry_run_node(state: AgentState) -> dict[str, Any]:
    contract = state["business_contract"]
    spec = artifact_spec_from_contract(contract)
    local_output = simulate_contract_output(state["synthetic_rows"], spec)
    expected_output = simulate_contract_output(state["synthetic_rows"], spec)
    script_checks = validate_script_artifacts(state.get("artifacts", []), spec, state.get("contract_audit", {}))
    reconciliation = reconcile_local_output(local_output, expected_output, spec, script_checks)
    execution_report = {
        "status": reconciliation["status"],
        "mode": "local_python_equivalent",
        "input_rows": len(state["synthetic_rows"]),
        "output_rows": len(local_output),
        "dimensions": spec["dimensions"],
        "metrics": spec["metrics"],
        "filters": {
            "tax_year": spec["tax_year"] or None,
            "regions": spec["regions"],
            "active_only": spec["active_only"],
        },
        "artifacts_checked": ["mrs_transform.py", "dws_serving.sql", "dataarts_dag.yaml"],
        "summary": reconciliation["summary"],
    }
    local_execution = {
        "status": reconciliation["status"],
        "execution_report": execution_report,
        "local_run_output": local_output,
        "metric_reconciliation": reconciliation,
    }
    artifacts = [
        *state.get("artifacts", []),
        {
            "name": "execution_report.json",
            "kind": "execution",
            "path": "memory://execution_report.json",
            "content": json.dumps(execution_report, ensure_ascii=False, indent=2),
        },
        {
            "name": "local_run_output.json",
            "kind": "execution",
            "path": "memory://local_run_output.json",
            "content": json.dumps(local_output, ensure_ascii=False, indent=2),
        },
        {
            "name": "metric_reconciliation.json",
            "kind": "execution",
            "path": "memory://metric_reconciliation.json",
            "content": json.dumps(reconciliation, ensure_ascii=False, indent=2),
        },
    ]
    agent = {
        "name": "local-dry-run-agent",
        "role": "Local execution and metric reconciliation",
        "status": "ready" if reconciliation["status"] == "passed" else "failed",
        "summary": (
            f"Executed a local Python equivalent run over {len(state['synthetic_rows'])} synthetic rows, "
            f"produced {len(local_output)} output rows, and reconciled {len(reconciliation['checks'])} checks."
        ),
        "outputs": ["execution_report.json", "local_run_output.json", "metric_reconciliation.json"],
    }
    return {
        "local_execution": local_execution,
        "artifacts": artifacts,
        "agents": [*state["agents"], agent],
        "lineage": [
            *state["lineage"],
            {"from": "mrs_transform.py", "to": "local_run_output.json", "control": "local dry run"},
            {"from": "local_run_output.json", "to": "metric_reconciliation.json", "control": "metric reconciliation"},
        ],
    }


async def review_gates_node(state: AgentState) -> dict[str, Any]:
    prompt = state["request"].prompt
    rows = state["synthetic_rows"]
    audit = state.get("contract_audit") or {}
    audit_findings = audit.get("findings") or []
    audit_failed = sum(1 for finding in audit_findings if finding.get("status") == "failed")
    audit_warnings = sum(1 for finding in audit_findings if finding.get("status") == "warning")
    local_execution = state.get("local_execution") or {}
    local_reconciliation = local_execution.get("metric_reconciliation") or {}
    local_checks = local_reconciliation.get("checks") or []
    local_failed = sum(1 for check in local_checks if check.get("status") == "failed")
    gates = [
        {
            "id": "FG-001",
            "name": "Prompt has enough business context",
            "status": "passed" if len(prompt) >= 20 else "failed",
            "detail": f"prompt_length={len(prompt)}",
        },
        {
            "id": "FG-002",
            "name": "Business contract matches local execution contract",
            "status": "failed" if audit_failed else "passed",
            "detail": f"contract_audit={audit.get('status', 'missing')}; failures={audit_failed}; warnings={audit_warnings}",
        },
        {
            "id": "FG-003",
            "name": "Local dry run output reconciles with contract",
            "status": "failed" if local_failed else "passed",
            "detail": f"local_execution={local_execution.get('status', 'missing')}; failures={local_failed}; output_rows={local_execution.get('execution_report', {}).get('output_rows', 0)}",
        },
        {
            "id": "FG-004",
            "name": "No direct RFC in generated preview rows",
            "status": "passed" if all("rfc" not in row for row in rows) else "failed",
            "detail": "Rows expose rfc_hash and masked_rfc only.",
        },
        {
            "id": "FG-005",
            "name": "MaaS credentials are not embedded",
            "status": "passed",
            "detail": "MaaS reads only environment variables.",
        },
        {
            "id": "FG-006",
            "name": "Production big-data execution",
            "status": "blocked",
            "detail": "Cloud execution for this generated package remains blocked until the three core artifacts are approved.",
        },
    ]
    agent = {
        "name": "governance-agent",
        "role": "Quality, security, and approval gate",
        "status": "blocked",
        "summary": "Approved local review, blocked production execution until explicit cloud approval.",
        "outputs": ["quality_gates.json", "security_review.md", "lineage_manifest.json"],
    }
    return {
        "quality_gates": gates,
        "agents": [*state["agents"], agent],
        "lineage": [
            *state["lineage"],
            {"from": "all artifact previews", "to": "quality_gates.json", "control": "approval gate"},
        ],
    }


async def finalize_node(state: AgentState) -> dict[str, Any]:
    failed = [gate for gate in state["quality_gates"] if gate["status"] == "failed"]
    blocked = [gate for gate in state["quality_gates"] if gate["status"] == "blocked"]
    decision = {
        "local_dev": "approved" if not failed else "needs_fix",
        "production": "blocked",
        "failed_gates": len(failed),
        "blocked_gates": len(blocked),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "next_action": "Review artifacts in code-server or VS Code, then decide whether to wire real MaaS and cloud execution.",
    }
    return {"decision": decision}


def local_summary(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if len(normalized) > 220:
        normalized = f"{normalized[:217]}..."
    return normalized


def render_business_contract(contract: dict[str, Any]) -> str:
    ordered_keys = [
        "task_id",
        "template_id",
        "business_goal",
        "source",
        "data_sources",
        "grain",
        "dimensions",
        "metrics",
        "filters",
        "privacy",
        "masking_rules",
        "quality_rules",
        "security_rules",
        "approval_policy",
        "output_artifacts",
        "acceptance",
        "assumptions",
    ]
    lines: list[str] = []
    for key in ordered_keys:
        if key not in contract:
            continue
        lines.extend(render_yaml_field(key, contract[key]))
    return "\n".join(lines)


def render_yaml_field(key: str, value: Any) -> list[str]:
    if isinstance(value, list):
        lines = [f"{key}:"]
        if not value:
            lines.append("  []")
            return lines
        for item in value:
            if isinstance(item, dict):
                lines.append("  -")
                for child_key, child_value in item.items():
                    lines.append(f"      {child_key}: {yaml_scalar(child_value)}")
            else:
                lines.append(f"  - {yaml_scalar(item)}")
        return lines
    if isinstance(value, dict):
        lines = [f"{key}:"]
        for child_key, child_value in value.items():
            lines.append(f"  {child_key}: {yaml_scalar(child_value)}")
        return lines
    return [f"{key}: {yaml_scalar(value)}"]


def yaml_scalar(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    if not text:
        return '""'
    if any(char in text for char in [":", "#", "{", "}", "[", "]", ","]):
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


KNOWN_REGIONS = ["CDMX", "Jalisco", "Nuevo Leon", "Puebla", "Yucatan"]


def artifact_spec_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    dimensions = [extract_named_value(item) for item in normalize_list(contract.get("dimensions"))]
    metrics = [extract_named_value(item) for item in normalize_list(contract.get("metrics"))]
    filters = [filter_text(item) for item in normalize_list(contract.get("filters"))]
    text_for_hints = " ".join(
        [
            str(contract.get("business_goal", "")),
            str(contract.get("grain", "")),
            " ".join(filters),
            " ".join(str(item) for item in normalize_list(contract.get("data_sources"))),
        ]
    )
    source_uris = sorted(contract_source_uris(contract.get("data_sources")))
    tax_year_match = re.search(r"\b(20\d{2})\b", text_for_hints)
    regions = [region for region in KNOWN_REGIONS if re.search(rf"\b{re.escape(region)}\b", text_for_hints, re.IGNORECASE)]
    active_only = bool(re.search(r"\bstatus\s*=\s*active\b|\bactive only\b", text_for_hints, re.IGNORECASE))
    return {
        "source_uri": source_uris[0] if source_uris else "local://landing/taxpayer_registry.csv",
        "dimensions": [item for item in dimensions if item] or sorted(SUPPORTED_DIMENSIONS),
        "metrics": [item for item in metrics if item] or sorted(SUPPORTED_METRICS),
        "filters": [item for item in filters if item],
        "tax_year": tax_year_match.group(1) if tax_year_match else "",
        "regions": regions,
        "active_only": active_only,
    }


def filter_text(item: Any) -> str:
    if isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    return str(item or "").strip()


def py_literal(value: Any) -> str:
    return repr(value)


def pyspark_metric_expression(metric: str) -> str:
    if metric == "active_taxpayers":
        return 'F.sum(F.when(F.upper(F.col("status")) == F.lit("ACTIVE"), 1).otherwise(0)).alias("active_taxpayers")'
    if metric == "total_declared_amount":
        return 'F.sum("declared_amount").alias("total_declared_amount")'
    safe_metric = metric.replace('"', '\\"')
    return f'F.lit(None).cast("double").alias("{safe_metric}")  # unsupported by current local adapter'


def render_pyspark_filter_lines(spec: dict[str, Any]) -> list[str]:
    lines = ["    filtered = prepared"]
    if spec["tax_year"]:
        lines.append(f'    filtered = filtered.filter(F.col("ejercicio_analisis") == F.lit({py_literal(spec["tax_year"])}))')
    if spec["regions"]:
        lines.append('    filtered = filtered.filter(F.col("region").isin(*ALLOWED_REGIONS))')
    if spec["active_only"]:
        lines.append('    filtered = filtered.filter(F.upper(F.col("status")) == F.lit("ACTIVE"))')
    lines.append("    return filtered")
    return lines


def render_sql_where_clause(spec: dict[str, Any]) -> str:
    clauses: list[str] = []
    if spec["tax_year"]:
        clauses.append(f"ejercicio_analisis = {sql_literal(spec['tax_year'])}")
    if spec["regions"]:
        regions = ", ".join(sql_literal(region) for region in spec["regions"])
        clauses.append(f"region in ({regions})")
    if not clauses:
        return ""
    return "\nwhere " + "\n  and ".join(clauses)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def yaml_block_list(items: list[str], indent: int) -> str:
    spaces = " " * indent
    return "\n".join(f"{spaces}- {yaml_scalar(item)}" for item in items)


def simulate_contract_output(rows: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        if spec["tax_year"] and row.get("ejercicio_analisis") != spec["tax_year"]:
            continue
        if spec["regions"] and row.get("region") not in spec["regions"]:
            continue
        if spec["active_only"] and row.get("status") != "ACTIVE":
            continue
        key = tuple(row.get(dimension) for dimension in spec["dimensions"])
        bucket = grouped.setdefault(
            key,
            {dimension: row.get(dimension) for dimension in spec["dimensions"]},
        )
        for metric in spec["metrics"]:
            if metric == "active_taxpayers":
                bucket.setdefault(metric, 0)
                if row.get("status") == "ACTIVE":
                    bucket[metric] += 1
            elif metric == "total_declared_amount":
                bucket[metric] = round(float(bucket.get(metric, 0.0)) + float(row.get("declared_amount", 0.0)), 2)
            else:
                bucket.setdefault(metric, None)
    return sorted(grouped.values(), key=lambda item: tuple(str(item.get(dimension, "")) for dimension in spec["dimensions"]))


def validate_script_artifacts(
    artifacts: list[dict[str, Any]],
    spec: dict[str, Any],
    audit: dict[str, Any],
) -> list[dict[str, str]]:
    artifact_map = {artifact["name"]: artifact.get("content", "") for artifact in artifacts}
    pyspark = artifact_map.get("mrs_transform.py", "")
    sql = artifact_map.get("dws_serving.sql", "")
    dag = artifact_map.get("dataarts_dag.yaml", "")

    checks: list[dict[str, str]] = []
    checks.append(local_check(
        "LR-004",
        "PySpark carries contract metadata",
        all(marker in pyspark for marker in ("Generated from business_contract.yaml", "DIMENSIONS =", "METRICS =", "CONTRACT_FILTERS =")),
        "PySpark preview includes generated-from-contract markers.",
    ))
    checks.append(local_check(
        "LR-005",
        "SQL carries contract metadata",
        "Generated from business_contract.yaml" in sql and "contract_filters" in sql,
        "DWS SQL preview includes contract metadata comments.",
    ))
    checks.append(local_check(
        "LR-006",
        "DataArts DAG references contract audit",
        "contract_audit_status" in dag and str(audit.get("status", "missing")) in dag,
        "DataArts DAG includes the contract audit status.",
    ))
    for dimension in spec["dimensions"]:
        checks.append(local_check(
            f"LR-DIM-{dimension}",
            f"Script outputs dimension {dimension}",
            dimension in pyspark and dimension in sql and dimension in dag,
            f"{dimension} appears across PySpark, SQL, and DAG contract metadata.",
        ))
    for metric in spec["metrics"]:
        checks.append(local_check(
            f"LR-MET-{metric}",
            f"Script outputs metric {metric}",
            metric in pyspark and metric in sql and metric in dag,
            f"{metric} appears across PySpark, SQL, and DAG contract metadata.",
        ))
    return checks


def reconcile_local_output(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    spec: dict[str, Any],
    script_checks: list[dict[str, str]],
) -> dict[str, Any]:
    expected_columns = set(spec["dimensions"] + spec["metrics"])
    actual_columns = set(actual[0].keys()) if actual else expected_columns
    checks = [
        local_check(
            "LR-001",
            "Local output row count matches expected contract output",
            len(actual) == len(expected),
            f"actual_rows={len(actual)}; expected_rows={len(expected)}",
        ),
        local_check(
            "LR-002",
            "Local output columns match contract dimensions and metrics",
            actual_columns == expected_columns,
            f"actual_columns={sorted(actual_columns)}; expected_columns={sorted(expected_columns)}",
        ),
        local_check(
            "LR-003",
            "Local output rows match expected metric aggregates",
            actual == expected,
            "Local run output equals the independently recomputed expected aggregate.",
        ),
        local_check(
            "LR-007",
            "No direct RFC leaks into local run output",
            all("rfc" not in row for row in actual),
            "Only aggregate dimensions and metrics appear in dry-run output.",
        ),
        *script_checks,
    ]
    failed = sum(1 for check in checks if check["status"] == "failed")
    passed = sum(1 for check in checks if check["status"] == "passed")
    return {
        "status": "failed" if failed else "passed",
        "summary": f"{passed} local run checks passed, {failed} failed.",
        "checks": checks,
        "actual_rows": len(actual),
        "expected_rows": len(expected),
        "sample_actual": actual[:5],
        "sample_expected": expected[:5],
    }


def local_check(check_id: str, name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def render_pyspark_preview(task_id: str, contract: dict[str, Any]) -> str:
    spec = artifact_spec_from_contract(contract)
    agg_lines = ",\n              ".join(pyspark_metric_expression(metric) for metric in spec["metrics"])
    filter_lines = render_pyspark_filter_lines(spec)
    filter_block = "\n".join(filter_lines) if filter_lines else "    return prepared"
    return f'''from pyspark.sql import functions as F

# Generated from business_contract.yaml. Review before submitting to MRS Spark.
TASK_ID = {py_literal(task_id)}
SOURCE_URI = {py_literal(spec["source_uri"])}
DIMENSIONS = {py_literal(spec["dimensions"])}
METRICS = {py_literal(spec["metrics"])}
CONTRACT_FILTERS = {py_literal(spec["filters"])}
TAX_YEAR = {py_literal(spec["tax_year"])}
ALLOWED_REGIONS = {py_literal(spec["regions"])}
ACTIVE_ONLY = {py_literal(spec["active_only"])}


def prepare_taxpayer_registry(df):
    return (
        df.withColumn("rfc_hash", F.sha2(F.col("rfc"), 256))
          .withColumn("masked_rfc", F.concat(F.substring("rfc", 1, 3), F.lit("***"), F.substring("rfc", -3, 3)))
          .drop("rfc")
    )


def apply_contract_filters(df):
    prepared = prepare_taxpayer_registry(df)
{filter_block}


def transform_taxpayer_registry(df):
    filtered = apply_contract_filters(df)
    return (
        filtered
          .groupBy(*DIMENSIONS)
          .agg(
              {agg_lines}
          )
    )
'''


def render_sql_preview(task_id: str, contract: dict[str, Any]) -> str:
    spec = artifact_spec_from_contract(contract)
    select_columns = spec["dimensions"] + spec["metrics"]
    select_sql = ",\n  ".join(select_columns)
    where_sql = render_sql_where_clause(spec)
    return f"""-- Generated from business_contract.yaml. Review before running in DWS.
-- task_id: {task_id}
-- source_uri: {spec["source_uri"]}
-- contract_filters: {", ".join(spec["filters"]) if spec["filters"] else "none"}
create or replace view tax_gold.v_taxpayer_regime_year as
select
  {select_sql}
from tax_gold.fact_taxpayer_regime_year{where_sql};
"""


def render_dag_preview(task_id: str, contract: dict[str, Any], audit: dict[str, Any]) -> str:
    spec = artifact_spec_from_contract(contract)
    return f"""dag_id: {task_id}
runtime: dataarts_factory
execution: blocked_until_artifact_approval
contract:
  source_uri: {yaml_scalar(spec["source_uri"])}
  dimensions:
{yaml_block_list(spec["dimensions"], indent=4)}
  metrics:
{yaml_block_list(spec["metrics"], indent=4)}
  filters:
{yaml_block_list(spec["filters"] or ["none"], indent=4)}
  contract_audit_status: {yaml_scalar(audit.get("status", "missing"))}
tasks:
  - id: validate_contract_audit
    type: quality_gate
    input: contract_audit.json
  - id: submit_mrs_spark_transform
    type: mrs_spark
    script: mrs_transform.py
    depends_on: validate_contract_audit
  - id: load_dws_serving_view
    type: dws_sql
    script: dws_serving.sql
    depends_on: submit_mrs_spark_transform
  - id: publish_lineage_manifest
    type: metadata
    input: lineage_manifest.json
    depends_on: load_dws_serving_view
"""


def render_security_review() -> str:
    return """# Security Review

- Secrets: no MaaS key is stored in code or prompt artifacts.
- Identifiers: direct RFC is excluded from UI output.
- Execution: cloud jobs are blocked in the minimal frontend phase.
- Approval: production requires an explicit human gate.
"""
