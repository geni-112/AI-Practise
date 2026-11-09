# Acceptance checks

Run checks appropriate to the selected mode. Do not claim cloud integration from a frontend build or configuration-only health flag.

## Skill/package

```bash
python "<skill-dir>/scripts/validate_package.py"
python "<skill-dir>/scripts/quickstart.py" --dest "<fresh-test-dir>" --prepare-only
```

The validator checks frontmatter, relative links, allowed paths and SHA-256 manifest entries. The scaffolder must refuse nonempty destinations. Verify that installing into a test Copilot/Codex/Claude project creates `data-agent-practice/SKILL.md` in the corresponding skill directory with all referenced assets, rather than a bare markdown file.

## Generated app: offline

```bash
npm ci
npm run build
MODEL_API_KEY='' MODEL_BASE_URL='' HUAWEICLOUD_MODEL_API_KEY='' .venv/bin/python -m pytest tests -q
```

Use a fresh synthetic test project with `DEMO_MODE=true`, `DATA_BACKEND=sqlite`, no cloud/model credentials and no production OIDC/OPA values. Explicit empty model environment values prevent `.env` from activating a paid model. Python's existing test suite covers the 10,000-row data contract, tenant-consistent foreign keys, order/line reconciliation, SQL injection rejection, region/domain/export/execution boundaries, flow validation, localization, metadata authentication renewal and the **real local openJiuwen → MCP → SQLite** query.

The deterministic regional-manager October result is one `Mexico City` row, `7180.33` USD, in demo-rules mode. Compare it independently to source CSV/SQLite rather than accepting only an agent's summary.

Browser checks: visit all six workbench pages, expand a catalog, inspect asset fields, submit sales and another scenario, change chart, save a board, draft/inspect a flow and view task state. Verify the top-right selector in `zh-CN`, `en-US`, `es-ES`, preferred font-family, translated dialogs/chart labels, persistence after reload and narrow-screen layout. Confirm that browser mode does not connect an unrelated port-8000 backend or display model execution as real.

## Integrated services

With dedicated local OpenMetadata and Temporal running and seeding complete:

```bash
.venv/bin/python tests/verify_integration.py
```

This creates synthetic sandbox outputs, successful/failed jobs and a temporary daily schedule, then removes that schedule. Verify actual OpenMetadata asset/lineage records, an Iceberg history table, Temporal completion/quality-failure behavior and idempotent output partitioning. Closing the browser must not stop a server-side task.

## DWS and model

Use authorized private connectivity and a read-only query account. Check a live scoped query against independently computed synthetic CSV totals, both tenants, restricted region/domain, and export denial. Confirm `mode=model` only when a model request actually returned an accepted plan. Repeat an English and Spanish request with matching localized summaries and unchanged data permissions. Do not run this test with inherited production secrets or record sensitive HTTP headers/DSNs.

The dedicated cloud verifier is described in [cloud-deployment.md](cloud-deployment.md); it must be run and inspected in the new cloud installation before reporting a deployed state.
