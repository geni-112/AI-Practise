# Notebook Trigger Workflow

This demo uses the notebook as the automation trigger and keeps execution logic in reusable scripts.

## Trigger

- Notebook: `notebooks/dli_hudi_demo.ipynb`
- Auto runner: `notebooks/run_notebook_auto.py`
- PowerShell entrypoint: `scripts/15_run_notebook_auto.ps1`

## Automated Flow

1. Select Huawei Cloud auth.
   - Prefer local AK/SK if available.
   - Use fallback IAM token when `-ForceFallbackAuth` is passed by the notebook.
   - Convert IAM token to temporary AK/SK for OBS operations.
2. Ensure OBS bucket.
   - Target default: `docktest`.
   - Create it if it does not exist.
3. Upload platform assets to OBS.
   - Python Spark jobs under `obs://docktest/jobs/dli/`.
   - DLI SQL scripts under `obs://docktest/jobs/sql/`.
   - Raw CDC data under `obs://docktest/raw/`.
   - Schema files under `obs://docktest/schema/`.
4. Generate DLI Spark payloads.
5. Run one or more table workflows:
   - Submit bronze Spark job.
   - Poll until bronze succeeds.
   - Submit silver Spark job.
   - Poll until silver succeeds.
   - Submit SQL table discovery.
   - Submit SQL row-count validation.
   - Persist run summary to `runtime/notebook-dataflow-run-summary.json`.

## Dry Run

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Bucket docktest -Queue <dli-queue> -SmokeTables 1 -DryRun
```

## Execute

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Bucket docktest -Queue <dli-queue> -SmokeTables 1
```

## Notes

- DLI Spark jobs are created by API submission. They do not need to exist in the console before running.
- SQL jobs are also created by API submission.
- The queue must allow both Spark job submission and SQL validation. If a region separates Spark and SQL queues, use a queue compatible with the selected stage or split queue settings in the orchestrator.
