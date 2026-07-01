# Streaming contracts flow

Use this reference for the optional business stream:

```text
RDS for PostgreSQL -> DMS Kafka -> MRS Flink -> OBS raw JSON -> MRS Spark Iceberg -> DataArts -> DWS -> BI/third-party systems
```

The raw OBS files are JSON CDC envelopes. They become Apache Iceberg tables only after MRS Spark processes them.

## Source table

The RDS source table is `billing.contracts`. The DDL is bundled at:

```text
assets/sql/billing_contracts_schema.sql
```

The table includes these columns:

```text
id, client_id, product_id, account_id, person_id, external_id, description,
status, overdue_at, amount_asset_iso_code, created_at, updated_at,
profile_id, cycle_id, first_due_date, effective_date, contracted_amount
```

The generator inserts UUIDv7-style values explicitly. The DDL includes a compatibility `uuidv7()` fallback so PostgreSQL versions without native UUIDv7 support can still create the table default.

## Generate 5-10 MiB of source data

```powershell
python scripts/streaming/generate_contracts_rds_data.py --target-mib 8 --out .\dockone-stream-run\data
```

Outputs:

- `contracts.csv`: bulk-load file for RDS PostgreSQL.
- `contracts_cdc.jsonl`: CDC-style JSON events for local testing or direct Kafka publish.
- `manifest.json`: one-table manifest for downstream MRS Spark processing.
- `contracts_generation_summary.json`: row count and file sizes.

## Load RDS PostgreSQL

Set RDS environment variables from `references/environment.md`, then run:

```powershell
python scripts/streaming/load_contracts_to_postgres.py `
  --csv .\dockone-stream-run\data\contracts.csv `
  --replace `
  --summary .\dockone-stream-run\contracts-rds-load-summary.json
```

This creates `billing.contracts` if needed and loads the generated rows through PostgreSQL `COPY`.

## Publish to DMS Kafka

Preferred path, reading from RDS:

```powershell
python scripts/streaming/publish_contracts_to_dms_kafka.py `
  --source db `
  --topic $env:DMS_KAFKA_TOPIC `
  --bootstrap-servers $env:DMS_KAFKA_BOOTSTRAP_SERVERS `
  --summary .\dockone-stream-run\contracts-kafka-publish-summary.json
```

Local/smoke path, using generated JSONL:

```powershell
python scripts/streaming/publish_contracts_to_dms_kafka.py `
  --source jsonl `
  --jsonl .\dockone-stream-run\data\contracts_cdc.jsonl `
  --dry-run
```

## Render and run MRS Flink SQL

```powershell
python scripts/streaming/render_contracts_flink_sql.py `
  --bucket $env:DEPLOYMENT_OBS_BUCKET `
  --topic $env:DMS_KAFKA_TOPIC `
  --bootstrap-servers $env:DMS_KAFKA_BOOTSTRAP_SERVERS `
  --out .\dockone-stream-run\flink_contracts_kafka_to_obs.sql
```

If the SQL is safe to upload, meaning it contains no real password:

```powershell
python scripts/streaming/upload_flink_contracts_assets.py `
  --sql .\dockone-stream-run\flink_contracts_kafka_to_obs.sql `
  --bucket $env:DEPLOYMENT_OBS_BUCKET
```

Submit the SQL on MRS Flink. Expected OBS raw path:

```text
raw/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.billing.contracts/
```

## Continue existing downstream flow

After Flink lands raw JSON in OBS:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_streaming_contracts_flow.ps1 `
  -TargetMiB 8 `
  -SkipRdsLoad `
  -SkipKafkaPublish `
  -ContinueAfterFlink
```

This uploads the streaming manifest and Spark assets, then continues through MRS Spark Iceberg, DataArts, DWS load/query, and BI validation.

## Local artifact-only command

Use this when the user asks only to produce data and scripts:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_streaming_contracts_flow.ps1 `
  -TargetMiB 8 `
  -SkipRdsLoad `
  -SkipKafkaPublish
```

## Runner ECS helper

Use `scripts/streaming/run_runner_stream_ingest.py` only when local access cannot reach private RDS/DMS endpoints and the runner ECS can. It uploads the RDS load/Kafka publish scripts plus the generated `contracts.csv` to the runner and pulls back summary JSON files into the current working directory's `runs/` folder.

## Validation checklist

1. `contracts_cdc.jsonl` is between 5 and 10 MiB unless the user requested another size.
2. RDS table `billing.contracts` exists and has the generated row count.
3. DMS Kafka topic `dockone.billing.contracts` receives the same number of CDC messages.
4. MRS Flink writes JSON files to the OBS raw contracts prefix.
5. MRS Spark creates or refreshes Iceberg table `obs_iceberg.silver.dockone_exampleapp_billing_contracts`.
6. Golden metrics include `dockone_exampleapp_billing_contracts`.
7. DWS `dockone_golden.table_metrics_bi` has a contracts row with nonzero records.
