# GitHub-Friendly Agent-Neutral Huawei MRS Hudi Demo Package

This package lets any capable coding/cloud agent reproduce the Databricks CDC/Delta to Huawei Cloud MRS + OBS + Apache Hudi smoke demo.

It is not tied to Codex skills, Claude, or any single agent runtime.

## Scope

- Source pattern: Databricks raw CDC -> bronze -> silver.
- Huawei target: OBS + MRS Spark + Apache Hudi.
- Stable region: Chile / `la-south-2`.
- Smoke table: `dockone_exampleapp_payment_outbox`.
- Data: synthetic CDC JSON for 21 inferred tables.
- Notebook role: automated trigger/orchestrator that calls scripts and waits for results.

## Contents

- `demo/`: executable demo scripts, configs, notebooks, PySpark jobs, SQL, docs.
- `data/raw/`: 21-table synthetic CDC JSON with short flat filenames.
- `data/raw-map.json`: maps short local raw files back to the original OBS CDC keys.
- `data/schema/`: inferred schemas and DDL.
- `automation/`: agent-neutral PowerShell wrappers for auth, validation, smoke runs, cluster checks, cleanup, and Sao Paulo diagnosis.
- `env/agent.env.example.ps1`: environment variable template, with no secrets filled in.
- `AGENT_RUNBOOK.md`: detailed operating guide for any agent.
- `SECURITY.md`: rules for credentials and logs.
- `MANIFEST.json`: machine-readable package inventory.

## Fast Start

Open PowerShell in this package directory.

Validate package:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Test-AgentPackage.ps1
```

Fetch the Apache Hudi bundle before upload/run:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Fetch-HudiBundle.ps1
```

Run against an existing Chile MRS cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-ChileMrsSmoke.ps1 `
  -Bucket docktest `
  -ClusterId <MRS_CLUSTER_ID> `
  -SmokeTables 1
```

Run notebook-triggered smoke against an existing Chile MRS cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-NotebookSmoke.ps1 `
  -Bucket docktest `
  -ClusterId <MRS_CLUSTER_ID> `
  -SmokeTables 1
```

Run transient Chile MRS smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Invoke-ChileMrsSmoke.ps1 `
  -Bucket docktest `
  -TransientCluster `
  -SmokeTables 1
```

## Required Credentials

The package does not contain credentials.

An agent/operator must provide either:

- temporary `HUAWEICLOUD_ACCESS_KEY`, `HUAWEICLOUD_SECRET_KEY`, optional `HUAWEICLOUD_SECURITY_TOKEN`, and `HUAWEICLOUD_PROJECT_ID`; or
- IAM env vars `HUAWEICLOUD_DOMAIN_NAME`, `HUAWEICLOUD_IAM_USER_NAME`, `HUAWEICLOUD_IAM_PASSWORD`; or
- on the original Windows host only, `-UseDpapiFallback` to reuse the locally encrypted credential selector.

Read `SECURITY.md` before running.

## GitHub Notes

- The package intentionally avoids the long OBS-style local raw paths.
- The package intentionally does not commit `hudi-spark3.3-bundle_2.12-0.15.0.jar`, because it is larger than GitHub's normal 100 MB file limit.
- `automation\Invoke-ChileMrsSmoke.ps1` downloads the Hudi bundle automatically if it is missing.
