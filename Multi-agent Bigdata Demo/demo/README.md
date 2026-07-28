# SAT Minimal Agentic Frontend

This is the first-phase frontend-only POC for replacing notebook development with an agent workbench.

It uses:

- code-server as the optional browser IDE shell.
- FastAPI for the local API and static frontend.
- LangGraph for multi-agent orchestration.
- Huawei MaaS as an optional OpenAI-compatible model endpoint.
- Local synthetic SAT-style rows for development and an explicitly enabled, allowlisted Huawei Cloud execution worker for production.
- A local prompt template library for business users.

The metadata center is integrated into the same workbench at `/metadata`. It exposes a
Catalog -> Schema -> Table tree, table and column metadata, governed metrics and dimensions,
privacy classifications, lineage, and verified Apache Iceberg snapshot evidence through
`GET /api/metadata/catalog`. It does not require deploying Unity Catalog. The current catalog
combines the application's governed semantic model with MRS execution evidence and can later
be backed by DataArts Catalog or another external catalog without changing the page contract.

The production control center is part of the Cloud environment result tab. Local POC mode
remains generation-only. Production cloud writes require all of the following:

- production mode and cloud execution explicitly enabled;
- authenticated JWT or trusted reverse-proxy identity with the required role;
- current artifact approvals stored against exact SHA-256 hashes;
- an immutable release manifest recorded in the control database;
- a successful real-cloud read-only resource probe;
- a server-managed execution profile whose target and resource identifiers are allowlisted;
- a second cloud operator approving the request before the independent worker can claim it.

See [`docs/production-deployment.md`](docs/production-deployment.md) for the deployment and
security contract.

The same chat entry also supports governed ChatBI questions. Result-oriented prompts are routed to
`POST /api/chatbi/query` and return a concise answer, KPIs, a chart payload, a detail table, and the
query/source evidence. Development prompts still enter the LangGraph artifact workflow. The demo
ChatBI semantic layer reads the latest published Huawei Cloud MRS Gold snapshot and never exposes
or scans raw RFC values.

Known query patterns use the deterministic parser. Unfamiliar wording is sent to Huawei MaaS as
schema-only context and must return a validated Query Contract. The contract is checked against
`app/chatbi_catalog.json`, then compiled into read-only parameterized SQL with allowlisted identifiers.
MaaS never receives Gold rows and never executes SQL directly. Recent follow-up context contains only
previously validated semantic contracts. If MaaS is unavailable or returns an invalid contract, the
API returns a safe clarification or deterministic fallback instead of executing untrusted output.

No DataArts, MRS, OBS, or DWS writes occur in the default configuration. The protected
execution worker can submit an allowlisted MRS or DataArts job only after production mode,
authentication, persisted approvals, release hashing, real-cloud verification, and four-eyes
approval are all enabled.

Each run now writes a local review package under:

```text
generated/<run_id>/
```

The package contains:

- `artifacts/business_contract.yaml`
- `artifacts/contract_audit.json`
- `artifacts/mrs_transform.py`
- `artifacts/dws_serving.sql`
- `artifacts/dataarts_dag.yaml`
- `artifacts/execution_report.json`
- `artifacts/local_run_output.json`
- `artifacts/metric_reconciliation.json`
- `artifacts/security_review.md`
- `quality_gates.json`
- `lineage_manifest.json`
- `synthetic_rows.json`
- `gold_preview.json`
- `contract_audit.json`
- `local_execution.json`
- `review_status.json`
- `maas_trace.json`
- `run_manifest.json`

The frontend can approve or reject reviewable artifacts. In this phase, reviewable means PySpark, SQL, and DataArts DAG previews. Approval updates `review_status.json`; it does not submit jobs to Huawei Cloud.

After all reviewable artifacts are approved and no quality gate has failed, the frontend can generate a local release candidate under:

```text
generated/<run_id>/release/
```

The release candidate contains:

- `approval_summary.json`
- `dataarts_import_package.json`
- `environment_profile.yaml`
- `cloud_parameter_map.json`
- `deployment_preflight.json`
- `deployment_plan.yaml`
- `rollback_plan.md`
- `release_manifest.json`

