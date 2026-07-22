# Acceptance Checklist

Use this checklist before calling a local build, cloud deployment, or customer handoff complete.

## Product Flow

- [ ] The initial viewport contains a clear chat composer and no mandatory configuration form.
- [ ] A user can submit a free-form business request without selecting a template.
- [ ] Templates and MaaS settings are available under a collapsed advanced control.
- [ ] Submission creates a durable run ID and switches to a progress view.
- [ ] Progress reflects actual backend stages rather than a timer animation.
- [ ] Each step exposes understandable input, output, status, duration, and error details.
- [ ] Completion opens a detailed results workbench instead of appending an oversized chat message.
- [ ] Results include Overview, Workflow, Artifacts, Data, Governance, and Cloud categories.
- [ ] A user can start a new task without losing access to completed run evidence.

## Agent And Artifact Behavior

- [ ] Data context is prepared before contract generation.
- [ ] The business contract validates against the packaged schema.
- [ ] Assumptions and unresolved questions are explicit.
- [ ] PySpark, SQL, and DataArts DAG files are separate and individually reviewable.
- [ ] Quality, security, and lineage outputs exist as structured evidence.
- [ ] Artifacts are written to a unique run directory or object prefix.
- [ ] Local validation and metric reconciliation run before release.
- [ ] Editing an approved artifact invalidates its approval.
- [ ] Release manifests contain hashes for every executable artifact.
- [ ] The executed package matches the released hashes.

## MaaS And Fallback

- [ ] The MaaS configuration test makes a real non-sensitive model call.
- [ ] Timeout, rate-limit, invalid-output, and unavailable-endpoint cases are handled.
- [ ] Local fallback remains usable when policy permits.
- [ ] Runtime evidence distinguishes `requested`, `configured`, and `used`.
- [ ] The UI never labels fallback content as MaaS-generated.
- [ ] Raw direct identifiers are absent from MaaS requests, logs, and responses.

## ChatBI Semantic Query

- [ ] Free-form paraphrases work without requiring a predefined prompt.
- [ ] Known expressions can use a deterministic fast path.
- [ ] Unfamiliar expressions use MaaS only when runtime evidence confirms the call.
- [ ] The model receives a semantic catalog and validated history, not raw Gold rows.
- [ ] Dimensions, metrics, filters, and limits are validated against the catalog.
- [ ] User values remain bound parameters and never enter SQL text directly.
- [ ] Compiled queries are read-only and expose their catalog version in evidence.
- [ ] Follow-up questions use only previously validated query contracts.
- [ ] Unknown values and model failures return a clarification instead of an execution error.
- [ ] Query results expose dataset, parser mode, filters, grouping, source, and run ID.

## Review And Safety Gates

- [ ] PySpark approval works and records reviewer, timestamp, hash, and comment.
- [ ] SQL approval works and records reviewer, timestamp, hash, and comment.
- [ ] DAG approval works and records reviewer, timestamp, hash, and comment.
- [ ] Rejecting an artifact blocks release.
- [ ] Contract, reconciliation, quality, and security failures block release.
- [ ] Production/cloud execution stays disabled before required approvals.
- [ ] Resource creation and chargeable changes require explicit approval.
- [ ] A cloud probe performs read-only operations only.

## Data And Execution

- [ ] Synthetic fixtures satisfy the declared schema and privacy policy.
- [ ] Local validation confirms grain, dimensions, metrics, masks, and filters.
- [ ] No disallowed local-only engine is used in a real MRS execution path.
- [ ] MRS or DataArts returns a successful terminal job state.
- [ ] Gold output exists and is non-empty when acceptance requires rows.
- [ ] Input/output row counts and critical metrics are reconciled.
- [ ] Lineage links source fields, transformations, outputs, and job IDs.
- [ ] Cloud resource bindings are symbolic until release and environment binding.

## API And Controls

Test every enabled user control, including:

- [ ] settings expand/collapse;
- [ ] template selection/application;
- [ ] MaaS test;
- [ ] prompt send and keyboard behavior;
- [ ] progress-step selection;
- [ ] retry/cancel where enabled;
- [ ] artifact selection, copy, and download;
- [ ] reject and approve;
- [ ] release creation;
- [ ] cloud binding and standardization;
- [ ] read-only cloud probe;
- [ ] DataArts package import or export;
- [ ] evaluation execution;
- [ ] Gold data query/refresh;
- [ ] cloud job refresh;
- [ ] new task.

Confirm disabled controls explain their unmet dependency and do not trigger hidden side effects.

## Visual Quality

- [ ] Compose, progress, failure, and results states are inspected at desktop width.
- [ ] The same states are inspected at a mobile width near 390px.
- [ ] There is no horizontal body overflow.
- [ ] Tables and code viewers scroll within their own containers.
- [ ] Long prompts, paths, and identifiers do not collapse the grid or overlap controls.
- [ ] Text is not clipped inside buttons, status labels, tabs, or headers.
- [ ] Focus, hover, active, disabled, loading, empty, and error states are visible.
- [ ] Status meaning is not communicated by color alone.
- [ ] No unexpected browser console errors occur during the primary flow.

## Bilingual Experience

- [ ] The language control is visible and usable on desktop and at a mobile width near 390px.
- [ ] The selected locale persists across reloads and is included in task, ChatBI, retry, and follow-up requests.
- [ ] Switching language preserves the current run, selected step, open result category, and user-authored prompt.
- [ ] Static chrome, dynamic progress, validation errors, result metadata, chart labels, table headers, tooltips, and accessibility labels use the selected language.
- [ ] User prompts, generated code, SQL, physical field names, paths, resource IDs, and immutable evidence are not translated.
- [ ] Equivalent Chinese and English ChatBI questions produce the same canonical contract and metric result.
- [ ] Ranking, comparison, grouping, top-N, and follow-up queries are tested in both languages.
- [ ] Every progress step and all result categories are inspected for unexpected text from the other language.
- [ ] Both language directions work without a full-page state reset or horizontal overflow.
- [ ] Public deployment checks use a cache-busted build and confirm that the currently served assets match the tested version.

## Deployment And Security

- [ ] Application archives contain no credentials or customer data.
- [ ] Secret files are outside the web root and source tree with restricted permissions.
- [ ] Logs and generated artifacts contain no keys, tokens, passwords, or signed URLs.
- [ ] Security-group ingress is limited to approved sources.
- [ ] Runtime roles follow least privilege.
- [ ] Health endpoints reveal configuration state, not secret values.
- [ ] The deployment has a versioned rollback target.
- [ ] Temporary credential files and upload archives are removed or protected.
- [ ] Resource tags, budget alerts, and expiration/destroy plans exist.

## Publication Readiness

- [ ] Skill frontmatter contains only `name` and `description`.
- [ ] Skill validation succeeds with `quick_validate.py`.
- [ ] Examples contain no live resource identifiers or credentials.
- [ ] References are linked from `SKILL.md` and loaded selectively.
- [ ] Packaged schemas and templates parse successfully.
- [ ] Repository destination and license are confirmed with the user.
- [ ] The user reviews the complete local package before any Git commit or upload.
- [ ] The public product name and examples use generic Tax branding; legacy physical resource IDs remain only in protected operational evidence.

## Stop Conditions

Stop and request a decision when:

- business semantics are ambiguous enough to change a metric or regulatory outcome;
- required data access is not authorized;
- a security review reports a blocking exposure;
- chargeable resources are needed but not explicitly approved;
- the release package changed after approval;
- cloud execution cannot be tied to immutable evidence;
- the requested action would expose credentials or direct identifiers.
