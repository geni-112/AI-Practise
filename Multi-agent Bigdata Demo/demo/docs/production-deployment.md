# Production deployment contract

This document describes the minimum deployment boundary for enabling real Huawei Cloud job
submission. The default application configuration remains read-only and generation-only.

## Components

Deploy the following as separate processes:

1. FastAPI web application behind an HTTPS reverse proxy.
2. PostgreSQL-compatible control database, preferably Huawei Cloud RDS for PostgreSQL.
3. `python -m app.execution_worker` as a private worker with no public listener.
4. Existing MRS, OBS, and DataArts resources referenced by server-managed execution profiles.

The web process creates approval and execution requests. Only the worker imports the write
adapters and submits cloud jobs.

## Identity boundary

Use one of these modes:

- `SAT_AUTH_MODE=jwt`: validate issuer, audience, algorithm, and either a JWKS URL or public
  verification key.
- `SAT_AUTH_MODE=trusted_header`: the reverse proxy must remove all inbound copies of
  `X-SAT-User` and `X-SAT-Roles`, authenticate the user, then inject trusted values.

Never expose trusted-header mode without that proxy behavior. Assign only the required roles:

- `artifact_reviewer`: approve or reject generated artifacts.
- `release_manager`: create an immutable release and request execution.
- `cloud_operator`: approve or cancel execution.
- `auditor`: read production status and evidence.
- `developer`: create local generation runs.

The request creator cannot approve the same execution request.

## Database

Set `SAT_DATABASE_URL` to a private PostgreSQL connection string supplied by the runtime secret
service. Do not put it in source control or an execution profile. Restrict database access to
the web and worker security groups, enable TLS, backups, and audit retention.

SQLite is for local testing only. SQLAlchemy creates the current schema on startup; controlled
production upgrades should replace this convenience behavior with an approved migration step
before deploying a newer application version.

## Cloud identity and secrets

Use a Huawei Cloud agency or workload identity where available. The SDK default credential
provider chain is used by the worker. Do not place AK, SK, passwords, security tokens, private
keys, or authorization headers in:

- `SAT_EXECUTION_PROFILES_JSON`;
- the control database;
- source files, screenshots, logs, or task notes.

The API rejects secret-like execution parameter keys and private-key material.

## Required environment

```text
SAT_PRODUCTION_MODE=true
SAT_AUTH_MODE=jwt
SAT_DATABASE_URL=<runtime secret>
SAT_CLOUD_EXECUTION_ENABLED=true
SAT_REQUIRE_REAL_CLOUD_PROBE=true
SAT_REQUIRE_EXECUTION_PROFILE=true
SAT_ALLOWED_EXECUTION_TARGETS=mrs,dataarts
SAT_EXECUTION_PROFILES_JSON=<server-managed JSON>
SAT_ALLOWED_MRS_CLUSTER_IDS=<comma-separated identifiers>
SAT_ALLOWED_DATAARTS_WORKSPACE_IDS=<comma-separated identifiers>
SAT_ALLOWED_DATAARTS_JOB_NAMES=<comma-separated names>
SAT_ALLOWED_OBS_PREFIXES=<comma-separated obs:// prefixes>
```

An MRS profile contains the existing cluster identifier, Spark job parameters, and allowlisted
OBS paths. A DataArts profile contains the existing workspace identifier and job name. Profiles
are server-side configuration; the browser receives only profile ID, label, description, and
target.

## Release and execution flow

1. Generate the run and review PySpark, SQL, and DataArts DAG artifacts.
2. Persist each decision with the authenticated reviewer and exact artifact SHA-256.
3. Generate the release. The control plane recomputes the canonical release hash and rejects
   missing, rejected, or stale artifact approvals.
4. Run the real read-only cloud probe against the bound resources.
5. A release manager requests one server-managed execution profile with an idempotency key.
6. A different cloud operator approves it.
7. The worker claims the queued request, submits the allowlisted job, polls to a terminal state,
   and records provider evidence.

Cancellation is recorded in the audit trail. MRS cancellation is forwarded to the provider when
the job is already running. DataArts cancellation remains a recorded control-plane request and
must be handled by the corresponding operational runbook.

## Network exposure

Bind the application service to a private address or `0.0.0.0` behind the reverse proxy. Permit
external access only through HTTPS, authenticated ingress, rate limits, request-size limits, and
an explicit office, VPN, or customer CIDR. Keep the worker and database private.

## Rollout checks

Before enabling `SAT_CLOUD_EXECUTION_ENABLED`:

- run the unit tests and JavaScript i18n audit;
- verify JWT or trusted-header behavior with an unauthorized request;
- verify the read-only cloud probe reports `real_cloud_verified=true`;
- verify every profile resource is within its corresponding allowlist;
- execute the `dry_run` adapter in a non-production test environment;
- confirm the worker identity has submit, read-status, and cancel permissions only;
- confirm logs and database rows contain no secrets;
- confirm timeout, cancellation, and rollback procedures with the cloud operator.
