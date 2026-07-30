# Demo Lessons

Use this file as the living memory for patterns discovered during real migrations. Keep entries short, dated, and actionable.

## Entry Template

```markdown
## YYYY-MM-DD - Demo or customer/context name

Source pattern:
- Exact Databricks/Snowflake/Delta/DataArts/DWS pattern observed.

Issue:
- What failed, surprised, or needed adaptation.

Huawei replacement:
- Verified rewrite, command, job shape, SQL pattern, or workaround.

Validation:
- Smoke test, row count, UI confirmation, or log line proving it worked.
```

## 2026-06-24 - Initial Skill Baseline

Source pattern:
- Databricks/Snowflake demos often mix Delta Lake storage, notebook orchestration, dbutils widgets, Snowflake SQL idioms, and dashboard-serving SQL in one repository.

Issue:
- A useful demo migration needs an inventory first, then separate rewrites for lake tables, orchestration, and DWS SQL.

Huawei replacement:
- Use OBS as the data boundary, MRS Spark with Iceberg for lakehouse tables, DataArts Factory for orchestration, and DWS for serving SQL.

Validation:
- Baseline skill created with references for Delta-to-Iceberg, Jobs-to-Huawei, and SQL-to-DWS rewrites.


## 2026-06-24 - Always-learning mechanism

Source pattern:
- New Databricks/Snowflake migration sessions may happen in fresh Codex windows, so reusable migration lessons must be persisted in the skill rather than only summarized in chat.

Issue:
- Without an explicit capture protocol, useful Delta, Jobs, DataArts, MRS, DWS, and SQL rewrite discoveries can be lost between sessions.

Huawei replacement:
- Add an Always-Learning Protocol to SKILL.md, add references/update-protocol.md, and use scripts/append_demo_lesson.py to append structured reusable lessons.

Validation:
- Skill files updated and append_demo_lesson.py successfully appended this baseline entry.


## 2026-06-24 - AI-vs-human conversion document feedback

Source pattern:
- Future sessions may compare skill-generated Databricks/Snowflake migration documents with human-authored conversion documents for the same source workload.

Issue:
- Reusable human corrections could be lost if document comparison is treated only as review feedback instead of skill calibration data.

Huawei replacement:
- Add document-comparison-feedback.md, extend SKILL.md trigger text, and update the skill update protocol so reusable AI-vs-human gaps become demo lessons or reference-rule updates.

Validation:
- Skill files updated; quick validation will be run after this entry.


## 2026-06-24 - PySpark Iceberg script test doc merge

Source pattern:
- User-provided Word document pyspark+iceberg脚本测试.docx described Databricks-to-MRS PySpark/Iceberg script modifications, MRS client commands, spark-submit patterns, and Spark SQL compatibility fixes.

Issue:
- Existing skill lacked a dedicated MRS PySpark + Iceberg execution runbook and did not fully capture notebook.run/entry_point/exit rewrites, overwriteSchema handling, version-hint.text path-read pitfalls, Catalyst EXISTS non-equi bug workaround, DATEADD-to-add_months, and SELECT * EXCEPT projection rewrites.

Huawei replacement:
- Added mrs-pyspark-iceberg-runbook.md; updated delta-to-iceberg.md, jobs-to-huawei.md, sql-to-dws.md, SKILL.md routing, and migration_inventory.py patterns.

Validation:
- Extracted 130 paragraphs and 2 tables from the DOCX; merged reusable rules into skill references; running quick_validate.py and inventory smoke test after updates.


## 2026-06-24 - GitHub mirror sync for personal migration skill

Source pattern:
- User requested the local Databricks migration skill files be mirrored into GitHub repository geni-112/AI-Practise under databrick migration skill/.

Issue:
- Local skill updates would otherwise remain only on this machine and could drift from the GitHub copy used for backup, review, or reuse.

Huawei replacement:
- Added scripts/sync_to_github.py, updated append_demo_lesson.py to auto-sync by default, and updated SKILL.md/update-protocol.md so every local skill update is followed by a GitHub mirror push.

Validation:
- GitHub repo access and push permission confirmed; quick_validate.py and sync_to_github.py will be run before final response.


## 2026-06-24 - Automatic GitHub linkage hardening

Source pattern:
- User emphasized that the Databricks migration skill must remember the GitHub linkage mechanism and ensure all local updates can automatically trigger GitHub synchronization.

