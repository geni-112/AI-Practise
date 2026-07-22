---
name: build-huawei-agentic-data-workbench
description: Design, build, deploy, and validate governed chat-first big-data development and ChatBI workbenches on Huawei Cloud using FastAPI, LangGraph, Huawei MaaS/GLM, semantic catalogs, deterministic validators, prompt templates, synthetic data, OBS, MRS Spark, DataArts, and optional DWS. Use when replacing or augmenting notebook-centric development with multi-agent vibe coding, implementing safe natural-language analytics, defining prompt-to-contract-to-code workflows, creating Databricks-inspired three-stage interfaces, planning Huawei Cloud resources, implementing review/security/lineage gates, or reproducing the Agentic Tax Bigdata Demo pattern.
---

# Build Huawei Agentic Data Workbench

## Target Outcome

Build a governed authoring surface where a business user describes an analytical or data-engineering need in chat, specialized agents turn it into reviewable contracts and artifacts, and Huawei Cloud services remain the controlled execution plane.

Treat the workbench as a Notebook replacement or augmentation at the development entry point. Do not replace OBS, MRS, DataArts, DWS, IAM, or operational controls with an LLM.

## Follow This Workflow

1. Inspect the existing codebase, cloud inventory, data classifications, network boundaries, and deployment constraints.
2. Define or validate the business contract before generating executable code.
3. Separate the experience, agent-control, governance, execution, and evidence planes.
4. Implement the three-stage user experience: chat composition, live progress, and detailed results. When more than one language is required, carry an explicit locale through the complete request, progress, result, and follow-up flow.
5. Generate PySpark, SQL, DAG, quality, security, and lineage artifacts as individually reviewable files.
6. Run deterministic local checks and reconcile metrics before requesting cloud execution.
7. Keep production execution blocked until required artifacts are approved and a release package is frozen.
8. Probe cloud bindings with read-only calls before scheduling or submitting jobs.
9. Execute only after explicit authorization, then publish Gold data and immutable run evidence.
10. Validate the complete experience on desktop and mobile, including every enabled control.

For direct analytical questions, route the prompt through a separate ChatBI path: semantic parsing, a validated query contract, a metric catalog, a parameterized read-only compiler, an approved serving dataset, and an evidence-bearing result response.

## Enforce These Principles

- Convert free-form intent into an explicit, versioned business contract.
- Use specialized agents for architecture, contracts, PySpark, SQL, orchestration, quality, security, and lineage.
- Treat an agent as a responsibility and state boundary, not automatically as an LLM call.
- Use AI for ambiguous language, semantic drafts, and explanations; use deterministic code for schemas, allowlists, syntax, reconciliation, policy, and release checks.
- Never let the same model be the sole author, reviewer, and approver of executable output.
- Keep generated code untrusted until deterministic validation and human approval pass.
- Send compact schemas, metadata, and policy context to MaaS; do not send raw direct identifiers.
- Preserve a deterministic local fallback when MaaS is unavailable, and record which path actually ran.
- Keep templates optional and hidden behind advanced controls so the initial screen remains a chat surface.
- Treat locale as an end-to-end contract. Localize product chrome in the client and business-semantic responses in the backend; never present a partially translated run as a supported language.
- Preserve the active task, selected result section, and validated ChatBI history when the user changes language.
- Return a clarification or recoverable error state when intent cannot be mapped safely; preserve the prompt and expose retry controls.
- Treat synthetic data as validation context, never as production truth.
- Persist every run under a unique identifier so prompts, contracts, code, approvals, and results can be diffed.
- Never place credentials, passwords, access keys, private keys, or live resource identifiers in the skill or generated repository.
- Never create paid cloud resources or enable a production release without explicit user approval.

## Load References Selectively

- Read [references/architecture.md](references/architecture.md) when defining system boundaries, agents, state transitions, or component topology.
- Read [references/resource-baseline.md](references/resource-baseline.md) when estimating or deploying local and Huawei Cloud resources.
- Read [references/agent-workflow.md](references/agent-workflow.md) when implementing LangGraph nodes, prompts, artifact contracts, reviews, or replay.
- Read [references/chatbi-semantic-query.md](references/chatbi-semantic-query.md) when implementing natural-language result queries, semantic catalogs, safe SQL compilation, follow-up context, or query evidence.
- Read [references/ui-design.md](references/ui-design.md) when implementing or reviewing the frontend experience.
- Read [references/bilingual-interface.md](references/bilingual-interface.md) when adding Chinese/English switching, localizing dynamic progress or results, or testing semantic parity across languages.
- Read [references/security-operations.md](references/security-operations.md) when handling credentials, MaaS connectivity, cloud probes, deployment, or operations.
- Read [references/acceptance-checklist.md](references/acceptance-checklist.md) before declaring a build, deployment, or handoff complete.

## Reuse The Assets

- Copy [assets/business-contract.schema.json](assets/business-contract.schema.json) as the starting validation contract for agent output.
- Adapt [assets/tax-business-prompt-template.md](assets/tax-business-prompt-template.md) for optional guided prompting and test cases.
- Import or translate [assets/workbench-design-tokens.css](assets/workbench-design-tokens.css) into the target frontend design system.
- Use [assets/agentic-tax-bigdata-business-flow.drawio](assets/agentic-tax-bigdata-business-flow.drawio) as the editable reference for the complete business flow.

## Keep The Release Boundary Explicit

Use four distinct states:

1. `draft`: intent, contract, and artifacts can change.
2. `reviewed`: required artifacts have named approvals.
3. `released`: approved files are checksummed and immutable for the run.
4. `executed`: a released package has cloud job evidence and result evidence.

Do not infer a later state from UI appearance alone. Persist state and evidence in backend artifacts.

## Require Verifiable Evidence

Before completion, require:

- a validated business contract;
- explicit MaaS or local-fallback execution metadata;
- syntax and policy results for each generated artifact;
- reviewer decisions for PySpark, SQL, and DAG artifacts;
- a release manifest containing hashes;
- read-only cloud-binding evidence before execution;
- job identifiers, timestamps, row counts, quality results, and lineage after execution;
- frontend interaction and responsive-layout checks.

Do not claim MaaS generated content unless runtime evidence records `maas.used=true`. Do not claim a cloud pipeline succeeded unless the execution plane returned a successful terminal state and the expected output is non-empty.
