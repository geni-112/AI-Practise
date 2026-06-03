# Cloud Environment Status - 2026-06-03

## Deployed

- OBS bucket: `docktest`
- Raw CDC data: uploaded under `obs://docktest/raw/...`
- Spark jobs: uploaded under `obs://docktest/jobs/dli/...`
- Hudi bundle: `obs://docktest/jobs/jars/hudi-spark3.3-bundle_2.12-0.15.0.jar`
- Hudi outputs from previous MRS smoke:
  - `obs://docktest/lake/bronze/payment/outbox`
  - `obs://docktest/lake/silver/payment/outbox`
- ECS cloud notebook scheduler:
  - name: `dockone-notebook-scheduler`
  - server id: `dfc96ba8-66b8-4625-b9fe-cd1e3a56292a`
  - flavor: `s6.medium.2`
  - image: Ubuntu 22.04 server 64bit
  - private IP: `192.168.0.189`
  - public IP: `159.138.119.17`
  - security group: `c8359dc9-53c5-43f8-827d-2698454ba9c1`
  - ECS agency: `dockone_mrs_ecs_agency`
  - JupyterLab: running on port `8888`
  - local Jupyter/ECS credentials: stored with Windows DPAPI at `%LOCALAPPDATA%\Codex\huawei-cloud-bigdata\cloud-notebook-credentials.xml`

## Cloud Notebook Runtime

The ECS bootstrap successfully installed:

- Python venv
- JupyterLab
- Huawei Cloud SDKs
- OBS SDK
- demo package under `/opt/dockone-demo/huawei-dli-hudi-demo`
- systemd service `dockone-jupyter.service`
- systemd service/timer `dockone-run-onboot.service` / `dockone-run-onboot.timer`

## MRS/Agency Remediation

The original ECS agency `MRS_ECS_DEFAULT_AGENCY` did not have permission to create MRS run-job-flow clusters. A dedicated demo agency was created and assigned to the ECS metadata:

- Agency: `dockone_mrs_ecs_agency`
- Bound to project `la-south-2`:
  - `MRS Administrator`
  - `Server Administrator`
  - `Tenant Guest`
  - `OBS OperateAccess`
- Bound at domain/all-projects scope for OBS:
  - `OBS Administrator`
  - `OBS OperateAccess`

The ECS instance metadata was updated in place from `MRS_ECS_DEFAULT_AGENCY` to `dockone_mrs_ecs_agency`.

## Latest Cloud Run

Cloud notebook triggered MRS execution successfully on cluster `28f0eeb6-c85c-40f6-a5fd-369988c15f66`.

- Bronze Hudi job: `FINISHED` / `SUCCEEDED`
- Silver Hudi job: `FINISHED` / `SUCCEEDED`
- Verified OBS Hudi output prefixes:
  - `obs://docktest/lake/bronze/payment/outbox/`
  - `obs://docktest/lake/silver/payment/outbox/`

The systemd run was marked failed because MRS terminated the transient cluster immediately after job completion, and the previous script treated a final single-job-status query error as fatal. `scripts/18_run_mrs_dataflow_workflow.py` now falls back to the MRS job list when single-job lookup fails after termination.

## Latest Repair Run

Permissions were re-applied idempotently for agency `dockone_mrs_ecs_agency`, and ECS metadata still points to that agency.

Smoke workflow was rerun on MRS cluster `d6927b01-318e-4b26-a601-07103a300cbe`:

- `bronze-dockone_exampleapp_payment_outbox`: `FINISHED` / `SUCCEEDED`
- `silver-dockone_exampleapp_payment_outbox`: `FINISHED` / `SUCCEEDED`
- Cluster cleanup: delete submitted and cluster reached `terminated`
- OBS Hudi output verified under:
  - `obs://docktest/lake/bronze/payment/outbox/`
  - `obs://docktest/lake/silver/payment/outbox/`

Additional workflow repair:

- `config/mrs-config.json` now uses `dockone_mrs_ecs_agency`.
- `scripts/18_run_mrs_dataflow_workflow.py` has a manual transient mode that can create a transient MRS cluster, wait for it, submit jobs explicitly, and clean up.
- In `la-south-2`, `run-job-flow` step attachment remained unreliable in testing, so the proven stable path is explicit Spark job submission against a running MRS cluster.

## Stability Repair - 2026-06-03 Later Run

The notebook/MRS controller was hardened after a transient timing issue was reproduced.

Observed issue:

