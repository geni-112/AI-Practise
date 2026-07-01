# Architecture and current-state notes

Use this reference when the user asks whether the live environment matches the latest two-flow architecture or asks to update diagrams.

## Target architecture

The approved logical flow is:

```text
① Historical/batch ingress:
S3 -> OMS -> Huawei OBS -> MRS Spark -> Apache Iceberg lakehouse -> DataArts -> DWS -> BI/third-party systems

② Near-real-time ingress:
RDS for PostgreSQL -> DMS Kafka -> MRS Flink -> Huawei OBS raw JSON -> MRS Spark -> Apache Iceberg lakehouse -> DataArts -> DWS -> BI/third-party systems
```

The two flows converge at OBS raw data and share the same downstream MRS Spark Iceberg, Golden, DataArts, DWS, and BI path.

## Latest diagram assets

Use these files when exporting or editing the diagram:

- `assets/architecture/dockone-regular-two-flow-architecture.drawio`
- `assets/architecture/dockone-regular-two-flow-architecture.png`
- `assets/architecture/dockone-regular-two-flow-architecture.json`
- `assets/architecture/dockone-regular-two-flow-resources.csv`

## Current live resource match

As of the last validation on 2026-07-01, excluding AWS-side resources:

| Target part | Current status | Notes |
| --- | --- | --- |
| Huawei OBS raw landing | Present | Batch raw data exists in OBS. Current bucket name still contains the old `retail-lakehouse` token because OBS was intentionally not renamed. |
| S3 -> OMS -> OBS | Not fully implemented | OMS task inventory did not show an active/visible migration task. Existing batch raw data was loaded by scripts, not by a confirmed OMS task. |
| MRS Spark -> Iceberg | Present and validated | Raw JSON/JSONL becomes Apache Iceberg only after MRS Spark processing. |
| DataArts MRS orchestration | Present | Use `dockone_obs_mrs_iceberg_golden` for the MRS/Iceberg stage when available. |
| DataArts DWS publication | Present but fragile | The latest observed `dockone_golden_to_dws` instance status was failed; DWS was still validated with direct loading scripts. Re-check before claiming DataArts-only success. |
| DWS Golden serving | Present and validated | Schema is `dockone_golden`; expected objects include `table_metrics_stage`, `table_metrics`, and `table_metrics_bi`. |
| RDS -> DMS Kafka -> MRS Flink -> OBS | Present and validated as streaming extension | This is part of flow ② only. It lands raw JSON into OBS before downstream Iceberg conversion. |
| Monitoring website | Present | Last known public URL: `http://176.52.139.160/`; title returned `DockOne Monitor`. |
| CDM/RDS old test link | Removed/out of scope | Do not reintroduce CDM unless the user explicitly asks for a separate path. |

## Naming guidance

- Cloud resources that can be renamed in place should use `dockone` or `dockone-iceberg`.
- Do not use `retail` in generated table names, schemas, diagrams, or reports.
- If an immutable resource still has an older name, document it as a legacy resource identifier and do not infer architecture semantics from it.
