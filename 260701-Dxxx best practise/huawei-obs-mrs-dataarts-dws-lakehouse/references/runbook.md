# End-to-end batch runbook

This runbook executes the final batch path:

```text
OBS raw JSONL -> MRS Spark/Iceberg Bronze/Silver/Golden -> DataArts orchestration -> DWS Golden schema -> BI/third-party queries
```

Raw files are not Iceberg tables. Iceberg tables are created by the MRS Spark job.

## 1. Prepare the shell

From the skill root:

```powershell
python -m pip install -r scripts/requirements.txt
```

Set the environment variables listed in `references/environment.md`. Keep secrets in the shell or a secure local/cloud secret store only.

## 2. Generate raw DockOne data

Generate a 50 MiB run:

```powershell
python scripts/batch/generate_dockone_cdc.py --target-mib 50 --out .\dockone-run\data
```

The generated files are CDC-style JSONL records using DockOne ExampleApp table/domain names.

## 3. Upload raw data to OBS

```powershell
python scripts/batch/upload_raw_to_obs.py --data-dir .\dockone-run\data --bucket $env:DEPLOYMENT_OBS_BUCKET
```

Expected OBS prefix:

```text
raw/dockone_exampleapp/
```

## 4. Upload MRS job assets

```powershell
python scripts/batch/upload_mrs_assets.py `
  --data-dir .\dockone-run\data `
  --bucket $env:DEPLOYMENT_OBS_BUCKET `
  --iceberg-jar $env:ICEBERG_RUNTIME_JAR
```

This uploads the Spark script, generated manifest, optional schema metadata, and Apache Iceberg Spark runtime JAR to OBS.

## 5. Run MRS processing

Preferred path: trigger the DataArts Factory MRS job:

```powershell
python scripts/dataarts/trigger_dataarts_job.py `
  --job-name dockone_obs_mrs_iceberg_golden `
  --workspace-id $env:DATAARTS_WORKSPACE_ID `
  --project-id $env:HUAWEICLOUD_PROJECT_ID `
  --summary .\dockone-run\dataarts-mrs-summary.json
```

Fallback path: submit directly to MRS if DataArts orchestration is unavailable or intentionally bypassed:

```powershell
python scripts/mrs/run_mrs_iceberg_job.py `
  --bucket $env:DEPLOYMENT_OBS_BUCKET `
  --cluster-id $env:DEPLOYMENT_MRS_CLUSTER_ID `
  --project-id $env:HUAWEICLOUD_PROJECT_ID `
  --summary .\dockone-run\mrs-iceberg-job-summary.json
```

Expected OBS outputs:

```text
lake/iceberg/dockone/
publish/dockone_table_metrics/current/
```

## 6. Load Golden data into DWS

Download the Golden CSV:

```powershell
python scripts/dws/download_golden_csv.py `
  --bucket $env:DEPLOYMENT_OBS_BUCKET `
  --out .\dockone-run\runtime\dockone_table_metrics.csv
```

Load or refresh DWS:

```powershell
python scripts/dws/load_dws_table_metrics.py --csv .\dockone-run\runtime\dockone_table_metrics.csv
```

If the final DWS publication is scheduled in DataArts, trigger it after the MRS stage:

```powershell
python scripts/dataarts/trigger_dataarts_job.py `
  --job-name dockone_golden_to_dws `
  --workspace-id $env:DATAARTS_WORKSPACE_ID `
  --project-id $env:HUAWEICLOUD_PROJECT_ID `
  --summary .\dockone-run\dataarts-dws-summary.json
```

Current-state caveat: the last observed `dockone_golden_to_dws` instance had failed, while direct DWS loading was validated. Re-check DataArts before claiming DataArts-only DWS success.

## 7. Query DWS

Default validation query:

```powershell
python scripts/dws/query_dws.py
```

Custom read-only query:

```powershell
python scripts/dws/query_dws.py --sql "SELECT domain, COUNT(*) FROM dockone_golden.table_metrics_bi GROUP BY domain ORDER BY 1"
```

Use `references/dws_queries.sql` for more BI and warehouse validation examples.

## 8. One-shot wrapper

For a full end-to-end run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_full_pipeline.ps1 -TargetMiB 50
```

Use direct MRS submission only when requested or when DataArts is unavailable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/orchestration/run_full_pipeline.ps1 -TargetMiB 50 -DirectMrsSubmit
```

Useful flags:

- `-SkipDwsLoad`: run lake processing but skip local DWS loading.
- `-SkipQuery`: skip the final DWS query.
- `-RunDir <path>`: place generated data and summaries somewhere specific.

## Validation checkpoints

Check these before reporting success:

1. Generated run manifest exists under `.\dockone-run\data\manifest.json`.
2. OBS contains JSONL files under `raw/dockone_exampleapp/`.
3. MRS/DataArts job completes and writes Iceberg metadata under `lake/iceberg/dockone/`.
4. Golden CSV exists under `publish/dockone_table_metrics/current/`.
5. DWS schema `dockone_golden` contains `table_metrics_stage`, `table_metrics`, and `table_metrics_bi`.
6. `scripts/dws/query_dws.py` returns nonzero rows.
7. Monitor API/site does not include CDM or RDS in the batch topology.

## Troubleshooting notes

- If DWS reports account locked or invalid password, stop and reconcile the local DWS secret and ECS monitor environment. Do not print the password while debugging.
- If a DataArts job cannot be found, confirm workspace ID, project ID, and job name. Direct MRS submission is an acceptable fallback only when the user agrees or the task allows bypassing DataArts.
- If Iceberg classes are missing, upload the correct `iceberg-spark-runtime` JAR and pass its OBS object name to the MRS job.
- If the user asks about the S3/OMS portion, read `references/architecture_current_state.md`; OMS was not confirmed in the latest live resource check.
- The monitor site currently uses HTTP unless TLS was configured separately.