This is a local preview package only. It keeps DataArts, MRS, OBS, and DWS execution blocked until a future cloud deployment approval.

The release package also includes a deployment preflight agent result. It checks the local release candidate against a Huawei Cloud environment contract: `la-south-2`, OBS raw/silver/gold/release/audit paths, MRS Spark, DWS, DataArts Factory, DEW/KMS, IAM least privilege, production approval windows, and cloud parameter placeholders. The preflight can pass local governance checks while still reporting `needs_cloud_binding`, because the POC does not bind real cloud resources.

After the release candidate exists, the frontend can run a local cloud-binding simulation. This writes additional review files under the same `release/` directory:

- `cloud_binding_simulation.json`
- `resolved_dataarts_import_package.json`
- `cloud_import_readiness.json`

This step validates that required Huawei Cloud parameters can be mapped before a real import review. It uses local placeholder values by default, does not call Huawei Cloud APIs, does not store credentials, and keeps DataArts, MRS, OBS, and DWS execution blocked.

After cloud binding succeeds, the frontend can run a local import-review agent. It writes:

- `cloud_import_review.json`
- `operator_handoff.md`
- `final_import_manifest.json`

This is the handoff checkpoint before a future cloud operator prepares DataArts import. It checks that approvals are still current, preflight has no failed checks, cloud binding evidence is present, the resolved import package has no placeholders, no credential-like bindings are included, and all DataArts/MRS execution remains blocked.

Before a real execution layer is considered, the frontend can run two more checkpoints. DataArts standardization writes `dataarts_import_standard_schema.json`, `dataarts_import_standard_package.json`, and `dataarts_import_validation.json`. The existing cloud resource read-only validation gate writes `resolved_dataarts_standard_package.json`, `real_cloud_resource_binding_template.json`, `cloud_resource_probe.json`, `cloud_execution_readiness.json`, `cloud_readonly_verification_checklist.md`, and `cloud_execution_approval_request.md`. These steps validate the import schema and resource binding contract, but they do not create resources, enable schedules, submit jobs, or authorize cloud execution.

The read-only validation gate can optionally call Huawei Cloud read-only SDK APIs for OBS, MRS, DWS, DataArts, KMS, and VPC/subnet. Real cloud verification requires the optional SDK packages, `allow_network_probe=true`, and `HUAWEICLOUD_ENABLE_READONLY_PROBE=true`. Without those, the report is still generated but `real_cloud_verified` remains `false`.

Prompt templates are exposed through:

```http
GET /api/prompt-templates
POST /api/prompt-templates/{template_id}/render
```

Available starter templates:

- `sat_taxpayer_annual_base`
- `sat_resico_control`
- `sat_regime_reconciliation`

Template ID and template variables are written to `request.json` and `run_manifest.json` for traceability.

MaaS can generate the structured business contract, but the local graph then runs a contract consistency audit before code/DAG generation. The audit checks required contract sections, expected dimensions and metrics, masking identifiers, declared artifacts, source URI alignment, and the production approval lock. Audit evidence is saved as `contract_audit.json` and surfaced again in `quality_gates.json`.

PySpark, SQL, and DataArts DAG previews are generated from `business_contract.yaml` after the audit step. The local adapter currently supports the SAT annual-base grain `ejercicio_analisis, region, cve_regimen, is_resico` and the metrics `active_taxpayers, total_declared_amount`. If MaaS or a prompt introduces unsupported dimensions or metrics, the contract audit marks the run as needing a fix instead of silently producing mismatched code.

After script generation, the graph runs a local dry-run agent. It does not submit Spark, DWS, or DataArts jobs. Instead, it uses a local Python-equivalent execution over the synthetic rows, checks that generated PySpark/SQL/DAG previews carry the same contract dimensions and metrics, and writes `execution_report.json`, `local_run_output.json`, and `metric_reconciliation.json`. The reconciliation result is included in `quality_gates.json`.

The POC also includes a local evaluation harness. It runs a small SAT prompt set through the full chain: agent generation, artifact review, release package, cloud binding simulation, and import review. Each evaluation writes:

