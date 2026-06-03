# Huawei Cloud Chile Demo Deployment Status

Date: 2026-06-02
Region: `la-south-2` (Chile LA-Santiago)
Project name: `la-south-2`

## Completed

- Local DPAPI credential skill was found and used:
  - `%LOCALAPPDATA%\Codex\huawei-cloud-bigdata\credentials.xml`
- AK/SK authentication succeeded for IAM project discovery.
- Existing OBS bucket found in Chile:
  - `ai-hw-site-9347`
- Demo assets were uploaded to the existing OBS bucket:
  - `obs://ai-hw-site-9347/jobs/dli/bronze_hudi_job.py`
  - `obs://ai-hw-site-9347/jobs/dli/silver_hudi_job.py`
  - `obs://ai-hw-site-9347/jobs/dli/load_silver_to_dws_job.py`
  - 21 raw CDC JSON files under `obs://ai-hw-site-9347/raw/dockone_exampleapp/...`
  - schema files under `obs://ai-hw-site-9347/schema/`
- OBS object metadata was verified for representative files with HTTP status `200`.

## Blocked

- Creating a new OBS bucket was blocked by Huawei Cloud with:
  - `UserRestricted`
  - Meaning: the current user/AK is restricted from creating buckets.
- Creating the minimal DLI 16CU general queue was blocked by Huawei Cloud with:
  - `DLI.0001`
  - Message: `The queue is sold out and cannot be purchased.`
- Submitting a Spark smoke job to the existing DLI `default` queue was blocked by IAM/DLI authorization:
  - `DLI.0003`
  - Meaning: the current principal lacks `SUBMIT_JOB` permission on `queues.default`.

## Current Usable State

The OBS-side data lake assets are ready in Chile. DLI execution is not yet available because the account cannot create a queue in the region and cannot submit jobs to the existing `default` queue.

## Resume Command

After DLI queue capacity or permissions are fixed, rerun:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\12_resume_existing_bucket_smoke.ps1 -Bucket ai-hw-site-9347 -Queue <dli-queue-name> -Execute -SmokeTables 1
```

If using the existing `default` queue, the account needs `SUBMIT_JOB` permission on `queues.default`.
