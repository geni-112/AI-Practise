---
name: scenario-demo-builder
description: Build architecture-backed, locally previewable demos for business or product scenarios. Use when the user asks to create a demo, prototype, preview site, clickable concept, architecture plus demo, MVP mock, scenario walkthrough, or wants to turn a business use case such as retail, finance, operations, cloud, or AI workflow into a clear local web demo with implementation planning artifacts.
---

# Scenario Demo Builder

## Overview

Create a stakeholder-readable demo first, then the technical scaffolding around it. The output should make the scenario obvious in the first viewport, provide a useful architecture view, include a working preview, and leave planning artifacts that can become implementation work.

## Workflow

1. Restate the scenario in plain business language.
   - Identify the target user, the business problem, the input, the generated or transformed output, and the handoff or decision.
   - If the scenario is ambiguous, make a reasonable assumption and label it briefly.

2. Define the demo contract before building.
   - First viewport: show what the site is for, who uses it, and what happens from input to output.
   - Core workflow: provide at least one realistic operator action, not only static cards.
   - Architecture: show source systems, orchestration or business logic, AI/service layer when relevant, review/publishing, and feedback loops.
   - Planning: create CCPM PRD/Epic files when the request implies product delivery or future build work.

3. Build a local preview.
   - Prefer a small static app (`index.html`, `styles.css`, `app.js`) for fast scenario demos unless the existing repo already has an app framework.
   - Use existing project conventions when working inside a repo.
   - Use business labels over internal jargon. Avoid unexplained English-only acronyms for non-technical stakeholders.
   - Include realistic sample data and meaningful states such as draft, ready, needs review, approved, failed check, or published.

4. Add architecture assets.
   - Use an on-page architecture view for immediate comprehension.
   - When the user asks for architecture, or when the system has 3+ meaningful components, also create an editable diagram source such as `.drawio` when the drawio skill is available.
   - Keep the diagram readable: 4-6 lanes or layers, concise labels, arrows that do not cross important nodes, and a visible feedback loop if analytics or learning is part of the scenario.

5. Integrate CCPM when planning is relevant.
   - Use the CCPM skill for PRD/Epic conventions.
   - Create `.claude/prds/<feature-name>.md` and `.claude/epics/<feature-name>/epic.md` for demos that may become implementation projects.
   - Mark early demo planning as `backlog` unless the user explicitly starts execution.

6. Verify before handing off.
   - Open the local preview in the in-app browser when possible.
   - Validate that the first viewport explains the purpose, the main CTA works, generated or transformed output appears, console has no errors, and page body has no unexpected horizontal overflow.
   - If screenshot capture fails but DOM and interaction checks pass, report that clearly.

## Business Clarity Rules

- Do not lead with architecture terms. Lead with "this is for X user to do Y from Z input."
- Avoid a marketing landing page unless the user explicitly asks for one. Build the actual work surface or workflow preview.
- Include an "Input -> Processing/AI -> Review/Output" explanation band for complex demos.
- Use domain-specific sample data that a stakeholder can recognize.
- Make the demo self-explanatory enough that the user does not need to ask "what is this website for?"

## Frontend Shape

For static demos, use this structure unless the repo suggests another pattern:

```text
index.html
styles.css
app.js
.claude/prds/<feature-name>.md
.claude/epics/<feature-name>/epic.md
<feature-name>-architecture.drawio
<feature-name>-architecture.png
```

Recommended sections:

- Scenario header: clear title, user, problem, and outcome.
- Explanation band: input, generation/processing, review/publish/output.
- Architecture: layered system view.
- Workspace: controls, sample records, and primary action.
- Output/review: generated results, status, score, warnings, or next actions.

## References

- Read `references/quality-checklist.md` before final verification.
- Read `references/ccpm-demo-notes.md` when creating planning artifacts.