```text
evaluations/<eval_id>/
```

The package contains:

- `summary.json`
- `scorecard.md`
- `case_results.json`

The current evaluation checks required artifacts, contract audit, quality gates, direct RFC exposure, local dry-run reconciliation, release generation, cloud binding, import review handoff, execution lock, resolved placeholders, and handoff files.

The POC also includes a Local vs MaaS comparison harness. It runs the same SAT prompt set through the local fallback branch and, when MaaS is configured, through the GLM-5.2-assisted branch. Each comparison writes:

```text
evaluations/<compare_id>/
```

The package contains:

- `summary.json`
- `comparison_report.md`
- `artifact_diff.json`
- `local/summary.json`
- `maas/summary.json` or `maas/skipped.json`

The comparison explicitly reports whether MaaS was configured and whether each case actually used MaaS. If the MaaS branch falls back locally, the comparison is not marked as a MaaS success.

When a comparison fails, the failed case is materialized into the failure sample library:

```text
evaluations/failures/<case_id>/<failure_id>/
```

Each failure sample contains:

- `failure.json`
- `diagnosis.md`
- `local_business_contract.yaml`
- `maas_business_contract.yaml`

The current MaaS prompt strategy library includes `strict_contract`, `security_first`, `reconciliation`, and `dataarts_ready`. The graph chooses a strategy from the scenario, template, and prompt text, then records the selected strategy in `maas_trace.json` and `run_manifest.json`.

## Run API

The frontend prefers the streaming run API so the process view can update step by step as each agent node completes:

```http
POST /api/runs/stream
```

The stream emits `run_started`, `step_started`, `step_completed`, and `run_completed` events. The non-streaming endpoint remains available as a fallback:

```http
POST /api/runs
```

## Evaluation API

```http
GET /api/evaluations
POST /api/evaluations
GET /api/evaluations/comparisons
POST /api/evaluations/compare
GET /api/evaluations/failures
POST /api/evaluations/failures/replay
GET /api/maas/strategies
GET /api/runs/{run_id}/pre-execution
POST /api/runs/{run_id}/pre-execution
GET /api/runs/{run_id}/dataarts-standardization
POST /api/runs/{run_id}/dataarts-standardization
GET /api/runs/{run_id}/cloud-resource-probe
POST /api/runs/{run_id}/cloud-resource-probe
```

`POST` runs the local evaluation set. It uses local fallback generation by default, auto-approves reviewable artifacts for evaluation only, and still keeps cloud execution blocked.

Example request:

```json
{
  "use_maas": false,
  "max_cases": 5
}
```

The response includes the evaluation score, case-level results, and links to `scorecard.md`, `summary.json`, and `case_results.json`.

`POST /api/evaluations/compare` runs the Local vs MaaS A/B comparison:

```json
{
  "max_cases": 5
}
```

If MaaS is not configured, the local baseline still runs and the MaaS branch is recorded as skipped. If MaaS is configured but not actually used by the agent graph, the comparison reports `maas_unavailable` instead of treating local fallback as MaaS output.

`POST /api/evaluations/failures/replay` reruns captured failure samples through the current MaaS strategy and current audit rules. It is local validation only; DataArts, MRS, OBS, and DWS execution remain blocked.

`POST /api/runs/{run_id}/pre-execution` now creates the eight-step real-resource-creation preparation package under `generated/{run_id}/pre_execution/`: environment mode decision, target environment definition, data compliance classification, cloud provisioning blueprint, cost/quota review, IAM/key strategy, IaC state management, and IaC dry-run plus approval request. When all eight gates pass, the local preparation phase is complete and the next step is creating real Huawei Cloud resources under explicit operator approval.

## Run the frontend

```powershell
Set-Location C:\Users\Matebook\Documents\大数据\sat-agent-vibe-poc\frontend-min
.\run_frontend.ps1
```

Open http://127.0.0.1:8788.

For access from other addresses, bind Uvicorn to `0.0.0.0` only behind an HTTPS reverse proxy
and an authenticated network boundary. Do not expose the development server directly to the
Internet. Production deployment must use the identity and database settings described in
`docs/production-deployment.md`.

