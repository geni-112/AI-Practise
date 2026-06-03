# MRS Replacement Workflow

This mode replaces DLI with Huawei Cloud MRS while keeping the original Databricks bronze/silver flow shape.

## Mapping

- Databricks `task.py --step bronze --job_id <table>`
  - MRS `SparkPython` job
  - Script: `obs://docktest/jobs/dli/bronze_hudi_job.py`
  - Output: `obs://docktest/lake/bronze/...`

- Databricks `task.py --step silver --job_id <table>`
  - MRS `SparkPython` job
  - Script: `obs://docktest/jobs/dli/silver_hudi_job.py`
  - Output: `obs://docktest/lake/silver/...`

SQL validation remains an extra verification stage, not a replacement for the original bronze/silver flow.

## Existing Cluster

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Engine mrs -Bucket docktest -MrsClusterId <mrs-cluster-id> -SmokeTables 1
```

## Transient Cluster

Creates an MRS cluster, submits the workflow steps, and configures the cluster to terminate after the steps finish.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\15_run_notebook_auto.ps1 -Engine mrs -Bucket docktest -TransientMrsCluster -SmokeTables 1
```

The transient cluster config is in `config/mrs-config.json`, derived from the previously detected `mrs-demo-clarovtr` cluster network and MRS 3.5.0-LTS/Spark 3.3.1 component set.
