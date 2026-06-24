# AI-vs-Human Conversion Document Feedback

Use this reference when the user provides both an AI-generated conversion document and a human conversion document for the same Databricks/Snowflake migration task.

## Goal

Treat the human document as calibration input for the skill. Identify where the AI migration output missed, overcomplicated, simplified incorrectly, or formatted the result less usefully. Convert reusable gaps into skill updates.

## Comparison Workflow

1. Confirm both documents target the same source scripts, tables, jobs, or SQL workload.
2. Compare by migration dimension:
   - Delta/Iceberg table conversion
   - CDC and merge semantics
   - Databricks Jobs to DataArts/MRS orchestration
   - Snowflake/Databricks SQL to DWS syntax
   - OBS paths, deployment steps, parameters, and validation
   - Demo readability, artifact layout, and operator runbook quality
3. Classify each difference:
   - `missing-rule`: human document contains a rule not in the skill.
   - `wrong-rule`: AI output applied a rule that should be changed.
   - `overfit`: human document is project-specific and should not become a general rule.
   - `style`: formatting or documentation style improvement.
   - `validation`: human document includes better smoke tests or acceptance checks.
4. Update the skill only for reusable differences. Keep customer-specific details out.
5. Append a lesson to `references/demo-lessons.md` with comparison evidence.

## Capture Format

When appending a lesson from a document comparison, use:

- Source pattern: the original Databricks/Snowflake feature or migration area being compared.
- Issue: the AI-generated document gap compared with the human document.
- Huawei replacement: the corrected rule, document pattern, or migration step learned from the human document.
- Validation: state whether the human document was accepted, manually verified, or still needs runtime validation.

## What to Promote

Promote to general references when the comparison reveals:

- A repeatable Delta-to-Iceberg conversion nuance.
- A DataArts/MRS orchestration pattern that makes demos easier to run.
- A DWS SQL rewrite that avoids known incompatibility.
- A validation query or smoke test that catches real migration mistakes.
- A document structure that makes future conversion docs clearer.

Do not promote:

- Customer names, credentials, private topology, private endpoints, or unredacted IDs.
- Human document phrasing copied wholesale.
- Choices that only apply to one demo's artificial naming scheme.
