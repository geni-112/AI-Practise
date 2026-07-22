# Security And Operations

## Security Model

Assume generated artifacts are untrusted, users can request unsafe operations, model output can be structurally valid but semantically wrong, and cloud credentials can cause material cost or data exposure.

Apply controls at four boundaries:

1. Input boundary: classify and redact prompt/data context.
2. Generation boundary: validate schema, code, paths, and policy.
3. Release boundary: require reviews, hashes, and explicit approval.
4. Execution boundary: use least-privilege identities, read-only probes, and immutable packages.

## Credential Handling

- Accept secrets from workload identity, instance agency, DEW, a protected CLI profile, or process environment.
- Never embed secrets in `SKILL.md`, source code, templates, artifacts, screenshots, shell history, URLs, or Git.
- Keep service environment files outside the application directory with owner-only permissions such as mode `600` on Linux.
- Limit remote MaaS environment files to the minimum required variables.
- Remove temporary credential bootstrap files immediately after use.
- Redact authorization headers, access keys, tokens, passwords, private-key paths, and signed URLs from logs.
- Fail closed when a required credential is missing; do not substitute a different account silently.

For a systemd-hosted POC, prefer an external environment file referenced by the service unit. Verify ownership and permissions, restart the service, and test configuration without printing values.

## Data Protection

- Do not send raw direct identifiers, credentials, unrestricted samples, or regulated payloads to MaaS.
- Build model context from schema, classifications, allowed fields, masked examples, distributions, and business rules.
- Hash identifiers only when the salt/key lifecycle and re-identification risk are understood.
- Separate local synthetic samples from cloud production paths.
- Scan browser/API responses so direct identifiers cannot appear in previews.
- Keep source-level authorization checks in the execution plane; a prompt cannot grant access.
- Treat model instructions embedded in user prompts, schema descriptions, and catalog labels as untrusted data.
- Validate model-produced query intent against a versioned semantic catalog before compiling any query.
- Keep user-provided values in bound parameters; never interpolate them into SQL text.
- Reject non-read-only operations and identifiers outside the catalog even when the model requests them.

## Authorization Roles

Separate these capabilities where possible:

| Role | Allowed operations |
|---|---|
| App runtime | Read templates, write draft artifacts, call approved MaaS endpoint |
| Cloud probe | List/get approved resource metadata only |
| Artifact reviewer | Approve or reject named hashes |
| Release manager | Freeze approved package and bind resources |
| Execution role | Submit approved MRS/DataArts jobs and write approved OBS prefixes |
| Operator | View jobs, logs, alerts, and evidence |

Do not give the chat-facing application unrestricted resource-creation or account-administration permissions.

## Cloud Probe Semantics

A cloud probe is read-only. Use it to verify:

- endpoint/network reachability;
- authentication and project scope;
- existence and state of named resources;
- permission to read required metadata;
- OBS prefix visibility;
- MRS/DataArts/DWS binding compatibility.

The probe must not create, resize, start, stop, delete, schedule, submit, or modify resources. Display `Probe successful` instead of `Cloud ready to execute` unless all release and execution gates also pass.

## MaaS Deployment Verification

After configuring MaaS in a deployed environment:

1. Verify the application health endpoint reports configuration presence without revealing values.
2. Call a dedicated MaaS test endpoint with a small non-sensitive request.
3. Confirm the response came from the configured model, not the local fallback.
4. Run one full test case with `use_maas=true`.
5. Confirm run evidence records `maas.requested=true` and `maas.used=true`.
6. Confirm templates and synthetic fixtures are present in the deployed package or object location.
7. Verify secrets are absent from the deployment archive, web root, logs, and generated artifacts.

Treat a healthy UI or configured checkbox as insufficient evidence of MaaS use.

## Deployment Sequence

1. Build an application archive that excludes credentials, local virtual environments, caches, and generated production evidence.
2. Validate templates, schemas, static assets, and API tests locally.
3. Upload through a controlled channel and verify checksum.
4. Install into a versioned release directory.
5. Configure external secrets and service identity.
6. Point a stable service link to the versioned release.
7. Restart and verify health.
8. Test MaaS and local fallback separately.
9. Test read-only cloud probes.
10. Run a synthetic end-to-end case with cloud execution disabled.
11. Enable execution only after approvals, cost boundaries, and rollback are confirmed.

## Operational Evidence

Capture:

- run and correlation IDs;
- graph node start/end times and outcomes;
- MaaS requested/used/model/error metadata;
- artifact hashes and reviewer decisions;
- cloud probe results;
- job submission IDs and terminal states;
- input/output row counts and quality metrics;
- Gold object/table locations;
- security and lineage result versions.

Avoid logging full prompts or generated code by default when they can contain sensitive context. Store protected artifacts in an access-controlled evidence location.

## Failure And Recovery

- Retry MaaS timeouts and rate limits with bounded exponential backoff and jitter.
- Do not retry deterministic schema or policy failures without changing input.
- Make MRS and DataArts submissions idempotent by release ID where supported.
- Preserve failed run evidence before retry.
- Require a new release hash when code or bindings change.
- Keep the previous deployed application release for rollback.
- Never roll back data blindly; use versioned outputs and documented recovery procedures.
- Return a safe clarification when semantic parsing fails; do not expose provider errors, stack traces, prompts, or credentials to the browser.
- Preserve the original user prompt and offer retry or return-to-input actions after workflow failures.

## Cost And Lifecycle Controls

- Tag POC resources with owner, purpose, environment, creation date, and expiry.
- Define budgets and alerts before long-running clusters are enabled.
- Prefer reuse of approved resources for validation.
- Stop or delete temporary compute according to the approved lifecycle plan.
- Expire temporary OBS prefixes while retaining required audit evidence.
- Reconfirm user approval when resource shape, count, region, or expected lifetime increases.

## Repository Scan

Before publication, scan for:

- access/secret keys and token-shaped values;
- passwords and private keys;
- public IPs, live resource IDs, account/project IDs, and bucket names that should stay private;
- `.env` files and service environment files;
- generated customer data and execution logs;
- signed URLs and authorization headers.

Keep reusable examples symbolic. Put environment-specific inventory in a protected operational repository or secrets/configuration system.
