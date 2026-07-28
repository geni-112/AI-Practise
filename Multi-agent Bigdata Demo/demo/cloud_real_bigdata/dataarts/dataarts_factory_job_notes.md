# DataArts Factory Job Notes

Terraform can define `huaweicloud_dataarts_factory_job`, but previous runs have seen service-side `DLF.3051` failures when creating Factory jobs through API.

Use this sequence:

1. Create VPC, subnet, security group, OBS, MRS, and optional DWS through Terraform.
2. Create or reuse the DataArts Studio instance and workspace.
3. Import the reviewed DAG only after PySpark, SQL, quality, and security review are approved.
4. Keep schedules disabled until the operator explicitly starts the run.
5. If the API path fails with `DLF.3051`, create the Factory job in the logged-in Huawei Cloud console:
   - Batch job.
   - Node type: MRS Spark Python.
   - Cluster: the Terraform-created MRS cluster.
   - Script type: Offline.
   - Script path: `obs://<bucket>/scripts/sat_taxpayer_etl.py`.
   - Arguments:

```text
--raw-path
obs://<bucket>/raw/sat/<run_id>/taxpayer_registry.csv
--gold-path
obs://<bucket>/gold/sat/<run_id>/taxpayer_gold_csv
--audit-path
obs://<bucket>/audit/<run_id>/mrs_audit.json
--year
2025
```

Do not inspect or export browser cookies, local storage, saved passwords, or session files.
