# Script catalog

Run commands from the skill root unless a script says otherwise.

## Orchestration

- `scripts/orchestration/run_full_pipeline.ps1`: batch OBS -> MRS Iceberg -> DataArts/DWS one-shot wrapper.
- `scripts/orchestration/run_streaming_contracts_flow.ps1`: RDS/DMS/Flink ingress wrapper with optional downstream continuation.

## Batch raw and OBS/MRS assets

- `scripts/batch/generate_dockone_cdc.py`: generate DockOne ExampleApp CDC-style JSONL raw data.
- `scripts/batch/upload_raw_to_obs.py`: upload generated raw files and manifests to OBS.
- `scripts/batch/upload_mrs_assets.py`: upload Spark job, manifest, schema metadata, and Iceberg runtime artifacts to OBS.

## Streaming ingress

- `scripts/streaming/generate_contracts_rds_data.py`: generate 5-10 MiB `billing.contracts` CSV and CDC JSONL.
- `scripts/streaming/load_contracts_to_postgres.py`: create/load RDS PostgreSQL `billing.contracts`.
- `scripts/streaming/publish_contracts_to_dms_kafka.py`: publish RDS rows or JSONL CDC envelopes to DMS Kafka.
- `scripts/streaming/render_contracts_flink_sql.py`: render MRS Flink SQL from `assets/flink/contracts_kafka_to_obs.sql.tpl`.
- `scripts/streaming/upload_flink_contracts_assets.py`: upload rendered Flink SQL to OBS when it contains no real secrets.
- `scripts/streaming/run_mrs_flink_sql.py`: submit rendered Flink SQL through MRS where supported.
- `scripts/streaming/run_mrs_flink_kafka_to_obs_job.py`: run a Kafka-to-OBS Flink job on MRS.
- `scripts/streaming/run_mrs_flink_kafka_to_obs_jar.py`: helper for JAR-based Flink submission.
- `scripts/streaming/run_runner_kafka_to_obs.py`: runner/ECS-based Kafka-to-OBS fallback.
- `scripts/streaming/run_runner_stream_ingest.py`: upload/run RDS load and Kafka publish scripts from the runner ECS.

## MRS, DataArts, and DWS

- `scripts/mrs/run_mrs_iceberg_job.py`: direct MRS Spark/Iceberg submission.
- `scripts/dataarts/trigger_dataarts_job.py`: trigger DataArts Factory jobs.
- `scripts/dws/download_golden_csv.py`: download Golden CSV from OBS.
- `scripts/dws/load_dws_table_metrics.py`: load/refresh DWS Golden tables.
- `scripts/dws/query_dws.py`: run read-only DWS validation queries.

## Cloud bootstrap and diagnostics

- `scripts/cloud/ensure_stream_resources.py`: create/check streaming resources such as RDS and DMS Kafka.
- `scripts/cloud/ensure_mrs_flink_cluster.py`: create/check the MRS Flink cluster.
- `scripts/cloud/ensure_runner_ecs.py`: create/check the runner ECS used for private-network operations.
- `scripts/diagnostics/huawei_inventory.py`: inventory relevant Huawei Cloud resources.
- `scripts/diagnostics/list_huawei_products.py`: list product availability metadata.
- `scripts/diagnostics/mrs_remote_exec.py`: execute safe remote MRS diagnostics.
- `scripts/diagnostics/fetch_mrs_file.py`: fetch files from MRS nodes for troubleshooting.
- `scripts/diagnostics/fetch_mrs_yarn_logs.py`: fetch YARN logs for MRS jobs.
- `scripts/diagnostics/probe_mrs_flink_client.py`: check Flink client availability on MRS.
- `scripts/diagnostics/probe_mrs_node_logs.py`: inspect selected MRS node logs.
- `scripts/diagnostics/test_mrs_obs_credentials.py`: test MRS/OBS access without printing credentials.
- `scripts/env/with_huawei_env.ps1`: helper pattern for loading environment variables securely.
