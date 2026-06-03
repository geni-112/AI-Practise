# Agent Runbook

This runbook is for any Agent that can run PowerShell, Python, and Huawei Cloud SDK operations.

## Non-Negotiable Rules

- Never print, store, summarize, or commit Huawei Cloud passwords, AK/SK, security tokens, Jupyter tokens, or admin passwords.
- Do not write secrets into files inside this package.
- Start with one smoke table: `dockone_exampleapp_payment_outbox`.
- Preserve the original flow: raw CDC -> bronze Hudi -> silver Hudi.
- Keep `hoodie.datasource.hive_sync.enable=false` for the minimal PoC.
- Verify MRS cleanup after every transient/debug run.

## Environment

Minimum local runtime:

- Windows PowerShell 5+ or PowerShell 7+.
- Python 3.10+.
- Python packages from `demo/requirements.txt`.
- Network access to Huawei Cloud IAM, OBS, ECS, and MRS endpoints.

Credential options:

```powershell
# Option A: temp AK/SK/token supplied by a secret manager or operator
$env:HUAWEICLOUD_ACCESS_KEY = "<temp-ak>"
$env:HUAWEICLOUD_SECRET_KEY = "<temp-sk>"
$env:HUAWEICLOUD_SECURITY_TOKEN = "<temp-token-if-any>"
$env:HUAWEICLOUD_PROJECT_ID = "<project-id>"

# Option B: IAM password flow; avoid shell history when possible
$env:HUAWEICLOUD_DOMAIN_NAME = "<domain>"
$env:HUAWEICLOUD_IAM_USER_NAME = "<iam-user>"
$env:HUAWEICLOUD_IAM_PASSWORD = "<password>"
```

On the original Windows host only, pass `-UseDpapiFallback` to use the local encrypted credential selector.

## Package Validation

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Test-AgentPackage.ps1
```

Expected:

- Demo package has 21 table configs.
- `scripts/18_run_mrs_dataflow_workflow.py` compiles.
- Smoke raw CDC file exists.
- Hudi bundle may be absent in the GitHub package by design.

Fetch the Hudi bundle before cloud upload/run:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Fetch-HudiBundle.ps1
```

## Chile Stable MRS Smoke

This is the known-good path.

Existing cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-ChileMrsSmoke.ps1 `
  -Bucket docktest `
  -ClusterId <MRS_CLUSTER_ID> `
  -SmokeTables 1
```

Transient cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-ChileMrsSmoke.ps1 `
  -Bucket docktest `
  -TransientCluster `
  -SmokeTables 1
```

What this does:

1. Authenticates to `la-south-2`.
2. Validates the demo package.
3. Packages Spark jobs.
4. Downloads the Hudi bundle if missing.
5. Ensures OBS bucket exists.
6. Uploads scripts, SQL, full synthetic CDC data, schemas, and Hudi bundle.
7. Runs bronze and silver MRS Spark jobs.
8. Waits for success.

Expected MRS results:

- `bronze-dockone_exampleapp_payment_outbox`: `FINISHED` / `SUCCEEDED`.
- `silver-dockone_exampleapp_payment_outbox`: `FINISHED` / `SUCCEEDED`.

Expected OBS prefixes:

- `obs://docktest/lake/bronze/payment/outbox/`
- `obs://docktest/lake/silver/payment/outbox/`

## Notebook Trigger Smoke

Existing cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-NotebookSmoke.ps1 `
  -Bucket docktest `
  -ClusterId <MRS_CLUSTER_ID> `
  -SmokeTables 1
```

Transient cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-NotebookSmoke.ps1 `
  -Bucket docktest `
  -TransientCluster `
  -SmokeTables 1
```

Expected notebook result:

- cells executed: `2, 3, 4, 5, 7, 9` on Windows runner.
- `failures: []`.
- bronze and silver jobs succeed.

The notebook is an orchestrator. It is not only documentation.

## MRS Cluster Check And Cleanup

Check a cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Check-MrsCluster.ps1 `
  -ClusterId <MRS_CLUSTER_ID> `
  -Region la-south-2
```

Delete a debug cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Remove-MrsCluster.ps1 `
  -ClusterId <MRS_CLUSTER_ID> `
  -Region la-south-2
```

After deletion, call `Check-MrsCluster.ps1` until state is `terminated`.

## Known Chile MRS Timing Issue

MRS can report `running` before JobGateway is ready. Also, the first run-job-flow bronze step may already exist while explicit submission starts.

Do not remove the following behaviors from `scripts/18_run_mrs_dataflow_workflow.py`:

- same-name job adoption.
- submit retry while JobGateway warms up.
- waiting for an existing first bronze job.
- MRS job-list offset starts at `1`.

## Sao Paulo Diagnostic

Sao Paulo was prepared but did not reach Spark/Hudi execution in the tested account.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Diagnose-SaoPauloMrs.ps1
```

Known finding from the tested account:

- Region: `sa-brazil-1`.
- MRS version: `MRS 3.5.0-LTS`.
- Smallest AZ1 MRS flavor: API metadata `m6.2xlarge.8`; create API product form `m6.2xlarge.8.linux.bigdata`.
- MRS minimum topology: 2 master + 3 core.
- Tested account ECS RAM quota: 262144 MB, below the about 327680 MB required by the minimum topology.
- Conclusion: Sao Paulo smoke was quota-blocked before script execution.

## Latest Validated Chile Results

Date: 2026-06-03.

Existing-cluster smoke on debug cluster `6edebdbe-62b1-44db-aafd-8e15e16cda79`:

- Bronze job `d960ad3c-d19b-485e-8abf-9eaf8796ed98`: `SUCCEEDED`.
- Silver job `97d7dbfe-9049-47eb-97c1-218956a32756`: `SUCCEEDED`.

Notebook-triggered existing-cluster smoke on the same cluster:

- Cells executed: `2, 3, 4, 5, 7, 9`.
- Failures: none.
- Bronze job `8595bac3-7ce7-49db-b253-2cdb23adfec3`: `SUCCEEDED`.
- Silver job `e5e1f2fd-6877-4f61-b084-612a75e3ccc7`: `SUCCEEDED`.

Cleanup:

- Cluster `6edebdbe-62b1-44db-aafd-8e15e16cda79` reached `terminated`.

## GitHub-Friendly Layout

This package is flatter than the original self-contained package.

- Local raw files are stored as `data/raw/<table_name>.json`.
- `data/raw-map.json` maps each short filename to its original OBS object key.
- `demo/scripts/02_upload_assets_to_obs.py` reads `raw-map.json` and uploads each file to the correct OBS CDC path.
- The Hudi jar is not committed; use `automation/Fetch-HudiBundle.ps1`.