```powershell
.\run_frontend.ps1 -HostAddress 0.0.0.0 -Port 8788 -NoReload
```

## Metadata API

```http
GET /api/metadata/catalog
GET /metadata
```

The table asset reports `Apache Iceberg` only when the published execution evidence includes
a verified snapshot. Until then the UI shows `migration pending verification`; it does not
claim that CSV compatibility output has already been converted.

## Production control API

```http
GET  /api/auth/me
GET  /api/runs/{run_id}/production-control
GET  /api/execution-profiles
POST /api/runs/{run_id}/execution-requests
POST /api/execution-requests/{request_id}/approve
POST /api/execution-requests/{request_id}/cancel
```

Run the queue worker as a separate process after production configuration is validated:

```powershell
.\.venv\Scripts\python.exe -m app.execution_worker
```

The worker refuses to start unless both `SAT_PRODUCTION_MODE=true` and
`SAT_CLOUD_EXECUTION_ENABLED=true`.

## Review API

```http
POST /api/runs/{run_id}/artifacts/{artifact_name}/review
```

Example request:

```json
{
  "status": "approved",
  "reviewer": "local_operator",
  "note": "Approved in frontend review."
}
```

## Release Package API

```http
GET /api/runs/{run_id}/release-package
POST /api/runs/{run_id}/release-package
```

`GET` reports whether PySpark, SQL, and DataArts DAG have all been approved. `POST` writes the local `release/` package only when the run is ready. It does not submit jobs to Huawei Cloud.

The generated `deployment_preflight.json` should be treated as the next approval checkpoint before any cloud import. A warning for unbound `MRS_CLUSTER_ID`, `DWS_CONNECTION_NAME`, `DATAARTS_WORKSPACE_ID`, OBS paths, VPC, subnet, or KMS key is expected in this local-only phase.

## Cloud Binding API

```http
GET /api/runs/{run_id}/cloud-binding
POST /api/runs/{run_id}/cloud-binding
```

`GET` reports whether the release candidate still needs cloud parameter binding. `POST` creates a local binding simulation by default and validates region, OBS layer paths, MRS/DWS/DataArts identifiers, KMS placeholder handling, and the cloud execution lock.

Example request for operator-provided non-secret values:

```json
{
  "mode": "operator_provided",
  "reviewer": "local_operator",
  "note": "Values copied from an approved cloud design review.",
  "bindings": {
    "HUAWEICLOUD_REGION": "la-south-2",
    "HUAWEICLOUD_PROJECT_ID": "project-placeholder",
    "VPC_ID": "vpc-placeholder",
    "PRIVATE_SUBNET_ID": "subnet-placeholder",
    "KMS_KEY_ID": "kms-placeholder",
    "OBS_RAW_URI": "obs://sat-approved/raw/sat/",
    "OBS_SILVER_URI": "obs://sat-approved/silver/sat/",
    "OBS_GOLD_URI": "obs://sat-approved/gold/sat/",
    "OBS_RELEASE_URI": "obs://sat-approved/release/front-example/",
    "OBS_AUDIT_URI": "obs://sat-approved/audit/front-example/",
    "MRS_CLUSTER_ID": "mrs-placeholder",
    "DWS_CONNECTION_NAME": "dws-sat-placeholder",
    "DATAARTS_WORKSPACE_ID": "dataarts-placeholder"
  }
}
```

Never include AK/SK, passwords, private keys, or database credentials in this request. Even after a successful binding simulation, cloud import and production execution remain blocked until a separate cloud deployment approval.

## Import Review API

```http
GET /api/runs/{run_id}/import-review
POST /api/runs/{run_id}/import-review
```

`GET` reports whether cloud binding is ready for import review. `POST` generates the local operator handoff files after a successful binding simulation. It does not import DataArts jobs or submit MRS/DWS/OBS work.

The review checks:

- executable artifact approvals are still current
- deployment preflight has no failed checks
- cloud binding is ready and attached to the release manifest
- resolved DataArts package has no placeholders
- DataArts schedules and MRS submits remain blocked
- handoff files do not include credential-like bindings

