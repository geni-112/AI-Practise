# Local development

Use a new destination. Python 3.12 is the supported backend environment; Node.js 22.12+ is recommended. The browser profile needs only Python's standard library to generate data and npm to run the UI. The integrated profile additionally needs Docker Compose, uv and sufficient memory for OpenMetadata/OpenSearch (plan for about 8 GB available).

## Browser demo

```bash
python "<skill-dir>/scripts/quickstart.py" --dest "<new-project-dir>"
```

Default URL: `http://127.0.0.1:5173`. Use `--port 5180` if occupied. The script refuses a nonempty destination; to restart an existing generated project, run `npm run dev -- --host 127.0.0.1 --port 5173` there instead. `--prepare-only` copies source, creates a private `.env`, and generates data and safe UI download archives without dependency installation.

The Vite configuration reads `NEXO_BROWSER_ONLY=true` and disables API proxying. This prevents accidentally attaching the new browser demo to an unrelated backend already running on port 8000. It never exposes model keys using `VITE_*`.

## Integrated backend

```bash
python "<skill-dir>/scripts/scaffold.py" --dest "<new-project-dir>" --profile integrated
cd "<new-project-dir>"
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
docker compose --env-file .env -p nexo -f infra/local-compose.yml -f infra/runtime-compose.yml up -d
```

All commands below run from this generated project. On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`. If reusing an existing integrated stack, inspect port usage and existing volumes before starting another Compose project. Do not delete a user's volumes to resolve port conflicts.

Wait for OpenMetadata's version endpoint to return HTTP 200 and Temporal on 7233 to accept connections. Then run:

```bash
.venv/bin/python -m backend.metadata
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

URLs: UI 5173, API 8000, OpenMetadata 8585, Temporal UI 8233. Compose binds development ports to loopback. Local OpenMetadata uses the upstream development administrator (`admin@open-metadata.org` / `admin`); do not expose that stack publicly. The scaffolder generates a new private Fernet key in `.env` for local Compose. OpenMetadata authentication refresh is allowed only for the local demo bootstrap, with tokens stored privately in `.runtime`.

OpenMetadata seeding registers 11 business tables for each of the two logical tenant catalogs; the control `tenants` table is not a regular discoverable business asset. Confirm the API health and real task/lineage checks in [acceptance.md](acceptance.md).

To move a browser scaffold to integrated mode, change `.env`: `NEXO_BROWSER_ONLY=false`, `OPENMETADATA_URL=http://127.0.0.1:8585`, `TEMPORAL_ENABLED=true`. Restart Vite and API after changing configuration.

## Data and maintenance

The scaffolder runs the deterministic generator automatically in the new project. It creates 12 CSVs, `data/schema.sql`, `data/manifest.json`, `public/demo-data.json` and `.runtime/warehouse.db`. All records are fictional, in English, seed 20261106, USD; quality scenarios are 18 missing phones and 6 negative inventory values. The generator replaces only the demo's local SQLite source tables, so do not run it against a directory holding user-maintained data.

Quickstart generates the UI download archives locally. If using `scaffold.py` directly, run `python scripts/package_downloads.py` before a release build when UI download links are needed. It generates source and data archives from allowlisted source paths; keep actual `.env` and `.runtime` excluded. These archives are not prebuilt in the skill.

Stopping `docker compose --env-file .env -p nexo -f infra/local-compose.yml -f infra/runtime-compose.yml stop` preserves volumes. Removing volumes is a separate destructive action and is not part of routine shutdown.
