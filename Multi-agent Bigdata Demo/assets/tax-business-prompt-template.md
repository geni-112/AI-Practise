# Tax Business Prompt Template

Use this template only when guided intake helps the user. Keep free-form chat available.

## Blank Template

```text
Business objective:
Create or update [data product/report/process] so that [business user] can [decision or action].

Business owner and domain:
[owner/team] / [domain]

Time scope:
[date range, tax year, reporting period, or event window]

Source data:
[logical dataset names and approved local/OBS/table locations]

Scope and filters:
[regions, entities, statuses, exclusions]

Output grain:
One row per [business key and time level].

Dimensions:
[dimension names and business definitions]

Metrics:
[metric name = exact business formula, aggregation, unit, tolerance]

Privacy and masking:
[direct identifiers, allowed transformations, model-context restrictions]

Quality expectations:
[required columns, uniqueness, null limits, reconciliation, row-count rules]

Requested artifacts:
[business contract, PySpark, SQL, DataArts DAG, quality, security, lineage]

Target services:
[local validation, OBS, MRS, DataArts, optional DWS]

Approval policy:
Keep production execution blocked until [artifacts] are approved by [roles].

Acceptance criteria:
[measurable result checks and expected evidence]
```

## Synthetic Tax Example

```text
Build a governed Tax taxpayer annual analytical base for tax year 2025.

Use the synthetic source at local://landing/taxpayer_registry.csv for local validation. Restrict the demonstration to CDMX, Jalisco, Nuevo Leon, Puebla, and Yucatan.

Produce one row per taxpayer regime and year. Include year, region, regime, and RESICO flag as dimensions. Include taxpayer count and active taxpayer count with exact formulas recorded in the business contract.

Treat RFC as a direct identifier. Do not send direct RFC values to MaaS and do not include them in browser previews or analytical outputs. Retain only approved hashed and partially masked derivatives.

Generate a business contract, MRS-compatible PySpark, DWS-compatible SQL, a DataArts DAG package, quality rules, a security review, and lineage evidence. Reconcile critical metrics between the transformation and serving definitions.

Use synthetic data for validation only. Keep cloud and production execution blocked until the contract, PySpark, SQL, and DAG have been reviewed and an immutable release package has been approved.
```

## Clarification Policy

Ask a concise clarification question when the answer would change:

- the output grain;
- a metric formula;
- a privacy or retention rule;
- the source of truth;
- an execution target;
- a regulatory or financial outcome.

Record safe defaults in `assumptions`. Never hide an invented business rule inside generated code.