The output status `operator_handoff_ready` means the local package is ready for human cloud-console review only. It does not authorize cloud execution.

## DataArts Standardization API

```http
GET /api/runs/{run_id}/dataarts-standardization
POST /api/runs/{run_id}/dataarts-standardization
```

`POST` converts the local DataArts preview package into a stable `dataarts.factory.import.v1alpha1` package. It validates required fields, parameters, node types, dependency references, disabled schedules, execution locks, and secret boundaries.

## Existing Cloud Resource Read-only Validation API

```http
GET /api/runs/{run_id}/cloud-resource-probe
POST /api/runs/{run_id}/cloud-resource-probe
```

Example:

```json
{
  "source": "existing_binding",
  "allow_network_probe": true,
  "reviewer": "local_operator",
  "note": "Validate existing Huawei Cloud resources with read-only checks. No write call is allowed."
}
```

Valid `source` values are `existing_binding`, `environment`, and `operator_provided`. Environment mode reads only non-secret identifiers and OBS URIs such as `HUAWEICLOUD_REGION`, `HUAWEICLOUD_PROJECT_ID`, `HUAWEICLOUD_VPC_ID`, `HUAWEICLOUD_PRIVATE_SUBNET_ID`, `HUAWEICLOUD_KMS_KEY_ID`, `HUAWEICLOUD_MRS_CLUSTER_ID`, `HUAWEICLOUD_DATAARTS_WORKSPACE_ID`, `HUAWEICLOUD_DWS_CONNECTION_NAME`, and `HUAWEICLOUD_OBS_BUCKET`.

The generated `real_cloud_resource_binding_template.json` is the handoff template for real environments. It contains only non-secret resource identifiers and OBS URIs. It must not contain AK/SK values, passwords, private keys, or database credentials.

The generated `cloud_readonly_verification_checklist.md` explains the operator steps, expected pass criteria, and stop conditions. Passing the checklist still does not create resources, import DataArts jobs, submit MRS jobs, run SQL, upload OBS files, enable schedules, or approve production execution.

To enable real read-only cloud checks, install the optional dependencies and set read-only credential values in the operator shell environment only:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-huaweicloud-readonly.txt
$env:HUAWEICLOUD_ENABLE_READONLY_PROBE = "true"
$env:HUAWEICLOUD_ACCESS_KEY = "<read-only-ak>"
$env:HUAWEICLOUD_SECRET_KEY = "<read-only-sk>"
$env:HUAWEICLOUD_REGION = "la-south-2"
$env:HUAWEICLOUD_PROJECT_ID = "<project-id>"
```

The adapter only uses read-only SDK calls such as VPC/subnet list, OBS list objects, MRS show cluster details, DWS list cluster details, KMS list keys, and DataArts list workspaces. It writes `real_cloud_verified=true` only when the read-only SDK checks pass. It still writes `cloud_execution=blocked`.

Never include AK/SK, passwords, private keys, or database credentials in the request body or generated files.

## Optional MaaS configuration

The app works without MaaS. To call Huawei MaaS GLM-5.2, `HUAWEI_MAAS_API_KEY` is required. `HUAWEI_MAAS_BASE_URL` and `HUAWEI_MAAS_MODEL` have defaults, but can be overridden.

```powershell
$env:HUAWEI_MAAS_BASE_URL = "https://api-ap-southeast-1.modelarts-maas.com/openai/v1"
$env:HUAWEI_MAAS_API_KEY = "<secure-api-key>"
$env:HUAWEI_MAAS_MODEL = "glm-5.2"
```

You can also put these values in local `.env.local` or `.env`; both are ignored by git. Do not store keys in committed files.

MaaS status and test endpoints:

```http
GET /api/maas/status
POST /api/maas/test
```

The frontend test button sends a short connectivity prompt to MaaS. It does not submit DataArts, MRS, OBS, or DWS jobs.

## Optional code-server

```powershell
.\run_code_server.ps1
```

If code-server is not installed, the frontend still runs. The local VS Code CLI can be used while code-server is added later.
