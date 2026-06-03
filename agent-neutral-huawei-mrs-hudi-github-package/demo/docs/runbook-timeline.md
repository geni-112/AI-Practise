# Runbook Timeline

## T-7 days: Resource and compatibility confirmation

- Confirm service availability in the selected Huawei Cloud region.
- Confirm minimum DLI queue/resource pool shape and quota.
- Confirm OBS bucket naming, lifecycle, VPCEP, IAM agency, and DEW encryption.
- Confirm DLI Spark version and Hudi bundle compatibility.
- Confirm whether DWS and CCE/JupyterHub are required for this POC stage.

## T-1 day: Packaging and upload

- Run `scripts/00_validate_prereqs.ps1`.
- Run `scripts/01_package_jobs.ps1`.
- Run `scripts/02_upload_assets_to_obs.py --dry-run`, then `--execute` after credentials and OBS endpoint are approved.
- Run `scripts/03_build_dli_payloads.py`.
- Run `notebooks/validate_notebook_execution.py` and record success rate.

## T0: Raw to bronze

- Submit all bronze DLI Spark jobs.
- Each job reads CDC JSON from OBS raw, projects `after.*` or delete `before.*`, and writes bronze Hudi.
- Success gate: all bronze jobs reach DLI state `Success`; no missing `id` or `_cdc_timestamp`.

## T0: Bronze to silver

- Submit silver jobs only after corresponding bronze job succeeds.
- Each job deduplicates by `id`, orders by `_cdc_timestamp`, then writes Hudi upserts and Hudi deletes separately.
- Success gate: Hudi silver tables contain latest non-deleted records, and delete envelopes are not retained as ordinary rows.

## T0+1 hour: Observability and report

- Poll DLI states and logs.
- Capture Hudi commit timeline paths.
- Compare raw event counts, bronze row counts, silver upsert/delete counts.
- Record notebook execution success rate.
