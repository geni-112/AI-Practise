---
name: huawei-realtime-monitor-website
description: Build secure realtime monitoring websites for Huawei Cloud big-data environments. Use when Codex needs to log in with local AK/SK or IAM credentials, discover and aggregate OBS/MRS/CDM/DataArts/RDS/OBS/ECS/VPC resources, generate a cadence-aware realtime monitoring website with live status refresh, script-status catalog, data-layer catalog, deployment evidence/log summaries, OBS static publishing, and HTTPS ECS/Caddy exposure without committing secrets.
---

# Huawei Realtime Monitor Website

## Overview
Use this skill to reproduce an end-to-end Huawei Cloud realtime monitor build: credential bootstrap, resource inventory, status aggregation, live status refresh, static site generation, OBS publishing, HTTPS ECS/Caddy exposure, and delivery evidence.

Prefer AK/SK loaded from encrypted local profiles or environment variables. Never commit secrets, raw credential profiles, raw cloud logs, or unredacted inventory exports.

## Workflow
1. **Credential bootstrap**
   - Prefer `scripts/Update-SatAkSkProfileDialog.ps1` to validate AK/SK and save it locally with Windows DPAPI.
   - Load credentials in the active shell with `scripts/Load-HuaweiCredentialProfile.ps1`.
   - Use password-based scripts only as a fallback when AK/SK is not available.
2. **Asset discovery**
   - Run `scripts/huawei_inventory.py --region <region> --project-id <project_id>`.
   - Use AK/SK mode when `HUAWEICLOUD_ACCESS_KEY`, `HUAWEICLOUD_SECRET_KEY`, and `HUAWEICLOUD_PROJECT_ID` are set.
   - Treat API failures as partial collection notes, not fatal findings, unless core services cannot be queried.
3. **Asset aggregation**
   - Run `scripts/analyze_bigdata_assets.py`.
   - The output `monitor/data/status.json` is the website data contract.
   - Distinguish cloud resource records from business assets. Exclude monitor ECS/EIP from pipeline counts unless the user explicitly wants infrastructure monitoring.
   - Add `layer` and `status` to data catalog rows. Classify RAW/Bronze/Silver/Gold from explicit path names where available, and otherwise use SAT path rules such as logs/input/Datos_idc as RAW, Iceberg/MVP intermediate tables as Bronze/Silver, and RDS serving records as Gold.
   - Include `script_chain` records for credential loading, inventory, aggregation, packaging, OBS deployment, live refresh, and background launcher status.
4. **Website generation**
   - Copy `assets/monitor-template/` into the working project's `monitor/` folder, or adapt the existing monitor folder.
   - Run `scripts/build_static_site.py --zip`.
   - Use `refresh_seconds` from `status.json` for the browser polling cadence. Do not hard-code 5 seconds when live collection takes longer.
   - Use native `<progress value="..." max="100">` for stage progress so 100% fills green and partial values, such as 45%, stop at the real percentage.
   - Show separate poll time and data-generation time. Keep JSON timestamps in UTC, but display the user-facing business timezone clearly when required.
   - Include the Script Status Catalog before Data Structure, and show Data Structure Layer and Status columns.
   - Use modern dark UI defaults unless the user provides another design.
5. **OBS static copy**
   - Run `scripts/deploy_obs_static_site.py --region <region> --bucket <bucket>`.
   - Use OBS as the source for static files and `data/status.json`.
   - Do not rely on default OBS website domains for final demos if the browser blocks downloads or flags the origin.
6. **Secure HTTPS website**
   - Run `scripts/deploy_ecs_monitor_site.py --region <region> --project-id <project_id> --name <name>`.
   - The script creates a small pay-per-use ECS, EIP, security group, and Caddy HTTPS endpoint.
   - Prefer a real customer domain. For quick POCs, `sslip.io` can map the EIP to a DNS name that supports certificate issuance.
   - Do not send users to bare HTTP IP URLs.
7. **Live refresh**
   - Run `scripts/refresh_live_status.py --region <region> --interval <seconds>` for a one-shot refresh or add `--loop` for continuous refresh.
   - On Windows, prefer `scripts/Start-SatRealtimeStatusRefresh.ps1 -IntervalSeconds 20 -Region <region>` after loading the encrypted AK/SK profile.
   - Set `SAT_MONITOR_REFRESH_SECONDS` before running aggregation when the site cadence should be stored in `status.json`; SAT Mexico currently uses 20 seconds because one live scan takes about 20 seconds.
   - Treat browser polling as a view refresh and live inventory collection as data refresh. Do not claim data is realtime unless `generated_at` advances through the refresh loop.
8. **Evidence and logs**
   - Run `scripts/aggregate_monitor_evidence.py --site-url <https_url>`.
   - Include resource summary, service counts, latest status timestamp, deployment URL, and limited-source notes.
   - Browser console checks and HTTP status checks should be summarized in the final handoff.

## Key Resources
- Read `references/workflow.md` before executing the full live-cloud workflow.
- Read `references/security-model.md` before handling credentials, publishing to GitHub, or creating paid cloud resources.
- Use `assets/monitor-template/` as the frontend baseline.
- Use scripts directly; patch only environment-specific constants or naming.

## Safety Rules
- Never commit `%LOCALAPPDATA%` credential profiles, `.env` files, AK/SK, IAM passwords, DWS passwords, tokens, or raw unredacted API logs.
- Before recursive deletes or cleanup on Windows, verify the absolute path is inside the intended workspace.
- When replacing a temporary web ECS, verify the new HTTPS endpoint works before deleting the old endpoint.
- Keep MRS, DWS, RDS, and DataArts private. Expose only the web ingress on HTTP/HTTPS.
