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
   - `python scripts/analyze_bigdata_assets.py`
   - Check `monitor/data/status.json`.
5. Build the static site:
   - `python scripts/build_static_site.py --zip`
6. Publish the OBS source copy:
   - `python scripts/deploy_obs_static_site.py --region <region> --bucket <bucket>`
7. Deploy the secure endpoint:
   - `python scripts/deploy_ecs_monitor_site.py --region <region> --project-id $env:HUAWEICLOUD_PROJECT_ID --name <monitor-name>`
8. Verify:
   - Fetch `<site-url>/`
   - Fetch `<site-url>/data/status.json`
   - Confirm resource count, generated timestamp, HTTPS certificate, and browser console logs.
9. Clean up superseded web endpoints only after the replacement HTTPS URL works.
10. Produce evidence:
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

## Common Commands
```powershell
. .\scripts\Load-HuaweiCredentialProfile.ps1
python scripts\validate_huawei_aksk.py
python scripts\huawei_inventory.py --region la-north-2 --project-id $env:HUAWEICLOUD_PROJECT_ID
python scripts\analyze_bigdata_assets.py
python scripts\build_static_site.py --zip
python scripts\deploy_obs_static_site.py --region la-north-2 --bucket <bucket>
python scripts\deploy_ecs_monitor_site.py --region la-north-2 --project-id $env:HUAWEICLOUD_PROJECT_ID --name <name>
python scripts\aggregate_monitor_evidence.py --site-url https://<domain>/
```

## Frontend Notes
- Keep the first screen the operational monitor, not a landing page.
- Use 5-second refresh through `setInterval`.
- Use consistent font size by hierarchy:
  - Body: 15px.
  - Section heading: 20px.
  - Metric number: 34px.
  - Status badge: 12px.
- Avoid global all-caps styling, excessive bold text, and negative letter spacing.
- Dark monitoring UIs should use black or near-black page background, low-contrast panels, and restrained status color.
