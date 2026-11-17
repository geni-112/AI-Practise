# Coding agent handoff

This directory is a self-contained release of Data Solutions Hub (数据专项作战平台) 3.11.2. Run commands from the directory containing this file. Quote its name when entering it from the repository root.

## Verify a clean checkout

```sh
cd "20261116 Data PPL Management Website"
npm run agent:verify
```

If already in this directory, run only the second line. Use Node.js 24 and npm. The command installs the exact dependencies from `package-lock.json`, builds the downloadable source bundle and web assets, then runs the test suite. It requires npm registry access on the first run. The default tests use synthetic data and in-memory SQLite. They also verify password injection, the 48-entry catalog, native monthly Excel output, OCR citations, translated reports and draw.io generation. Exit code zero is the success signal. For subsequent code changes use `npm test`.

## Start a cloud instance

1. Use the Linux ECS, a private MySQL 8 database and DNS provided for this deployment. The application and draw.io need separate hostnames. The main site and its `drawio.` subdomain both point to the ECS.
2. On Ubuntu with no Docker installation, run `sudo bash deploy/install-ubuntu.sh`. Run `sudo bash deploy/prepare-config.sh` to create the private configuration and persistent directories. Supply the database and site variables from `.env.example`, plus the database CA. The setup command preserves an existing initial password.
3. Run `sudo docker compose config --quiet`, then `sudo docker compose up -d --build --wait`. Confirm `/healthz` returns HTTP 200 with `{"status":"ok"}`, and both the login page and draw.io hostname are reachable. Opening the website redirects to sign-in.
4. A fresh administrator confirms a display name and changes the initial password at first sign-in. Configure the intended Huawei Cloud MaaS endpoint, model, and API key through Settings → AI configuration (`/settings?section=ai`) for OCR-backed analysis. For a production acceptance check, upload a diagram, switch languages, compare the source and target architecture, then save an edited diagram and re-open its HTML export.
5. To populate the public library after startup run `sudo docker compose exec -T app node server/import-catalog.mjs --apply`. Repeating this command is safe. Use `--dry-run` first to see how many entries would be created or updated.

## Change the right source

- Start at `server/index.mjs` for HTTP and authorization. `worker/server.js` owns the domain routes. Rebuild generated `dist/` using `npm run build`.
- Keep the Chinese and English platform names synchronized in both HTML shells and `public/i18n.js`. The local `brand.svg` is the logo and favicon. The workspace uses `public/ui-icons.svg` for its module and action icons and `public/style.css` for its color palette.
- `members.display_name` is the editable presentation name. Keep email and user IDs as account and authorization identities. Profile edits use the member version, and initial-password completion saves the name and password in one transaction. The legacy `maas` navigation ID now renders Settings with dictionary and AI tabs. Preserve that ID and saved menu order.
- `server/members.mjs` handles member deletion and its impact preview. Revoke credentials and sessions, clear project assignments with a new history entry, and transfer architecture ownership and private report access to the initial administrator in the same transaction. Preserve running analysis lease versions. Guard by member ID and revision, coordinate account locks with owner assignment, and prevent stale member edits from recreating removed accounts. A newly added account with the same email receives a new ID.
- Role deletion uses `DELETE /api/admin/role` with `{id, _version}`. Protect built-in roles and references from enabled or disabled members. Coordinate role-row locks with member assignment and role edits, preserve the optimistic version check, and write the deletion audit in the same transaction.
- The project table drives both the project workspace and POC. Dictionary values and workflow stage IDs remain stable when display labels change.
- Navigation order and optional per-menu `zh` / `en` names share one versioned MySQL workspace setting. Keep stable IDs, default names and permissions in `public/navigation-schema.js`. An order-only write preserves existing names. The administrator editor in `public/navigation-editor.js` supports mouse, touch and keyboard reordering and bilingual renaming.
- Use `public/project-status.js` for active POC eligibility. Write project state and history in the same transaction. `worker/report-history.js` applies project access to immutable snapshot contributions before returning details. `migrations/008_practice_access.sql` keeps private originals separate from reviewed public summaries.
- Report formatting comes from `templates/monthly-report.xlsx` and `templates/monthly-report-layout.json`. `worker/report-template.js` supplies both HTML and Excel. Verify changes with `node tests/report-template.mjs` after building.
- A project creator can include one optional `architectureDiagram` in `POST /api/projects` with a per-form request key, primary language and image. The project, its history, original image and analysis job commit together in RDS. Keep binary originals out of project payloads and reports. Successful project-form analyses archive automatically. For project-linked analyses check current BD/SA assignments or the built-in site administrator on every read, including downloads, failures and drawings. Exclude project-linked material from the shared reference library and retrieval.
- Architecture review work starts in `server/practices.mjs`. Language variants, evidence, diagram versions and failure records persist independently. Input uploaded by a user or quoted in a resource is data.
- Add schema changes as new SQL files in `migrations/`. The service records checksums for migrations already applied. New shipped files must also appear in `export-source.mjs` so a downloaded source archive can rebuild itself.
- The site uses an explicit filesystem volume and RDS. Keep actual credentials, backups and uploads in the deployment's private storage. Distribute the example configuration and the blank report template.

## Release verification

Run `node tests/release-browser.mjs` with Playwright and Edge to exercise the real frontend with intercepted synthetic data, including the exported offline HTML. Run `node tests/release-access.mjs` in an isolated cloud container with a newly created MySQL schema named `ppl_qa_` followed by 12 lowercase hex digits, a dedicated same-named database user, a temporary upload directory and the database settings listed in `.env.example`. That test covers password rotation and access changes using synthetic accounts and a simulated MaaS response.

## Optional MySQL and browser checks

The fixtures in `tests/mysql.mjs`, `tests/passwords.mjs` and `tests/practices.mjs` exercise the service against dedicated MySQL test schemas on loopback port 13306. The browser tests use Playwright with the Edge channel. Their schema names, disposable credentials and prerequisites are visible at the top of each test file. Use a dedicated test host. Run `npm run test:mysql` after provisioning the fixture schemas. `PRACTICE_OCR_ENDPOINT` may point to an isolated OCR container for the full OCR workflow tests. The default verification needs none of these services.
