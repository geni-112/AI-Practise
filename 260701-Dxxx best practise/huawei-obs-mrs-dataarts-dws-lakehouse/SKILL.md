---
name: huawei-obs-mrs-dataarts-dws-lakehouse
description: >-
  Build, run, troubleshoot, package, or explain the DockOne Huawei Cloud lakehouse demo covering two converging flows: batch ingress from S3/OMS/OBS into MRS Spark Apache Iceberg, DataArts Factory, DWS, and BI; plus streaming ingress from RDS for PostgreSQL through DMS Kafka and MRS Flink into OBS raw JSON before the same Iceberg/DataArts/DWS path. Use when Codex needs to generate synthetic DockOne raw CDC data, simulate billing.contracts data, load RDS PostgreSQL, publish to DMS Kafka, render or submit MRS Flink SQL, submit MRS Iceberg processing, trigger DataArts scheduling jobs, load/query DWS, deploy or verify the realtime monitoring website, inventory the existing Huawei Cloud resources, or produce repeatable run evidence for this specific workflow.
---

# Huawei OBS-MRS-DataArts-DWS Lakehouse

## Core safety rules

- Never store or print Huawei Cloud account passwords, AK/SK, DWS passwords, MRS passwords, Kafka passwords, SSH private keys, or Terraform state.
- Load credentials from environment variables, DPAPI/local secret stores, cloud secret services, or the active shell only.
- Raw data in OBS is JSON/JSONL or manifest data, not Iceberg. MRS Spark converts raw data into Apache Iceberg tables.
- Keep CDM and RDS out of the batch path. RDS is only part of the optional streaming ingress.
- Treat the OBS bucket name as a resource identifier only; the current bucket still includes an older `retail-lakehouse` token, but data/table naming should remain DockOne/billing, not retail.

## Architecture summary

The target demo has two labeled ingress flows that converge in OBS:

1. `Flow 1 / batch: S3 -> OMS -> Huawei OBS -> MRS Spark Iceberg -> DataArts -> DWS -> BI`
2. `Flow 2 / streaming: RDS for PostgreSQL -> DMS Kafka -> MRS Flink -> OBS raw JSON -> MRS Spark Iceberg -> DataArts -> DWS -> BI`

Read `references/architecture_current_state.md` when checking whether live Huawei Cloud resources match this target. The latest diagram assets are under `assets/architecture/`.

## Resource layout

- `assets/mrs/`: Spark/Iceberg processing job.
- `assets/flink/`: Flink SQL template for DMS Kafka `billing.contracts` to OBS raw JSON.
- `assets/sql/`: PostgreSQL schema for the streaming source table.
- `assets/seed-data/`: deterministic DockOne ExampleApp CDC seed data and schema metadata.
- `assets/monitor-site/`: realtime monitoring website/API assets.
- `scripts/orchestration/`: one-shot PowerShell wrappers.
- `scripts/batch/`: DockOne raw-data generation and OBS/MRS asset uploads.
- `scripts/streaming/`: RDS, DMS Kafka, and MRS Flink helpers.
- `scripts/mrs/`, `scripts/dataarts/`, `scripts/dws/`: service-specific processing, scheduling, loading, and querying.
- `scripts/cloud/`, `scripts/diagnostics/`, `scripts/env/`: resource bootstrap, inventory, probes, and environment helpers.
- `references/`: runbooks, environment map, script catalog, current-state notes, and DWS SQL.

For a categorized script list, read `references/script_catalog.md`.

## Standard batch workflow

1. Read `references/environment.md` before touching live cloud resources.
2. Install script dependencies from `scripts/requirements.txt` if missing.
3. Use `scripts/orchestration/run_full_pipeline.ps1` for a repeatable end-to-end run.
4. If running step-by-step, follow `references/runbook.md`.
5. Prefer DataArts for orchestration. Use direct MRS/DWS scripts only as an explicit fallback or when the user asks for bypass/smoke validation.

Typical one-shot command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_full_pipeline.ps1 -TargetMiB 50
```

## Streaming contracts extension

Use this when the user asks for RDS PostgreSQL, DMS Kafka, MRS Flink, or the `billing.contracts` business stream.

1. Read `references/streaming_contracts_flow.md`.
2. Generate 5-10 MiB of source data with `scripts/streaming/generate_contracts_rds_data.py`.
3. Load RDS, publish DMS Kafka, render/run MRS Flink SQL, and confirm OBS raw JSON.
4. Continue with the existing MRS Spark Iceberg, DataArts, DWS, and BI validation steps.

Typical wrapper command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_streaming_contracts_flow.ps1 -TargetMiB 8
```

Use `-SkipRdsLoad -SkipKafkaPublish` for local artifact generation only. Use `-ContinueAfterFlink` only after MRS Flink has landed raw JSON in OBS.

## Common validation

- OBS raw layer contains JSON/JSONL files under `raw/dockone_exampleapp/`.
- MRS Spark completes and writes Iceberg metadata under `lake/iceberg/dockone/`.
- Golden CSV exists under `publish/dockone_table_metrics/current/`.
- DWS schema `dockone_golden` has `table_metrics_stage`, `table_metrics`, and `table_metrics_bi`.
- `scripts/dws/query_dws.py` returns nonzero rows.
- Monitoring site/API reports the active OBS, MRS, DataArts, and DWS topology; no CDM/RDS appears unless streaming is in scope.

## When to read references

- Read `references/environment.md` before live operations or credential/resource-ID work.
- Read `references/architecture_current_state.md` before resource/data-flow match checks or diagram updates.
- Read `references/script_catalog.md` before editing or invoking categorized scripts.
- Read `references/runbook.md` before a live batch end-to-end run.
- Read `references/streaming_contracts_flow.md` before using the RDS/DMS/Flink extension.
- Read `references/dws_queries.sql` when validating warehouse outputs or writing BI queries.
