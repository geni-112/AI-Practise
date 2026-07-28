# Operator Runbook

## Phase 0: Local Package Validation

Run:

```powershell
.\cloud_execution_blueprint\scripts\validate_pre_execution_package.ps1 -RunId front-11ed357b8f
```

Expected result:

- Validation status is `passed`.
- `ready_for_execution_layer` is `true`.
- `cloud_execution` is still `blocked`.
- Release package and pre-execution evidence files are present.

## Phase 1: Cloud Resource Binding Review

Bind placeholders from `generated/<run_id>/release/cloud_parameter_map.json` to approved cloud resources:

- `HUAWEICLOUD_REGION`
- `HUAWEICLOUD_PROJECT_ID`
- `VPC_ID`
- `PRIVATE_SUBNET_ID`
- `KMS_KEY_ID`
- `MRS_CLUSTER_ID`
- `DATAARTS_WORKSPACE_ID`
- `DWS_CONNECTION_NAME`
- OBS raw, silver, gold, release, and audit URIs

Do not write credentials into the release package.

## Phase 2: OBS Release Staging

Upload the frozen release bundle to:

```text
obs://<approved_bucket>/release/<run_id>/
```

Required contents:

- Release manifest.
- DataArts import package.
- Resolved import preview.
- PySpark artifact.
- SQL artifact.
- DAG artifact.
- Quality rules.
- Security review.
- Lineage evidence.
- Pre-execution readiness report.

## Phase 3: DataArts Import Review

Import the DataArts package into the approved workspace as a review-only draft:

- Keep all schedules disabled.
- Verify MRS cluster reference.
- Verify OBS raw/silver/gold/release/audit paths.
- Verify DWS connection name.
- Verify retry policy and failure handling.
- Verify that production execution remains manually blocked.

## Phase 4: MRS and DWS Execution Approval

Only after a separate operator approval:

- Enable the reviewed DataArts job or submit the reviewed MRS Spark job.
- Capture MRS application id and logs.
- Validate silver and gold row counts.
- Load reviewed gold aggregates into DWS.
- Validate DWS table counts and schema.
- Write execution evidence to OBS audit.

## Phase 5: Rollback

If validation fails:

- Disable DataArts schedule immediately.
- Stop or cancel running MRS job if safe to do so.
- Keep failed output under an isolated audit prefix.
- Restore previous DWS serving view or schema pointer.
- Preserve release package and execution logs for review.
