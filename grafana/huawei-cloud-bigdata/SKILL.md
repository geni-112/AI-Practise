---
name: huawei-cloud-bigdata
description: Plan, automate, operate, and observe Huawei Cloud big-data stacks using OBS, MRS, FusionInsight Manager, DataArts, CDM, DWS, ECS, EIP, Cloud Eye, Grafana OSS, Prometheus, Loki, and Superset. Use when Codex needs to design infrastructure, create deployment scripts, build data lake or warehouse pipelines, implement Databricks-style monitoring, correlate jobs with nodes and logs, ingest big-data logs, estimate minimum resource shapes, or troubleshoot Huawei Cloud big-data workflows. Supply secrets from environment variables, CLI profiles, instance metadata, or cloud secret services; never embed them in the skill or repository.
---

# Huawei Cloud BigData

## Operating Rules

- Never ask the user to paste Huawei Cloud account passwords, AK/SK, database passwords, or private keys into chat unless no safer channel exists and the user explicitly accepts the risk.
- Never store secrets in `SKILL.md`, generated code, Terraform variables, README files, logs, screenshots, or committed files.
- Prefer environment variables for local automation:
  - `HUAWEICLOUD_ACCESS_KEY`
  - `HUAWEICLOUD_SECRET_KEY`
  - `HUAWEICLOUD_REGION`, default `la-south-2` for LA-Santiago when requested
  - `HUAWEICLOUD_PROJECT_ID`
  - `DWS_ADMIN_PASSWORD`
  - `SUPERSET_SECRET_KEY`
- For production, recommend IAM least privilege, temporary credentials where available, KMS/DEW for encryption keys, and Cloud Eye/AOM for metrics.
- Confirm region and quota before creating paid resources. Use pay-per-use for POC unless the user asks for yearly/monthly.
- Reuse an existing ECS only after confirming its identity and purpose. Never delete or replace a host merely because quota is constrained.
- Prefer private VPC access for monitoring. Add an EIP only when requested, and terminate public traffic with HTTPS.
- Treat FusionInsight Manager's self-signed certificate as a trust decision: verify and trust the expected certificate explicitly instead of disabling TLS verification.
- Mask password-, token-, secret-, AK-, and SK-looking values before exporting metrics or sending logs to Loki.

## Default Architecture

- Region: LA-Santiago, region id `la-south-2`, when the user asks for Santiago.
- Network: one VPC, one private subnet, restrictive security groups, EIP only for the web/Superset ingress layer.
- Storage: OBS Standard single-AZ for POC raw/bronze/silver/gold buckets; lifecycle raw archives after validation.
- Processing: MRS with Spark/Hive for batch cleansing; use CDM only when managed connector orchestration is more important than Spark-native ingestion.
- Warehouse: DWS for serving-layer star schemas and BI aggregations.
- BI: Superset on ECS or CCE, connected to DWS over private subnet; expose through Nginx with HTTPS when a domain is available.
- Monitoring: run Grafana OSS, Prometheus, Loki, Huawei API exporters, and Node Exporter on a private ECS in the same VPC as MRS. Collect pipeline events, Cloud Eye metrics, MRS and DataArts job history, OBS log inventory, FusionInsight Manager metrics, DWS load state, and BI refresh metadata.

## Workflow

1. Gather requirements: region, public access domain, dataset source, retention, refresh cadence, estimated source size, and whether the target is POC or production.
2. Size minimally for the first run, then state what must be confirmed in the cloud console: service availability in `la-south-2`, quotas, exact flavor names, and current pay-per-use prices.
3. Produce IaC plus scripts. Keep resource names parameterized and ensure every destructive command is a separate explicit step.
4. Build data flow in layers:
   - Raw files to `obs://.../raw/`
   - Cleaned, deduplicated data to `obs://.../silver/`
   - Curated dimensional or fact tables to `obs://.../gold/`
   - DWS tables loaded from gold data
   - Superset dashboards reading DWS
5. Add observability events for `downloaded_bytes`, `obs_bytes`, `mrs_cleaned_rows`, `dws_loaded_rows`, `bi_refresh_time`, `stage_duration_seconds`, and error counts.
6. For Grafana, job traceability, memory metrics, FusionInsight metrics, or unified log requests, read [references/grafana-mrs-observability.md](references/grafana-mrs-observability.md) and follow its source hierarchy and validation gates.
7. Before finalizing, explain any resources that still require live-console verification, certificate trust, Manager-side configuration, or credentials.

## Sizing Heuristics

- For a 50 GB public-data POC, start with one small ECS for web/Superset, one OBS bucket, one small MRS Spark/Hive cluster, and the smallest DWS shape that the region allows.
- Do not recommend DWS low-memory production use; call it POC-only when using 4 vCPU/16 GB or similar small nodes.
- For repeatable batch ingestion, prefer scripts scheduled by cron/systemd/Airflow over manual console actions.
- For CDM, use `cdm.large` or larger only when the connector path is required. Spark on MRS is usually enough for OBS-to-MRS file workflows.
- For external access, expose only HTTP/HTTPS and Superset ports through Nginx or ELB. Keep MRS, DWS, and database ports private.
- Size Loki retention, OBS-log history, and MRS job pagination explicitly. Bound log object count, file size, history window, and download concurrency before the first historical backfill.

## Useful References

- Huawei Cloud MRS API supports create-cluster-and-submit-job workflows.
- CDM is a batch data integration service and supports OBS/MRS/database connectors, incremental migration, field conversion, MD5 checks, and dirty-data archiving.
- OBS pay-per-use is suitable for short-term or bursty workloads; Standard storage is commonly used for active POC data.
- DWS supports pay-per-use and is appropriate for OLAP serving, but exact node shapes and prices must be checked in the selected region.
- Huawei regional API availability is not uniform. Discover and test the live endpoint before designing a dashboard around it; preserve an explicit `unavailable` state instead of fabricating data.
