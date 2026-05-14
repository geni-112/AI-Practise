# /huawei-deploy — Deploy site changes to Huawei Cloud

Deploy updated site files (HTML/CSS/JS/JSON) to OBS and push to the live ECS server.
The project root is `C:\Users\Matebook\huawei-ai-hardware-site`.

## When to use
- After editing `data/ai-hardware-config.json` (models, quantizations, hardware)
- After editing `dashboard.js`, `index.html`, or `styles.css`
- After any content change that needs to go live at http://110.238.65.209

## Steps to execute

### Step 1 — If `ai-hardware-config.json` was changed, sync INLINE_CONFIG first

Run this PowerShell script to update the hardcoded fallback inside `dashboard.js`:

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File fix-inline-config.ps1
```

Expected output:
- `Compact JSON: ~11587 chars`
- `All sanity checks passed.`
- `INLINE_CONFIG JSON length in new file: 11587 (expected 11587)`

If the script reports `ERROR: orphan content still present`, the INLINE_CONFIG section in `dashboard.js` is corrupted — run `/huawei-debug` instead.

### Step 2 — Upload to OBS and reinstall ECS

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File deploy-and-reinstall.ps1
```

Expected output (takes ~3 minutes total):
```
=== [1/3] Uploading files to OBS ===
  OBS PUT dashboard.js -> HTTP 200
  OBS PUT data/ai-hardware-config.json -> HTTP 200
=== [2/3] Getting IAM token ===
  Token: OK
=== [3/3] Reinstalling ECS ===
  Stopping server... Status: SHUTOFF
  Reinstall job: ff8080...
  [45s] SUCCESS
  Reinstall done!
```

### Step 3 — Verify live site

```powershell
$r = Invoke-WebRequest "http://110.238.65.209/" -UseBasicParsing -TimeoutSec 20
Write-Host "HTTP $($r.StatusCode) — length $($r.Content.Length)"

$cfg = Invoke-WebRequest "http://110.238.65.209/data/ai-hardware-config.json" -UseBasicParsing
$obj = $cfg.Content | ConvertFrom-Json
Write-Host "Models: $($obj.models.Count) — version $($obj.metadata.version)"
```

Expected: HTTP 200, 7 models, version 1.1.0+.

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `OBS SignatureDoesNotMatch` | Clock skew or wrong SK | Check `.local/credentials.ps1` HW_SK value |
| `Ecs.0100: not shutdown` | Server already SHUTOFF from prior run | Script handles this; retry once |
| `401 Unauthorized` on IAM | Wrong HW_IAMPASS or credentials file overwritten | Restore HW_IAMPASS = "Gogogo.0" in `.local/credentials.ps1` |
| Reinstall job stuck RUNNING > 5 min | API timeout | Run `/huawei-recover` |
| Site shows old content after deploy | Browser cache | Hard-refresh (Ctrl+Shift+R) |

## What deploy-and-reinstall.ps1 does internally
1. OBS-PUT dashboard.js and data/ai-hardware-config.json (HMAC-SHA1 signed)
2. Gets IAM unscoped token → scoped token for project `09d63c269e80f5e32f4ec00754ed462d`
3. Stops ECS `34cabb17-22bc-41c0-a611-ef8e465129b7` (SOFT stop)
4. Calls `POST /v1/{project}/cloudservers/{id}/reinstallos` with new cloud-init
5. Cloud-init pulls all 4 files from OBS into `/var/www/html/`
6. nginx restarted automatically
