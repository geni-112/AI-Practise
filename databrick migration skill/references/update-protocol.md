# Skill Update Protocol

Use this reference whenever the user shares Databricks/Snowflake scripts for conversion, asks migration questions, finishes a demo iteration, or compares AI-generated conversion documents with human conversion documents. The goal is to make the skill improve across new Codex windows and sessions.

## What to Capture

Add a lesson when at least one condition is true:

- A source pattern was not already covered by the references.
- A Huawei replacement was verified through a command, log, row count, UI action, or code review.
- A platform limitation or syntax incompatibility changed the migration approach.
- A workaround is likely to repeat in future Databricks/Snowflake demo migrations.
- A transformation became mechanical enough to become a future script or checklist item.
- A human conversion document exposes a reusable gap in the AI-generated conversion document.
- A human conversion document shows a better runbook, validation, DataArts job layout, DWS SQL style, or migration explanation pattern.

Do not capture:

- Secrets, tenant IDs, passwords, access keys, private endpoints, or customer-confidential values.
- Purely speculative ideas without a validated replacement.
- One-off file names or cosmetic project details that will not generalize.
- Large copied source code blocks. Store the pattern, not the whole customer script.
- Verbatim human-written document sections. Store the learned rule or gap, not the prose.

## Update Targets

- `references/demo-lessons.md`: Append every reusable session lesson here first.
- `references/delta-to-iceberg.md`: Update when the lesson affects Delta, CDC, Spark/Iceberg table behavior, schema evolution, or table maintenance.
- `references/jobs-to-huawei.md`: Update when the lesson affects Databricks Jobs, DataArts orchestration, MRS submit shape, parameters, retries, or dependencies.
- `references/sql-to-dws.md`: Update when the lesson affects Snowflake/Databricks SQL conversion or DWS compatibility.
- `references/document-comparison-feedback.md`: Read when comparing AI-generated and human conversion documents; update when the comparison workflow itself improves.
- `scripts/`: Add or extend scripts only when a repeated step is mechanical and testable.
- GitHub mirror: Keep `geni-112/AI-Practise` directory `databrick migration skill/` synchronized after local skill updates.

## Capture Flow

1. Re-read the relevant reference file before editing, so the new lesson does not duplicate existing rules.
2. Summarize the observed source pattern in neutral terms.
3. Record the issue or gap that required migration work.
4. Record the Huawei replacement that actually works or is the chosen demo-safe approximation.
5. Record validation evidence. If no validation was run, write `Validation: Not yet validated` and avoid promoting the idea into a general rule.
6. Run `quick_validate.py` after editing `SKILL.md` or metadata. For reference-only updates, at least inspect the appended markdown.
7. Sync the skill mirror to GitHub with `python scripts/sync_to_github.py` after any local update. Prefer `python scripts/record_update.py` when adding a lesson because it appends the lesson, validates, and syncs in one step. `append_demo_lesson.py` also runs sync automatically unless `--no-github-sync` is used.

## Document Comparison Capture

When comparing AI-generated conversion docs with human conversion docs:

1. Create a compact gap table with `area`, `AI behavior`, `human behavior`, `decision`, and `skill update`.
2. Promote only reusable differences into references or scripts.
3. Append a `demo-lessons.md` entry titled `AI-vs-human doc comparison - <context>`.
4. In the final response, state which gaps were promoted, which were rejected as one-off, and which still need runtime validation.

## Preferred Script

Use:

```bash
python scripts/record_update.py --title "Demo name" --source "..." --issue "..." --replacement "..." --validation "..."
python scripts/append_demo_lesson.py --title "Demo name" --source "..." --issue "..." --replacement "..." --validation "..."
```

`record_update.py` is the preferred entrypoint. It appends to `references/demo-lessons.md`, runs validation through `sync_to_github.py`, and pushes the GitHub mirror. `append_demo_lesson.py` remains available for direct lesson append and also syncs by default unless `--no-github-sync` is provided.

## GitHub Mirror Sync

The skill is mirrored into:

```text
https://github.com/geni-112/AI-Practise/tree/main/databrick%20migration%20skill
```

Use:

```bash
python scripts/sync_to_github.py
```

The sync script validates the skill by default, clones or updates a local checkout, replaces the repository directory `databrick migration skill/` with the current local skill files, commits changes when there is a diff, and pushes to `main`.