Issue:
- The prior flow had automatic sync for append_demo_lesson.py, but larger manual reference/SKILL updates depended on the agent remembering to run sync_to_github.py.

Huawei replacement:
- Added record_update.py as the preferred unified update entrypoint, added validation inside sync_to_github.py before push, and updated SKILL.md/update-protocol.md to require validation plus GitHub mirror sync for every local skill update.

Validation:
- record_update.py is being used for this update so lesson append, quick_validate.py, and GitHub sync run as one chain.


## 2026-07-29 - Delta/Iceberg and Spark SQL migration hardening

Source pattern:
- Databricks PySpark used Delta format declarations, Delta overwriteSchema, DBFS or mounted storage paths, source-config format fields, a Databricks-only `sat_pypi_packages` import, and Spark SQL containing a correlated EXISTS with equality plus date-range predicates, SQL Server DATEADD, and `SELECT * EXCEPT`.

Issue:
- Mechanical token replacement requires validation: Delta directories are not automatically Iceberg table roots, Databricks packages are unavailable on MRS, and Catalyst can fail while rewriting the complex correlated EXISTS to `LeftExistenceJoin` with a missing-attribute error such as `Couldn't find Fecha_Alta`. The initial assumption that Iceberg `overwriteSchema` must always be replaced was superseded by the verified 2026-07-30 Padron Base result below.

Huawei replacement:
- Use catalog-backed Iceberg reads/writes, explicit Iceberg schema evolution and intentional overwrite semantics, HDFS/OBS Iceberg table locations, `iceberg` in all source configurations, and explicit local imports packaged with the MRS job. Rewrite the EXISTS as `LEFT JOIN` plus aggregation at the unique outer-row grain, use `add_months` for month arithmetic, and explicitly enumerate projected columns.

Validation:
- Rules were consolidated into delta-to-iceberg.md, jobs-to-huawei.md, and sql-to-dws.md with executable-shape examples; skill validation and GitHub mirror diff are run before publishing.


## 2026-07-29 - Padron Base source vs ICEBERG code comparison

Source pattern:
- A Databricks-exported Padron Base Python module was compared with its manually converted ICEBERG version. The target added explicit imports, removed notebook markers, changed Delta format tokens, repaired a missing CTE `AS`, rewrote DATEADD, converted a correlated EXISTS to LEFT JOIN plus GROUP BY, and replaced `SELECT * EXCEPT` with an explicit projection.

Issue:
- The converted file contained five initially unverified `overwriteSchema` options on Iceberg writes and path-based `.save(...)` calls whose Iceberg table-root validity was not demonstrated during static comparison. Python compilation passed both files even though it cannot validate SQL strings, runtime package availability, or Iceberg semantics. Grouping by projected columns can also collapse duplicate outer rows. The `overwriteSchema` concern was later resolved by runtime validation recorded in the 2026-07-30 entry below.

Huawei replacement:
- Treat conversion as a two-pass process: implement portability rewrites, then scan the target for residual Delta/Databricks constructs. Use explicit local imports and packaged modules, validate CTE syntax and generated SQL in Spark, choose explicit Iceberg overwrite/schema-evolution behavior, and preserve correlated-EXISTS row multiplicity with a stable outer-row key.

Validation:
- Compared the complete Git diff, scanned both files for migration patterns, and ran `python -m py_compile` successfully on both. Runtime Spark/Iceberg execution was not available during this comparison, so the five writes were recorded as pending compatibility checks rather than rejected conversions.


## 2026-07-30 - Padron Base Iceberg overwriteSchema runtime correction

Source pattern:
- The migrated Padron Base jobs use `.write.mode("overwrite").option("overwriteSchema", "true").format("iceberg").save(target_path)`.

Issue:
- Static comparison had classified the five occurrences as unsupported residuals because upstream Iceberg guidance favors explicit DataFrameWriterV2 operations or documented schema-merge behavior.

Huawei replacement:
- Retain the `overwriteSchema` option for the already validated Padron Base MRS Spark/Iceberg environment. For other MRS/Spark/Iceberg versions, classify the same pattern as a compatibility check and verify schema, data, partitions, and snapshot before accepting or replacing it.

Validation:
- User confirmed on 2026-07-30 that this exact overwriteSchema portion has been successfully validated in the target environment. The skill and scanner were corrected so it is no longer reported as an automatic migration failure.
