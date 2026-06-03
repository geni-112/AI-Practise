# Chile Minimal Deployment

This demo is pinned to Huawei Cloud LA-Santiago, region id `la-south-2`.

## Minimal scope

The deployment script creates only:

- One OBS bucket for raw CDC data, Hudi tables, checkpoints, schemas, and DLI packages.
- One DLI general queue for Spark jobs.

It does not automatically create CCE/JupyterHub, DWS, CDM, or MRS. Those are optional and should be created only after the raw -> bronze -> silver Hudi path is validated.

## Required environment variables

Set these in PowerShell. Do not write secrets into files.

```powershell
$env:HUAWEICLOUD_REGION="la-south-2"
$env:HUAWEICLOUD_PROJECT_ID="<project-id>"
$env:DEMO_BUCKET="dockone-dli-hudi-demo-<unique-suffix>"
$env:OBS_ENDPOINT="https://obs.la-south-2.myhuaweicloud.com"
$env:DLI_ENDPOINT="https://dli.la-south-2.myhuaweicloud.com"
$env:DLI_QUEUE_NAME="dli_demo_min"
$env:DLI_SPARK_VERSION="3.3.1"
$env:DLI_AGENCY_URN="<dli-agency-name-or-urn>"
$env:HUAWEICLOUD_ACCESS_KEY="<set-in-shell-only>"
$env:HUAWEICLOUD_SECRET_KEY="<set-in-shell-only>"
$env:HUAWEICLOUD_X_AUTH_TOKEN="<temporary-token>"
```

## Dry run

```powershell
cd outputs\huawei-dli-hudi-demo
powershell -ExecutionPolicy Bypass -File scripts\08_deploy_chile_minimal.ps1
```

## Execute a one-table smoke deployment

```powershell
cd outputs\huawei-dli-hudi-demo
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\08_deploy_chile_minimal.ps1 -Execute -SmokeTables 1
```

Increase `-SmokeTables` only after the first table succeeds.

## References

- DLI is serverless and compatible with Spark/Flink/HetuEngine.
- DLI queue creation uses `POST /v1.0/{project_id}/queues`; the documented minimum queue size is 16 CUs.
- DLI Spark job submission uses `POST /v2.0/{project_id}/batches`.
- DLI Spark job status uses `GET /v2.0/{project_id}/batches/{batch_id}/state`.
- OBS endpoints must match the bucket region.
