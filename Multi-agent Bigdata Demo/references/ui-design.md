# UI Design System

## Design Intent

Create a quiet, work-focused interface inspired by the information density and hierarchy of Databricks workspaces without copying proprietary brand assets or exact layouts.

Optimize for a business user who starts with intent and an engineer or reviewer who later needs exact artifacts, parameters, and evidence. Reveal complexity only when the workflow reaches it.

## Visual Character

- Use a white or very light neutral background with restrained gray boundaries.
- Use one warm red-orange accent for primary actions and active navigation.
- Use green, amber, red, and gray only for semantic status.
- Use compact typography, stable spacing, and thin borders.
- Avoid gradients, decorative illustrations, oversized hero type, nested cards, and pill-heavy chrome.
- Keep card radii at 8px or less.
- Use a system font stack that renders cleanly in Chinese and English.

Recommended font stack:

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC",
  "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
```

Use `assets/workbench-design-tokens.css` as the starting token set.

## Three Interface Stages

### Stage 1: Compose

Make the initial viewport feel like a simple ChatGPT-style task entry, not a dashboard.

Show only:

- a compact product or workspace name;
- one centered conversation/composer area;
- a clear prompt placeholder in business language;
- a send icon button;
- one quiet safety statement indicating that cloud execution requires review;
- an optional collapsed settings control.

Hide prompt templates, MaaS settings, resource bindings, synthetic data, and engineering controls under settings. A user must be able to begin with one natural-language message.

### Stage 2: Progress

After submission, replace the empty state with a simple execution view:

- task title and one-line prompt summary;
- overall progress bar and completed/total count;
- ordered workflow steps with status icons;
- one selected-step inspector aligned to the right on desktop;
- plain-language input and output sections for the selected step;
- visible failure reason and retry/review action when applicable.

Do not show all detailed artifacts while work is still running. Keep the selected step synchronized with real backend state.

Recommended visible steps:

1. Data context
2. Business contract
3. Contract audit
4. Architecture decision
5. Code and DAG generation
6. Local validation
7. Governance and review
8. Release or cloud execution

### Stage 3: Results Workbench

When sufficient output exists, transition into a detailed workspace. Use a compact top task header, left navigation on desktop, and a content area with expandable sections.

Use these categories:

| Category | Show |
|---|---|
| Overview | Goal, owner, status, execution mode, acceptance, key metrics |
| Workflow | Step timeline, duration, inputs, outputs, errors, retries |
| Artifacts | Contract, PySpark, SQL, DAG, files, diff, review decisions |
| Data | Source schema, masked samples, Gold preview, row counts, partitions |
| Governance | Quality rules/results, security review, lineage, approvals |
| Cloud | Resource binding, read-only probe, job IDs, logs, result locations |

Use accordions inside each category so the user controls detail. Avoid putting cards inside cards. Present source code in a stable-height viewer with copy/download actions and syntax highlighting where available.

## Interaction Rules

- Use familiar icons for send, settings, refresh, copy, download, approve, reject, expand, and collapse.
- Add tooltips to unfamiliar icon-only controls.
- Use text buttons for consequential commands such as `Approve release` or `Execute in cloud`.
- Keep advanced options collapsed by default.
- Disable unavailable actions and state the actual dependency next to them.
- Show technical identifiers as secondary text beneath plain-language names.
- Preserve the user's prompt when a run fails or is retried.
- Make `New task` explicit after results exist.
- Do not imply MaaS was used based only on configuration; read runtime evidence.
- Do not imply cloud execution occurred based on a successful probe.

## Status Semantics

Always pair color with text or an icon.

| Status | Color role | Example label |
|---|---|---|
| Pending | neutral | Waiting |
| Running | accent/blue-neutral | Running |
| Success | green | Completed |
| Needs review | amber | Review required |
| Blocked | amber/red | Execution blocked |
| Failed | red | Failed |
| Skipped | neutral | Not required |

Keep status chips compact. Do not use chips for every piece of metadata.

## Responsive Layout

### Desktop

- Constrain the compose column to a readable width.
- Use a two-column progress layout: steps on the left and input/output inspector on the right.
- Use a 180-220px results sidebar and a flexible main content column.
- Keep the top task bar compact, approximately 48-56px.

### Mobile

- Collapse progress into one column with the inspector beneath the selected step.
- Convert the results sidebar into a sticky horizontal tab strip.
- Keep wide tables and code viewers internally scrollable; never widen the page body.
- Stack action groups and preserve a minimum 44px touch target.
- Ensure long paths, identifiers, and unbroken words wrap or truncate with an accessible full-value view.

## Typography And Spacing

- Use 14-16px body text and 12-13px secondary metadata.
- Use 20-28px only for primary page titles; use 16-18px for panel headings.
- Keep letter spacing at `0`.
- Do not scale font size with viewport width.
- Use an 8px spacing rhythm with 4px for dense internal alignment.
- Reserve bold weight for hierarchy and decisions, not every label.

## Accessibility

- Associate labels with all form controls.
- Support `Enter` to send and `Shift+Enter` for a new line.
- Expose progress and status changes to assistive technology.
- Maintain visible keyboard focus.
- Meet contrast requirements for text, controls, and status states.
- Do not depend on color alone to communicate success or failure.

## Visual Acceptance

Before handoff, capture and inspect at least:

- initial compose state on desktop and mobile;
- active progress state with a selected step;
- failure/retry state;
- completed results Overview;
- Artifacts code view;
- Data table on mobile;
- Governance and Cloud sections.

Reject layouts with horizontal body overflow, clipped labels, overlapping text, unstable button dimensions, empty excessive whitespace, or a narrow text column caused by accidental grid sizing.
