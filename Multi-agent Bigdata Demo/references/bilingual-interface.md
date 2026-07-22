# Bilingual Interface Contract

## Goal

Support Chinese and English as complete product modes without duplicating the application or weakening the governed query path. Language changes presentation and natural-language understanding; it must not change business definitions, permissions, executable artifacts, or evidence.

## Ownership Boundary

Use three layers:

| Layer | Owns | Must not own |
|---|---|---|
| Client localization | Navigation, buttons, status labels, form help, tooltips, deterministic field labels | Business answer generation or query semantics |
| Backend localization | ChatBI answers, KPI labels, chart/table metadata, clarifications, suggestions, workflow summaries | Physical schema renaming or translated executable code |
| Canonical domain model | Metric IDs, dimension IDs, formulas, policies, contracts, artifact hashes | Language-specific display text |

Make `locale` an explicit typed field on task and ChatBI APIs. Normalize it to a small allowlist such as `zh` and `en`, use one documented default, and return the effective locale in evidence.

## State-Preserving Switch

Persist the selected locale in browser storage or the authenticated user profile. A language switch should re-render known display text and refresh localized business content when needed, while preserving:

- run ID and execution state;
- the original user prompt;
- selected workflow step;
- open result category and accordion state;
- validated ChatBI contract history;
- approvals, hashes, logs, and cloud evidence.

Never translate user-authored prompts, generated PySpark or SQL, physical columns, file paths, resource identifiers, log payloads, or immutable evidence. Add translated explanations alongside technical values when useful.

## Dynamic Content

Static HTML translation is insufficient because this workbench renders most content after a request begins. Localize every dynamic source:

1. API responses include localized business labels and messages.
2. Streaming or polled workflow events use stable status codes plus localized display text.
3. Frontend render functions map deterministic codes and field labels through one translation registry.
4. Error responses expose a stable error code and a safe localized message.
5. Charts and tables receive localized titles and headers without changing canonical keys.

A DOM observer can be a transitional compatibility layer for legacy pages, but new components should call the translation registry directly. Do not use broad text replacement on code blocks, prompts, logs, or data cells.

## ChatBI Language Rules

Compile every supported language into one canonical query contract. Keep localized aliases in the semantic catalog and add deterministic coverage for common patterns before MaaS fallback.

Verify at least:

- totals and counts;
- ranking and top-N;
- comparison by dimension;
- grouping by tax regime, region, year, or approved flags;
- explicit filters and follow-up filters;
- ambiguous requests that require clarification.

For example, Chinese and English requests for taxpayer counts by tax regime must resolve to the same canonical metric and `group_by` value. Test the contract, not only the final sentence.

## Validation Matrix

Run the primary path in both directions, `zh -> en` and `en -> zh`, without clearing state.

| Surface | Required checks |
|---|---|
| Compose | Placeholder, settings, send behavior, persisted locale |
| Progress | All step names, statuses, input/output descriptions, failure and retry |
| Results | Overview, Workflow, Artifacts, Data, Governance, Cloud |
| ChatBI | KPI, chart, table, source evidence, suggestions, follow-ups |
| MaaS | Configuration test, runtime-used evidence, localized failure fallback |
| Responsive | Desktop and approximately 390px mobile, no body overflow |

Scan visible UI text for unexpected Han characters in English mode and unexpected untranslated product text in Chinese mode. Exclude user prompts, code, raw data, physical identifiers, and evidence fields from this scan.

## Deployment Checks

- Version or cache-bust JavaScript and CSS assets after localization changes.
- Confirm the public server is serving the tested asset revision, not only the local build.
- Exercise language controls, a complete engineering run, ChatBI, MaaS test, and all result categories on the public URL.
- Capture screenshots at desktop and mobile widths and inspect overflow, clipping, stale text, and state loss.
- Record the locale, build version, run ID, parser mode, catalog version, and MaaS usage in acceptance evidence.
