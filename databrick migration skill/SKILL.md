---
name: databricks-snowflake-huawei-migration
description: Migrate Databricks or Snowflake demo scripts, notebooks, SQL, Delta Lake pipelines, CDC jobs, and warehouse workloads into Huawei Cloud demo artifacts using OBS, MRS Spark with Iceberg, DataArts Factory jobs, and DWS-compatible SQL. Use when converting Delta Lake to Iceberg, translating Databricks Jobs to Huawei DataArts/MRS jobs, adapting Snowflake or Databricks SQL to GaussDB(DWS), consulting on Databricks migration scripts, comparing AI-generated conversion documents against human conversion documents, or updating this personal migration skill with reusable lessons from each demo/session.
---

# Databricks/Snowflake Huawei Migration

## Core Workflow

1. Inventory the source before editing. Prefer `scripts/migration_inventory.py <source_dir> --out <work_dir>` to find Delta, Databricks, Snowflake, SQL, notebook, and job-definition patterns.
2. Classify each artifact as lake table logic, orchestration/job logic, warehouse SQL, data generation, deployment, or validation.
3. Read only the relevant reference files:
   - Delta Lake or Databricks table logic: `references/delta-to-iceberg.md`
   - Databricks Jobs, notebooks, clusters, or workflow JSON/YAML: `references/jobs-to-huawei.md`
   - Snowflake or Databricks SQL to DWS: `references/sql-to-dws.md`
   - MRS PySpark + Iceberg execution runbooks: `references/mrs-pyspark-iceberg-runbook.md`
   - Demo-specific lessons and known pitfalls: `references/demo-lessons.md`
   - Skill update/capture rules: `references/update-protocol.md`
   - AI-vs-human conversion document comparison: `references/document-comparison-feedback.md`
4. Produce migration artifacts that can run as a demo, not just conceptual notes. Include Spark scripts, SQL files, DataArts job outlines, OBS paths, DWS DDL/DML, smoke tests, and rollback/cleanup notes when relevant.
5. Preserve source intent. Keep business logic, CDC ordering, schema evolution behavior, partitioning, and validation metrics visible in comments or migration notes.
6. Run the Always-Learning Protocol before finishing. Update `references/demo-lessons.md` when a new demo exposes a reusable pattern, platform limitation, workaround, or verified command.

## Migration Output Shape

For each migrated demo, create or update:

- `analysis/` or `docs/`: source inventory, assumptions, unsupported features, and mapping table.
- `mrs/` or `spark/`: PySpark/Scala/Spark SQL scripts using OBS and Iceberg-compatible catalogs.
- `dataarts/`: job graph, node parameters, schedule/trigger notes, and API/UI fallback steps.
- `dws/`: DWS DDL, load SQL, transformed analytic SQL, and validation queries.
- `scripts/`: repeatable local helpers for generating synthetic data, uploading to OBS, triggering MRS/DataArts, or smoke testing.
- `runbooks/`: MRS client setup, spark-sql/spark-submit commands, Python environment packaging, and validation steps when the demo needs operator instructions.

Use repository conventions when they exist. If no structure exists, keep outputs small and demo-oriented.

## Decision Rules

- Prefer Iceberg for lakehouse table replacement unless the user explicitly asks for Hudi or a previous demo requires Hudi.
- Prefer OBS as the durable object store boundary between generated/raw data, MRS Spark outputs, DataArts orchestration, and DWS loading.
- Treat DataArts Factory as orchestration. Put heavy transforms in MRS Spark or DWS SQL, not in hand-coded orchestration nodes.
- Treat DWS as the serving/analytics layer. Convert warehouse SQL to DWS syntax and keep lakehouse table maintenance in MRS.
- For unsupported features, create a demo-safe approximation plus a clearly named note. Do not silently drop semantics such as CDC deletes, merge keys, time travel, or deduplication windows.

## Iteration Discipline

After every real demo migration:

1. Add exact failing source pattern or command to `references/demo-lessons.md`.
2. Add the verified Huawei replacement pattern.
3. Note region/service assumptions such as OBS bucket naming, MRS Spark version, DWS compatibility, or DataArts API/UI behavior.
4. If a repeated transformation becomes mechanical, add or extend a script in `scripts/` and test it.

Keep the skill concise. Put detailed rules in references, not in this file.

## Always-Learning Protocol

When a user opens a new session and asks to convert, inspect, explain, consult on Databricks/Snowflake migration scripts, or compare AI-generated conversion documents with human conversion documents, treat that interaction as a chance to improve this personal skill.

Before the final response:

1. Identify whether the session produced a reusable lesson: a new source pattern, rewrite, Huawei limitation, demo workaround, validation command, repeated manual step, or AI-vs-human conversion gap.
2. If yes, append a dated entry to `references/demo-lessons.md`. Prefer `scripts/append_demo_lesson.py` for consistent formatting.
3. If the lesson changes a general rule, update the relevant reference file as well.
4. If the lesson is one-off, customer-specific, secret-bearing, or not verified, do not add it; summarize it only in the current answer.
5. Sync local skill changes to GitHub with `scripts/sync_to_github.py`; `append_demo_lesson.py` already does this automatically unless disabled.
6. In the final response, briefly state whether the skill was updated, which file changed, and whether the GitHub mirror was pushed.
