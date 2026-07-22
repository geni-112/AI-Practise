# Agent Workflow

## Workflow Contract

Represent each run as durable state, not a single model response. Every stage must declare its input, output, validator, retry policy, and evidence.

| Step | Stage | Input | Output |
|---|---|---|---|
| 0 | Context preflight | Schemas, masked samples, policies, service inventory | `data_context.json` |
| 1 | Intent intake | User message, optional template values | `intent.json` |
| 2 | Business contract | Intent and data context | `business_contract.yaml` |
| 3 | Contract audit | Contract and policy rules | `contract_audit.json` |
| 4 | Architecture decision | Audited contract and available services | `architecture_decision.json` |
| 5 | Artifact generation | Contract, architecture, source metadata | PySpark, SQL, and DAG drafts |
| 6 | Local validation | Draft artifacts and synthetic data | Syntax/test/reconciliation reports |
| 7 | Governance | Validated drafts and policies | Quality, security, and lineage artifacts |
| 8 | Artifact review | All generated files and test evidence | `review_status.json` |
| 9 | Release packaging | Approved files | Checksummed release package |
| 10 | Cloud binding | Release requirements and inventory | `cloud_binding.json` |
| 11 | Read-only probe | Cloud binding and restricted credentials | `cloud_probe.json` |
| 12 | Execution approval | Release, probe, cost, reviewer identity | `execution_approval.json` |
| 13 | Cloud execution | Approved immutable package | MRS/DataArts job evidence |
| 14 | Result publication | Execution output and quality results | Gold data and `run_manifest.json` |

Perform context preflight before interpreting the prompt. The user should not need to know bucket prefixes, table schemas, privacy labels, or available compute when the platform can discover them safely.

## Hybrid Agent Rule

Classify every workflow node as one of:

- `model_assisted`: language interpretation, contract draft, code draft, explanation;
- `deterministic`: schema validation, allowlists, safe SQL compilation, syntax, reconciliation, policy, hashing;
- `human_decision`: artifact approval, release approval, paid-resource authorization;
- `external_evidence`: Huawei Cloud API state, job status, row counts, logs, and object metadata.

Record the class in run evidence. Never describe a deterministic node as MaaS-generated, and never accept a model's statement that its own output is safe as proof.

## Business Contract

Make the contract the semantic center of the system. Validate it against `assets/business-contract.schema.json` and require, at minimum:

- business goal and owner;
- source datasets and allowed fields;
- grain, dimensions, metrics, filters, and time scope;
- privacy and masking behavior;
- quality thresholds;
- required output artifacts;
- approval policy and production block;
- measurable acceptance criteria;
- assumptions and unresolved questions.

If a required semantic decision is missing, return a clarification request instead of inventing a business rule. Allow safe defaults only when they are listed explicitly in `assumptions`.

## Model Invocation Rules

Use MaaS only when all of these are true:

1. the run requests model assistance;
2. endpoint, credential, and model configuration pass a health check;
3. the data context is allowed for model processing;
4. the request has a bounded timeout and retry policy.

Require structured model output. Pass it through a deterministic adapter that validates schema, canonicalizes paths and identifiers, removes disallowed content, and inserts required governance defaults.

On timeout, rate limit, invalid structure, or policy rejection:

- record the model error without exposing secrets;
- switch to the deterministic local path when policy permits;
- mark `execution_mode=local_fallback`;
- never label fallback output as model-generated.

Record metadata similar to:

```json
{
  "execution_mode": "maas",
  "maas": {
    "requested": true,
    "configured": true,
    "used": true,
    "model": "configured-at-runtime",
    "attempts": 1,
    "error_code": null
  }
}
```

Do not store prompts or responses containing direct identifiers. Store a redacted request digest and the validated contract when prompt retention is restricted.

## Parallel Artifact Generation

After the contract and architecture pass audit, fan out three primary branches:

### PySpark Branch

Generate MRS-compatible transformations with explicit source/output paths, schema handling, partition strategy, null behavior, masking, aggregations, and counters. Avoid local-only engines in artifacts intended for real MRS execution.

### SQL Branch

Generate DWS-compatible serving SQL or reconciliation SQL. Include idempotent object handling, documented dialect assumptions, data types, grants as separate optional statements, and queries that reconcile critical metrics with the Spark output.

### Orchestration Branch

Generate a DataArts importable representation with nodes, dependencies, parameters, retries, timeouts, resource bindings, and failure behavior. Keep resource IDs symbolic until cloud binding.

Join the branches only after each returns valid syntax and declared output metadata.

## Local Validation

Use synthetic or sanitized rows to validate semantics before cloud execution. At minimum:

- parse and lint generated files;
- validate the business contract and DAG schemas;
- exercise key transformation rules;
- compare Spark-style and SQL-style metric results;
- confirm masked outputs contain no direct identifiers;
- verify expected columns, grain, and row-count constraints;
- scan generated artifacts for credentials and unresolved placeholders.

Persist `local_run_output.json` and `metric_reconciliation.json`. Local success is evidence of consistency, not proof of distributed runtime compatibility.

## Governance Outputs

Generate these files independently so they can be reviewed and replaced:

```text
business_contract.yaml
contract_audit.json
architecture_decision.json
mrs_transform.py
dws_serving.sql
dataarts_dag.yaml
local_run_output.json
metric_reconciliation.json
quality_gates.json
security_review.md
lineage_manifest.json
review_status.json
release_manifest.json
cloud_binding.json
cloud_probe.json
execution_report.json
run_manifest.json
```

Do not keep final artifacts only in LangGraph memory. Write them to `generated/<run-id>/` or a versioned object prefix so every run is inspectable and diffable.

## Review And Release Gates

Require independent decisions for PySpark, SQL, and DAG artifacts. Record reviewer identity, timestamp, file hash, decision, and comment. A change to an approved file invalidates its approval.

Block release when:

- the contract audit fails;
- required fields or acceptance criteria are unresolved;
- a required artifact lacks approval;
- metric reconciliation exceeds tolerance;
- the security review finds a blocking issue;
- quality gates are not executable;
- the cloud binding contains unresolved symbols;
- release files contain secrets.

Freeze approved files into a checksummed release directory. Execute exactly that package, not mutable drafts.

## Replay And Evaluation

Make runs replayable with the same intent, contract version, template version, model configuration, and source snapshot metadata. Do not assume generative output will be byte-identical.

Maintain evaluation cases that test:

- correct contract semantics;
- stable required artifact generation;
- forbidden identifier handling;
- model timeout and fallback behavior;
- invalid code rejection;
- approval invalidation after edits;
- release hash enforcement;
- cloud execution disabled before approval;
- Gold result acceptance.

Use prompt templates as optional accelerators and evaluation fixtures. Keep free-form chat as the primary user experience.

Evaluate ChatBI separately with paraphrases, follow-up questions, unknown catalog values, prompt injection attempts, model timeout, local fallback, parameter isolation, and read-only enforcement. See `chatbi-semantic-query.md`.
