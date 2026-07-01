---
name: huawei-realtime-monitor-website
description: Build secure realtime monitoring websites for Huawei Cloud big-data environments. Use when Codex needs to log in with local AK/SK or IAM credentials, discover and aggregate OBS/MRS/CDM/DWS/DataArts/ECS/VPC resources, generate a 5-second-refresh monitoring website, collect deployment evidence/log summaries, deploy a static OBS copy, and expose the final site through HTTPS on ECS/Caddy without committing secrets.
---

# Huawei Realtime Monitor Website

## Overview
Use this skill to reproduce an end-to-end Huawei Cloud realtime monitor build: credential bootstrap, resource inventory, status aggregation, static site generation, OBS publishing, HTTPS ECS/Caddy exposure, and delivery evidence.

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
   - Distinguish cloud resource records from business assets. ECS nodes, EIPs, and terminated MRS clusters can inflate raw counts.
4. **Website generation**
   - Copy `assets/monitor-template/` into the working project's `monitor/` folder, or adapt the existing monitor folder.
   - Run `scripts/build_static_site.py --zip`.
   - Preserve the 5-second refresh in `app.js`.
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
7. **Evidence and logs**
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
