from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    prompt: str = Field(min_length=20)
    scenario: str = "tax_taxpayer_annual_base"
    use_maas: bool = False
    template_id: str | None = None
    template_variables: dict[str, str] = Field(default_factory=dict)


class ChatBIRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=6)
    locale: Literal["zh", "en"] = "zh"


class ChatBIResponse(BaseModel):
    handled: bool
    available: bool
    answer: str
    kpis: list[dict[str, Any]]
    chart: dict[str, Any]
    table: dict[str, Any]
    query_plan: dict[str, Any]
    source: dict[str, Any]
    suggestions: list[str]


class PromptTemplateVariable(BaseModel):
    name: str
    label: str
    default: str
    help: str = ""


class PromptTemplate(BaseModel):
    id: str
    name: str
    scenario: str
    summary: str
    variables: list[PromptTemplateVariable]
    guardrails: list[str]
    expected_artifacts: list[str]


class PromptTemplateRenderRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)


class PromptTemplateRenderResponse(BaseModel):
    template_id: str
    scenario: str
    prompt: str
    variables: dict[str, str]
    warnings: list[str]


class MaaSTestRequest(BaseModel):
    prompt: str = Field(default="Summarize this Tax data product in one sentence.", min_length=10)


class MaaSTestResponse(BaseModel):
    ok: bool
    configured: bool
    model: str
    summary: str
    error: str
    status: dict[str, Any]


class AgentResult(BaseModel):
    name: str
    role: str
    status: str
    summary: str
    outputs: list[str]


class ArtifactPreview(BaseModel):
    name: str
    kind: str
    path: str
    content: str
    url: str | None = None
    review_status: str = "not_required"
    review_required: bool = False


class GateResult(BaseModel):
    id: str
    name: str
    status: str
    detail: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    execution_mode: str
    generated_dir: str
    generated_url: str
    maas: dict[str, Any]
    bigdata_execution: dict[str, Any]
    business_contract: dict[str, Any]
    contract_audit: dict[str, Any]
    local_execution: dict[str, Any]
    agents: list[AgentResult]
    artifacts: list[ArtifactPreview]
    quality_gates: list[GateResult]
    synthetic_rows: list[dict[str, Any]]
    gold_rows: list[dict[str, Any]]
    lineage: list[dict[str, str]]
    review: dict[str, Any]
    decision: dict[str, Any]


class HealthResponse(BaseModel):
    ok: bool
    service: str
    langgraph_available: bool
    maas_configured: bool
    maas_model: str
    code_server_found: bool
    bigdata_deployed: bool


class ArtifactReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    reviewer: str = "local_operator"
    note: str = ""


class ArtifactReviewResponse(BaseModel):
    run_id: str
    artifact_name: str
    status: str
    artifact_hash: str = ""
    reviewer: str
    note: str
    updated_at: str
    review: dict[str, Any]


class ReleasePackageResponse(BaseModel):
    run_id: str
    status: str
    ready: bool
    message: str
    release_hash: str = ""
    release: dict[str, Any] = Field(default_factory=dict)
    missing_approvals: list[str] = Field(default_factory=list)
    failed_gates: list[str] = Field(default_factory=list)


class CloudBindingRequest(BaseModel):
    mode: Literal["local_simulation", "operator_provided"] = "local_simulation"
    bindings: dict[str, str] = Field(default_factory=dict)
    reviewer: str = "local_operator"
    note: str = ""


class CloudBindingResponse(BaseModel):
    run_id: str
    status: str
    ready_for_import_review: bool
    cloud_execution: str
    message: str
    binding: dict[str, Any] = Field(default_factory=dict)
    missing_bindings: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)


class ImportReviewRequest(BaseModel):
    reviewer: str = "local_operator"
    note: str = ""


class ImportReviewResponse(BaseModel):
    run_id: str
    status: str
    ready_for_operator_handoff: bool
    cloud_execution: str
    message: str
    review: dict[str, Any] = Field(default_factory=dict)
    failed_checks: list[str] = Field(default_factory=list)


class DataArtsStandardizationResponse(BaseModel):
    run_id: str
    status: str
    ready_for_cloud_probe: bool
    cloud_execution: str
    message: str
    standardization: dict[str, Any] = Field(default_factory=dict)
    failed_checks: list[str] = Field(default_factory=list)


class CloudResourceProbeRequest(BaseModel):
    source: Literal["existing_binding", "environment", "operator_provided"] = "environment"
    bindings: dict[str, str] = Field(default_factory=dict)
    allow_network_probe: bool = False
    reviewer: str = "local_operator"
    note: str = ""


class CloudResourceProbeResponse(BaseModel):
    run_id: str
    status: str
    ready_for_operator_execution_request: bool
    real_cloud_verified: bool
    cloud_execution: str
    message: str
    probe: dict[str, Any] = Field(default_factory=dict)
    missing_bindings: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    use_maas: bool = False
    max_cases: int = Field(default=5, ge=1, le=10)


class EvaluationRunResponse(BaseModel):
    eval_id: str
    status: str
    passed: bool
    score: int
    max_score: int
    pass_rate: float
    case_count: int
    summary: str
    eval_dir: str
    eval_url: str
    files: list[dict[str, str]] = Field(default_factory=list)
    cases: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonRunRequest(BaseModel):
    max_cases: int = Field(default=5, ge=1, le=10)


class ComparisonRunResponse(BaseModel):
    comparison_id: str
    status: str
    passed: bool
    summary: str
    recommendation: str
    comparison_dir: str
    comparison_url: str
    local: dict[str, Any]
    maas: dict[str, Any]
    metrics: dict[str, Any]
    files: list[dict[str, str]] = Field(default_factory=list)
    cases: list[dict[str, Any]] = Field(default_factory=list)


class FailureReplayRequest(BaseModel):
    max_failures: int = Field(default=3, ge=1, le=10)


class FailureReplayResponse(BaseModel):
    replay_id: str
    status: str
    passed: bool
    summary: str
    replay_dir: str
    replay_url: str
    files: list[dict[str, str]] = Field(default_factory=list)
    cases: list[dict[str, Any]] = Field(default_factory=list)


class PreExecutionReadinessResponse(BaseModel):
    run_id: str
    status: str
    ready_for_execution_layer: bool
    cloud_execution: str
    summary: str
    report_dir: str
    report_url: str
    files: list[dict[str, str]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionRequestCreate(BaseModel):
    profile_id: str = Field(
        default="",
        max_length=64,
        pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$",
    )
    target: Literal["mrs", "dataarts", "dry_run"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    release_hash: str = Field(default="", max_length=64, pattern=r"^$|^[0-9a-f]{64}$")


class ExecutionApprovalRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class ExecutionCancelRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class ExecutionRequestResponse(BaseModel):
    request_id: str
    run_id: str
    release_hash: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    status: str
    requested_by: str
    approved_by: str | None = None
    cloud_job_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    requested_at: str
    approved_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str
