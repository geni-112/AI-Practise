# Latest Deployment Status

Date: 2026-06-02
Region: `la-south-2`
Authentication: fallback IAM token

## Completed

- Notebook automation trigger is implemented.
- Fallback IAM login succeeded.
- IAM token was exchanged for temporary AK/SK for OBS operations.
- OBS bucket `docktest` was created successfully.
- DLI elastic resource pool was created successfully:
  - `dli_pool_demo_basic`
  - min CU: `16`
  - max CU: `64`
  - status: `AVAILABLE`
- DLI general queue was created in the elastic resource pool:
  - `dli_demo_pool_q`
  - queue CU: `16`
- Platform scripts were uploaded:
  - `obs://docktest/jobs/dli/bronze_hudi_job.py`
  - `obs://docktest/jobs/dli/silver_hudi_job.py`
  - `obs://docktest/jobs/dli/load_silver_to_dws_job.py`
- SQL validation scripts were uploaded:
  - `obs://docktest/jobs/sql/00_show_silver_table.sql`
  - `obs://docktest/jobs/sql/01_validate_silver_table.sql`
- 21 raw CDC JSON datasets were uploaded under:
  - `obs://docktest/raw/dockone_exampleapp/...`
- Schema files were uploaded under:
  - `obs://docktest/schema/`

## Databricks Flow Replacement

The replacement keeps the original Databricks shape:

- Original `task.py --step bronze --job_id <table>`:
  - Replaced by DLI Spark Python job `bronze_hudi_job.py`.
  - Reads raw CDC JSON envelope.
  - Writes Hudi bronze table to OBS.
- Original `task.py --step silver --job_id <table>`:
  - Replaced by DLI Spark Python job `silver_hudi_job.py`.
  - Reads bronze Hudi table.
  - Applies CDC merge semantics by `id` and `_cdc_timestamp`.
  - Writes Hudi silver table to OBS.
- Additional notebook-triggered SQL validation:
  - Runs after silver succeeds.
  - Does not replace the original flow; it validates the result.

## Current Blocker

DLI Spark execution is now blocked only by the required custom agency:

- Traditional DLI general queues were attempted at all valid Chile CU counts:
  - `16`, `64`, `256`, `512`
  - all returned `DLI.0001 The queue is sold out and cannot be purchased.`
- Elastic resource pool path succeeded:
  - resource pool `dli_pool_demo_basic`
  - queue `dli_demo_pool_q`
- Spark 3.3.1 job submission on `dli_demo_pool_q` requires a custom cloud service agency.
- DLI default agencies are rejected for Spark 3.3.1 jobs:
  - `dli_admin_agency`
  - `dli_management_agency`
  - `dli_data_clean_agency`
- Tested common custom agency names, but none exists in this account:
  - `dli_obs_agency_access`
  - `dli_ac_obs`
  - `dli_obs_agency`
  - `obs_dli_agency`
  - `dli_agency_obs`
  - `dli_obs_access`
- Current IAM user cannot list or manage IAM agencies:
  - Agency list API returned `403 Forbidden`.

Huawei Cloud documentation says Spark 3.3.1 general-queue jobs must use a custom DLI agency, and the agency must be created by the tenant account or an admin user.

## Resume Command After Queue Is Ready

After creating a custom DLI agency that can read/write OBS, rerun:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Bucket docktest -Queue dli_demo_pool_q -AgencyName <custom-dli-obs-agency-name> -SmokeTables 1
```

For full 1:1 table execution after the smoke run succeeds:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Bucket docktest -Queue dli_demo_pool_q -AgencyName <custom-dli-obs-agency-name> -SmokeTables 0
```

## Required Custom Agency

Create a cloud service agency in IAM:

- Agency name example: `dli_obs_agency_access`
- Agency type: Cloud service
- Cloud service: Data Lake Insight (DLI)
- Validity: Unlimited
- Scope for OBS policy: Global services
- Permission policy: allow DLI Spark jobs to read/write bucket `docktest`.

The OBS policy must include at least:

- `obs:bucket:HeadBucket`
- `obs:bucket:ListBucket`
- `obs:bucket:GetBucketLocation`
- `obs:object:GetObject`
- `obs:object:PutObject`
- `obs:object:DeleteObject`
- `obs:bucket:ListAllMyBuckets`
