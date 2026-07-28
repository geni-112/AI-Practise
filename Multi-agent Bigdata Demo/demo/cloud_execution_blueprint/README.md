# Cloud Execution Blueprint

This folder is the handoff layer between the local SAT Agentic POC and a future Huawei Cloud execution environment.

It is intentionally non-executing:

- It does not create OBS, MRS, DWS, DataArts, IAM, KMS, VPC, or subnet resources.
- It does not submit Spark jobs or import DataArts jobs.
- It does not store AK/SK, passwords, private keys, or database credentials.
- It assumes cloud execution stays blocked until a human operator approves a separate deployment window.

## Current Verified Run

The current local run used by these docs is:

```text
front-11ed357b8f
```

The upstream local gates are expected to be:

- MaaS reliability judge passed.
- Business contract freeze passed.
- Local execution sandbox passed.
- Cloud import dry-run handoff passed.
- `cloud_execution` remains `blocked`.

## Folder Contents

- `huawei_cloud_execution_blueprint.md`: target Huawei Cloud architecture and handoff boundary.
- `operator_runbook.md`: step-by-step operator process before real execution.
- `execution_contract.yaml`: machine-readable cloud execution contract template.
- `terraform/`: resource-free Terraform scaffold for parameters, outputs, and future IaC extension.
- `scripts/validate_pre_execution_package.ps1`: local validator for a generated run package.
- `scripts/render_operator_handoff.ps1`: local handoff renderer for a generated run package.

## Local Validation

Run from `frontend-min`:

```powershell
.\cloud_execution_blueprint\scripts\validate_pre_execution_package.ps1 -RunId front-11ed357b8f
.\cloud_execution_blueprint\scripts\render_operator_handoff.ps1 -RunId front-11ed357b8f
```

The scripts write local review output to:

```text
cloud_execution_blueprint/out/<run_id>/
```

## Required Live Console Confirmations

Before any real cloud deployment, an operator must confirm:

- Huawei Cloud region and project id.
- OBS bucket name, encryption policy, lifecycle policy, and layer paths.
- VPC, private subnet, security groups, and private connectivity between DataArts, MRS, DWS, and OBS.
- MRS Spark cluster id or approved cluster creation plan.
- DWS connection name and serving schema.
- DataArts workspace id and import permissions.
- IAM least-privilege roles and KMS/DEW key id.
- Quotas, exact flavor availability, and pay-per-use cost in the selected region.
