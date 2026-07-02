# Workflow Reference

## End-to-End Build
1. Confirm target region, project ID, and whether paid resources are allowed.
2. Validate credentials:
   - AK/SK: `powershell -STA -File scripts/Update-SatAkSkProfileDialog.ps1 -Region <region> -ProjectId <project_id>`
   - Load later shells: `. .\scripts\Load-HuaweiCredentialProfile.ps1`
3. Discover assets:
   - `python scripts/huawei_inventory.py --region <region> --project-id $env:HUAWEICLOUD_PROJECT_ID`
   - Optional enrichments: `OBS_BUCKETS`, `DATAARTS_WORKSPACE_ID`, `DWS_HOST`, `DWS_DATABASE`, `DWS_USER`, `DWS_PASSWORD`.
4. Aggregate website status:
   - `$env:SAT_MONITOR_REFRESH_SECONDS = "20"` when the live collection cadence should be 20 seconds.
   - `python scripts/analyze_bigdata_assets.py`
   - Check `monitor/data/status.json`.
   - Confirm `generated_at`, `refresh_seconds`, `script_chain`, and catalog `layer`/`status` fields.
5. Build the static site:
   - `python scripts/build_static_site.py --zip`
6. Publish the OBS source copy:
   - `python scripts/deploy_obs_static_site.py --region <region> --bucket <bucket>`
7. Deploy the secure endpoint:
   - `python scripts/deploy_ecs_monitor_site.py --region <region> --project-id $env:HUAWEICLOUD_PROJECT_ID --name <monitor-name>`
8. Start live status refresh:
   - One shot: `python scripts\refresh_live_status.py --region <region> --interval 20`
   - Continuous Windows loop: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Start-SatRealtimeStatusRefresh.ps1 -IntervalSeconds 20 -Region <region>`
   - Verify `<site-url>/api/status` advances `generated_at` after a full collection cycle.
9. Verify:
   - Fetch `<site-url>/`
   - Fetch `<site-url>/data/status.json`
   - Confirm resource count, generated timestamp, `refresh_seconds`, HTTPS certificate, browser console logs, Script Status Catalog, and RAW/Bronze/Silver/Gold/Support data layers.
10. Clean up superseded web endpoints only after the replacement HTTPS URL works.
11. Produce evidence:
   - `python scripts/aggregate_monitor_evidence.py --site-url <site-url>`

## Count Interpretation
Do not present raw `summary.resource_count` as business asset count without explanation. Raw records may include:
- ECS nodes that belong to an MRS cluster.
- Web ECS nodes created for the monitor.
- EIP records.
- Terminated or inactive MRS clusters still visible through APIs.

For executive dashboards, split:
- Core big-data assets: MRS, RDS, CDM, DWS, DataArts, OBS.
- Infrastructure records: ECS, VPC, EIP, security groups.
- Inactive records: terminated or deleted-but-visible resources.

## Realtime Interpretation
- Browser polling is not the same as cloud inventory refresh. The UI should use `status.refresh_seconds` for polling, and the backend refresh loop should advance `status.generated_at`.
- If a live collection cycle takes about 20 seconds, set the UI and backend cadence to 20 seconds instead of repeatedly polling a stale static file every 5 seconds.
- Keep stored timestamps in UTC for auditability. Convert display times to the user's business timezone and show the timezone label, such as `UTC-03`, in the page header.

## Data Structure Layers
- Add `layer` and `status` to each catalog row.
- Prefer explicit path names (`raw`, `bronze`, `silver`, `gold`) when present.
- For SAT-style paths without explicit layer folders, classify log/input/Datos_idc paths as RAW, Iceberg/MVP intermediate paths as Bronze or Silver, and RDS serving records as Gold.
- Include Support for script folders, user trash, temporary program paths, and other non-business data structures.

## Common Commands
```powershell
. .\scripts\Load-HuaweiCredentialProfile.ps1
python scripts\validate_huawei_aksk.py
python scripts\huawei_inventory.py --region la-north-2 --project-id $env:HUAWEICLOUD_PROJECT_ID
python scripts\analyze_bigdata_assets.py
python scripts\build_static_site.py --zip
python scripts\deploy_obs_static_site.py --region la-north-2 --bucket <bucket>
python scripts\deploy_ecs_monitor_site.py --region la-north-2 --project-id $env:HUAWEICLOUD_PROJECT_ID --name <name>
python scripts\refresh_live_status.py --region la-north-2 --interval 20
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Start-SatRealtimeStatusRefresh.ps1 -IntervalSeconds 20 -Region la-north-2
python scripts\aggregate_monitor_evidence.py --site-url https://<domain>/
```

## Frontend Notes
- Keep the first screen the operational monitor, not a landing page.
- Read the refresh cadence from `status.refresh_seconds`; do not hard-code `setInterval(..., 5000)`.
- Render pipeline completion with native `<progress>` values, not decorative width bars blocked by CSP.
- Place Script Status Catalog before Data Structure.
- Add Layer and Status columns to Data Structure.
- Use consistent font size by hierarchy:
  - Body: 15px.
  - Section heading: 20px.
  - Metric number: 34px.
  - Status badge: 12px.
- Avoid global all-caps styling, excessive bold text, and negative letter spacing.
- Dark monitoring UIs should use black or near-black page background, low-contrast panels, and restrained status color.
