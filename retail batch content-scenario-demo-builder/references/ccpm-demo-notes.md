# CCPM Notes For Demo Projects

Use CCPM artifacts when the demo is a seed for real product delivery.

## PRD

Create `.claude/prds/<feature-name>.md` with:

- Executive summary.
- Problem statement.
- User stories with acceptance criteria.
- Functional and non-functional requirements.
- Measurable success criteria.
- Constraints, assumptions, out of scope, and dependencies.

Keep demo-specific assumptions explicit. If the demo uses mock data or deterministic generation, say so.

## Epic

Create `.claude/epics/<feature-name>/epic.md` with:

- Overview.
- Architecture decisions.
- Technical approach split by frontend, backend, and infrastructure.
- Implementation strategy.
- Task breakdown preview.
- Dependencies and technical success criteria.
- Estimated effort.

Use `backlog` for early prototype artifacts unless the user explicitly starts implementation.