- Transient cluster `6edebdbe-62b1-44db-aafd-8e15e16cda79` reached `running`, but JobGateway was not immediately ready.
- The previous manual transient logic treated the first run-job-flow bronze step as "not succeeded" and tried to resubmit bronze immediately.
- MRS returned `0173 Failed to submit the job`; cleanup was briefly rejected with `409 Tasks are being executed in the cluster`.

Fixes applied:

- `scripts/18_run_mrs_dataflow_workflow.py`
  - Adds normalized MRS job-list parsing.
  - Adopts an existing same-name job instead of blindly duplicating it.
  - Retries explicit job submission while JobGateway warms up.
  - Waits for the first run-job-flow bronze step if it is visible and still running.
- `scripts/19_resume_mrs_notebook_workflow.ps1`
  - Adds `--wait-transient --transient-submit-mode manual` for transient MRS notebook runs, so the notebook waits for actual results instead of only submitting work.

Validation after repair:

- Existing-cluster smoke on `6edebdbe-62b1-44db-aafd-8e15e16cda79`:
  - `bronze-dockone_exampleapp_payment_outbox`: `SUCCEEDED`
  - `silver-dockone_exampleapp_payment_outbox`: `SUCCEEDED`
- Notebook-triggered existing-cluster smoke on the same cluster:
  - Notebook cells executed: `2, 3, 4, 5, 7, 9`
  - Notebook failures: none
  - `bronze-dockone_exampleapp_payment_outbox`: `SUCCEEDED`
  - `silver-dockone_exampleapp_payment_outbox`: `SUCCEEDED`
- Cleanup:
  - Cluster `6edebdbe-62b1-44db-aafd-8e15e16cda79` reached `terminated`.
- Cloud notebook files synchronized through Jupyter Contents API:
  - `scripts/18_run_mrs_dataflow_workflow.py`
  - `scripts/19_resume_mrs_notebook_workflow.ps1`
  - `config/mrs-config.json`
  - `config/mrs-config-sa-brazil-1.json`

## Sao Paulo Smoke Attempt

Region `sa-brazil-1` was prepared for smoke testing with a separate OBS bucket and MRS config.

Prepared resources/configuration:

- OBS bucket: `docktest-sa-brazil-1`
- Smoke raw data uploaded:
  - `raw/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.payment.outbox/part-00001.json`
- Spark jobs and Hudi bundle uploaded:
  - `jobs/dli/bronze_hudi_job.py`
  - `jobs/dli/silver_hudi_job.py`
  - `jobs/jars/hudi-spark3.3-bundle_2.12-0.15.0.jar`
- MRS config:
  - Region: `sa-brazil-1`
  - AZ: `sa-brazil-1a`
  - VPC: `vpc-sap-sfs-test`
  - Subnet: `subnet-sap-az1`
  - Security group: `62e0ad00-94c2-477f-af08-fd536496531c`
  - Agency: `dockone_mrs_ecs_agency`

Findings:

- `MRS 3.5.0-LTS` is the only listed MRS version in `sa-brazil-1`.
- MRS flavor metadata for `sa-brazil-1a` lists `m6.2xlarge.8` as the smallest master/core flavor.
- The create API requires the product form `m6.2xlarge.8.linux.bigdata`.
- MRS 3.5.0-LTS enforces at least `2` master nodes and at least `3` core nodes.
- Current ECS memory quota in `sa-brazil-1` is `262144 MB`; used memory was `12288 MB`.
- Minimum legal MRS topology in `sa-brazil-1a` requires about `5 * 65536 MB = 327680 MB`, so creation is blocked by quota before Spark/Hudi scripts run.

Conclusion:

- Sao Paulo smoke did not reach script execution.
- The blocker is cloud quota/minimum MRS topology, not a Databricks-to-Hudi script defect.
- To run Sao Paulo MRS smoke, raise the `sa-brazil-1` ECS RAM quota above the MRS minimum, or use a region/service shape that offers smaller MRS-compatible big-data flavors.

## CDM Status

CDM is not deployable with the current tenant permissions.

Observed CDM API error:

```text
403 CDM.0070
The current tenant does not have access to any az, or an error occurred while obtaining user az permissions.
```

## DWS Status

DWS minimum node types are available in `la-south-2`, but DWS was not created yet because the cloud notebook/MRS agency permission is the first blocker for end-to-end cloud orchestration.

Small available candidates:

- `dwsx2.h.xlarge.4.c6` - 4 vCPU / 16 GB
- `dwsx3.4U16G.4DPU` - 4 vCPU / 16 GB

## Security Notes

- No Huawei Cloud long-term AK/SK or password was written into the demo package or skill.
- ECS uses agency metadata for cloud-side temporary credentials.
- Early cloud logs were cleaned after debugging to remove temporary credential traces.
