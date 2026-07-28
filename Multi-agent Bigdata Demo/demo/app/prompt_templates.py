from __future__ import annotations

from collections import defaultdict

from .models import PromptTemplate, PromptTemplateRenderResponse


TEMPLATES = [
    {
        "id": "tax_taxpayer_annual_base",
        "name": "Tax taxpayer annual base",
        "scenario": "tax_taxpayer_annual_base",
        "summary": "Build a governed annual taxpayer base with masked identifiers and gold aggregates.",
        "variables": [
            {
                "name": "tax_year",
                "label": "Analysis year",
                "default": "2025",
                "help": "Fiscal year used for the annual taxpayer base.",
            },
            {
                "name": "source_path",
                "label": "Landing source",
                "default": "local://landing/taxpayer_registry.csv",
                "help": "Local or future OBS landing location.",
            },
            {
                "name": "region_scope",
                "label": "Region scope",
                "default": "CDMX, Jalisco, Nuevo Leon, Puebla, Yucatan",
                "help": "Regions included in the local validation set.",
            },
            {
                "name": "approval_policy",
                "label": "Approval policy",
                "default": "Keep production execution blocked until PySpark, SQL, and DAG are reviewed.",
                "help": "Human gate before any cloud execution.",
            },
        ],
        "guardrails": [
            "Do not expose direct RFC in UI or generated serving artifacts.",
            "Do not embed MaaS keys or Huawei Cloud credentials in generated files.",
            "Do not submit DataArts, MRS, OBS, or DWS jobs in the frontend-only phase.",
        ],
        "expected_artifacts": [
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
        "prompt_template": (
            "Build a governed Tax taxpayer annual base for tax year {tax_year}. "
            "Use source data from {source_path} and restrict local validation to {region_scope}. "
            "Mask direct RFC, keep rfc_hash and masked_rfc only, aggregate by year, region, "
            "regime, and RESICO flag, then produce PySpark, SQL, DataArts DAG, local dry-run evidence, "
            "quality rules, security review, and lineage evidence. {approval_policy}"
        ),
    },
    {
        "id": "tax_resico_control",
        "name": "RESICO taxpayer control",
        "scenario": "tax_resico_control",
        "summary": "Prepare a control view for RESICO taxpayers and regime compliance checks.",
        "variables": [
            {
                "name": "tax_year",
                "label": "Analysis year",
                "default": "2025",
                "help": "Fiscal year to validate.",
            },
            {
                "name": "source_path",
                "label": "Landing source",
                "default": "local://landing/taxpayer_registry.csv",
                "help": "Local or future OBS landing location.",
            },
            {
                "name": "risk_focus",
                "label": "Risk focus",
                "default": "active RESICO taxpayers with regime mismatches or missing declarations",
                "help": "Business risk that should shape quality and serving outputs.",
            },
            {
                "name": "approval_policy",
                "label": "Approval policy",
                "default": "Keep production execution blocked until quality and security review pass.",
                "help": "Human gate before any cloud execution.",
            },
        ],
        "guardrails": [
            "Do not expose direct RFC in generated controls.",
            "Separate local quality findings from production enforcement actions.",
            "Do not create cloud jobs without explicit approval.",
        ],
        "expected_artifacts": [
            "business_contract.yaml",
            "contract_audit.json",
            "mrs_transform.py",
            "dws_serving.sql",
            "dataarts_dag.yaml",
            "execution_report.json",
            "local_run_output.json",
            "metric_reconciliation.json",
            "quality_gates.json",
            "security_review.md",
            "lineage_manifest.json",
        ],
        "prompt_template": (
            "Build a Tax RESICO taxpayer control for tax year {tax_year}. "
            "Use source data from {source_path}. Focus on {risk_focus}. "
            "Generate masked taxpayer-level local previews and a governed aggregate serving layer. "
            "Produce PySpark, SQL, DataArts DAG, local dry-run evidence, quality rules, security review, and lineage. "
            "{approval_policy}"
        ),
    },
    {
        "id": "tax_regime_reconciliation",
        "name": "Regime reconciliation",
        "scenario": "tax_regime_reconciliation",
        "summary": "Compare taxpayer regime records across local landing snapshots and produce reconciliation evidence.",
        "variables": [
            {
                "name": "current_snapshot",
                "label": "Current snapshot",
                "default": "local://landing/taxpayer_registry_current.csv",
                "help": "Current local source snapshot.",
            },
            {
                "name": "previous_snapshot",
                "label": "Previous snapshot",
                "default": "local://landing/taxpayer_registry_previous.csv",
                "help": "Previous local source snapshot.",
            },
            {
                "name": "reconcile_keys",
                "label": "Reconcile keys",
                "default": "rfc_hash, ejercicio_analisis, cve_regimen",
                "help": "Keys used for local comparison.",
            },
            {
                "name": "approval_policy",
                "label": "Approval policy",
                "default": "Keep production execution blocked until reconciliation outputs are reviewed.",
                "help": "Human gate before any cloud execution.",
            },
        ],
        "guardrails": [
            "Use hashed identifiers only in reconciliation outputs.",
            "Write differences as review evidence, not production corrections.",
            "Do not trigger DataArts or MRS jobs in this phase.",
        ],
        "expected_artifacts": [
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
        "prompt_template": (
            "Build a Tax taxpayer regime reconciliation between {current_snapshot} and {previous_snapshot}. "
            "Compare records using {reconcile_keys}. Produce masked local difference previews, "
            "gold reconciliation aggregates, PySpark, SQL, DataArts DAG, local dry-run evidence, quality rules, security review, "
            "and lineage evidence. {approval_policy}"
        ),
    },
]


def list_templates() -> list[PromptTemplate]:
    return [PromptTemplate(**template) for template in TEMPLATES]


def get_template(template_id: str) -> dict:
    for template in TEMPLATES:
        if template["id"] == template_id:
            return template
    raise KeyError(template_id)


def render_template(template_id: str, variables: dict[str, str]) -> PromptTemplateRenderResponse:
    template = get_template(template_id)
    defaults = {item["name"]: item["default"] for item in template["variables"]}
    merged = {**defaults, **{key: value.strip() for key, value in variables.items() if value.strip()}}
    prompt = template["prompt_template"].format_map(defaultdict(str, merged))
    warnings = validate_variables(template, merged)
    return PromptTemplateRenderResponse(
        template_id=template_id,
        scenario=template["scenario"],
        prompt=prompt,
        variables=merged,
        warnings=warnings,
    )


def validate_variables(template: dict, variables: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    for item in template["variables"]:
        value = variables.get(item["name"], "")
        if not value.strip():
            warnings.append(f"{item['label']} is empty.")
    approval_policy = variables.get("approval_policy", "").lower()
    if "approval" not in approval_policy and "review" not in approval_policy:
        warnings.append("Approval policy should mention approval or review.")
    return warnings
