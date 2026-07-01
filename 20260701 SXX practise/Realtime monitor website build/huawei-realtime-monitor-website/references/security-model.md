# Security Model

## Credentials
- Prefer AK/SK validated by `validate_huawei_aksk.py`.
- Store local reusable credentials only with `SatCredentialStore.ps1`, which uses Windows DPAPI via PowerShell CLIXML.
- Never commit credential profile XML, `.env`, shell history, screenshots containing keys, or generated logs with secrets.
- Password-based prompts are legacy fallback. Use them only when AK/SK is unavailable and the user explicitly authorizes it.

## Repository Hygiene
Before committing:
```powershell
rg -n "AKIA|HUAWEICLOUD_SECRET_KEY|HUAWEICLOUD_ACCESS_KEY|password|secret|securitytoken|X-Auth-Token|BEGIN PRIVATE KEY" .
```
Expected matches should be variable names, documentation warnings, or code that reads environment variables, not real values.

Do not commit:
- `monitor/data/inventory.json` from a live cloud account unless it is sanitized.
- `exports/huawei_inventory_*.json` raw snapshots.
- Browser screenshots containing secrets.
- `%LOCALAPPDATA%\Codex\huawei-cloud-*\credential-profile.xml`.

## Public Website
- Do not expose MRS, RDS, DWS, DataArts, SSH, or database ports publicly.
- Expose only web ingress on TCP/80 and TCP/443.
- Use Caddy or another HTTPS reverse proxy for demos.
- Avoid bare IP URLs in customer-facing handoff. Use a real domain; `sslip.io` is acceptable only for temporary POCs.
- Set response headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a restrictive CSP.

## Paid Resource Control
- Use pay-per-use ECS/EIP for POC unless instructed otherwise.
- Verify a replacement endpoint is healthy before deleting the previous endpoint.
- Delete superseded web ECS instances, EIPs, and security groups after migration.
- Keep cleanup operations explicit and scoped to monitor-created resources.
