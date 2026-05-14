# /huawei-debug — Diagnose and fix AI Capacity Planner issues

Systematic diagnostic tree for all known failure modes.
Run each check in order — stop at the first failure and apply the fix.

---

## CHECK 1 — Is the site reachable?

```powershell
try {
    $r = Invoke-WebRequest "http://110.238.65.209/" -UseBasicParsing -TimeoutSec 10
    Write-Host "HTTP $($r.StatusCode) — length $($r.Content.Length)"
} catch { Write-Host "FAIL: $_" }
```

| Result | Diagnosis | Fix |
|--------|-----------|-----|
| HTTP 200 | Site is up, problem is JS/data | Continue to CHECK 2 |
| Connection refused / timeout | nginx down or ECS stopped | Run `/huawei-recover` |
| HTTP 502/503 | nginx running but broken | Run `/huawei-recover` |

---

## CHECK 2 — Does dashboard.js load and parse correctly?

```powershell
$r = Invoke-WebRequest "http://110.238.65.209/dashboard.js" -UseBasicParsing -TimeoutSec 10
Write-Host "JS length: $($r.Content.Length)  (expected ~43000-44000)"

# Check for known orphan corruption pattern
if ($r.Content -match '}\s*;\s*public specification') {
    Write-Host "CORRUPTED: orphan JSON content found in dashboard.js"
} else {
    Write-Host "No orphan content — JS structure OK"
}
```

**If "CORRUPTED"**: The INLINE_CONFIG was truncated by a buggy patch.

Fix:
```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File fix-inline-config.ps1
powershell -NonInteractive -ExecutionPolicy Bypass -File deploy-and-reinstall.ps1
```

Root cause: `patch-inline-config.ps1` (deprecated) searched for `;` to find INLINE_CONFIG end, but JSON note fields contain semicolons (e.g., `"64 GB HBM2e; public specification..."`). Always use `fix-inline-config.ps1` instead.

---

## CHECK 3 — Is INLINE_CONFIG complete and valid?

```powershell
$c = (Invoke-WebRequest "http://110.238.65.209/dashboard.js" -UseBasicParsing).Content
$idx = $c.IndexOf("const INLINE_CONFIG = ")
$js  = $idx + 22
$depth=0; $inStr=$false; $escape=$false; $ei=-1
for ($i=$js; $i -lt $c.Length; $i++) {
    $ch=$c[$i]
    if($escape){$escape=$false;continue}; if($ch -eq '\' -and $inStr){$escape=$true;continue}
    if($ch -eq '"'){$inStr=-not $inStr;continue}; if($inStr){continue}
    if($ch -eq '{'){$depth++} elseif($ch -eq '}'){$depth--;if($depth-eq 0){$ei=$i;break}}
}
$jsonStr = $c.Substring($js, $ei - $js + 1)
Write-Host "INLINE_CONFIG length: $($jsonStr.Length)  (expected ~11587)"
try {
    $obj = $jsonStr | ConvertFrom-Json
    Write-Host "INLINE_CONFIG parses OK — $($obj.hardware.Count) hardware, $($obj.models.Count) models"
} catch { Write-Host "INLINE_CONFIG PARSE ERROR: $_" }
```

| Result | Fix |
|--------|-----|
| length ~505, parse error | Run `fix-inline-config.ps1` + `deploy-and-reinstall.ps1` |
| length ~11587, parse OK | INLINE_CONFIG is fine |
| length ~11587 but wrong models | Re-run `fix-inline-config.ps1` (local JSON may have changed) |

---

## CHECK 4 — Does the data JSON file exist on the server?

```powershell
try {
    $cfg = (Invoke-WebRequest "http://110.238.65.209/data/ai-hardware-config.json" -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
    Write-Host "data JSON OK — $($cfg.models.Count) models, version $($cfg.metadata.version)"
} catch { Write-Host "data JSON MISSING or invalid: $_" }
```

If missing (404): The cloud-init script that pulled files from OBS didn't include the data file.

Fix — run a reinstall with the corrected cloud-init (which does include the data file):
```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File deploy-and-reinstall.ps1
```

---

## CHECK 5 — Is OBS serving the latest files?

```powershell
$base = "https://ai-hw-site-9347.obs.la-south-2.myhuaweicloud.com"
@("index.html","styles.css","dashboard.js","data/ai-hardware-config.json") | ForEach-Object {
    try {
        $r = Invoke-WebRequest "$base/$_" -UseBasicParsing -TimeoutSec 10
        Write-Host "OBS $_  HTTP $($r.StatusCode)  $($r.Content.Length) bytes"
    } catch { Write-Host "OBS $_ FAIL: $_" }
}
```

If any file returns 404 or fails: Upload it with `deploy-to-obs.ps1` or `upload-config.ps1`.

---

## CHECK 6 — Are credentials intact?

```powershell
$raw = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\.local\credentials.ps1" -Raw
$fields = @("HW_DOMAIN","HW_AK","HW_SK","HW_REGION","HW_BUCKET","HW_PROJECT","HW_IAMPASS","HW_ECSPASS","HW_ECS_ID","HW_ECS_EIP")
foreach ($f in $fields) {
    $present = $raw -match "(?m)^\`$$f\s*=\s*`"[^`"]+`""
    Write-Host "$(if($present){'OK  '}else{'MISS'}) $f"
}
```

If any field shows `MISS`:

| Missing field | How to restore |
|---------------|----------------|
| `HW_IAMPASS` | Add `$HW_IAMPASS = "Gogogo.0"` (overwritten by `deploy-to-obs.ps1` before BUG-10 fix) |
| `HW_ECSPASS` | Add `$HW_ECSPASS = "Gogogo.0"` |
| `HW_PROJECT` | Add `$HW_PROJECT = "09d63c269e80f5e32f4ec00754ed462d"` |
| `HW_ECS_ID`  | Add `$HW_ECS_ID = "34cabb17-22bc-41c0-a611-ef8e465129b7"` |
| `HW_ECS_EIP` | Add `$HW_ECS_EIP = "110.238.65.209"` |

---

## CHECK 7 — IAM auth test

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$raw = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\.local\credentials.ps1" -Raw
function Get-Cred($k){if($raw -match "(?m)^\`$$k\s*=\s*`"([^`"]*)`""){$Matches[1]}}
$DOMAIN=Get-Cred "HW_DOMAIN"; $PASS=Get-Cred "HW_IAMPASS"
$ub="{`"auth`":{`"identity`":{`"methods`":[`"password`"],`"password`":{`"user`":{`"domain`":{`"name`":`"$DOMAIN`"},`"name`":`"$DOMAIN`",`"password`":`"$PASS`"}}}}}"
try {
    $req=[System.Net.HttpWebRequest]::Create("https://iam.myhuaweicloud.com/v3/auth/tokens")
    $req.Method="POST"; $req.ContentType="application/json;charset=utf-8"; $req.Timeout=30000
    $b=[System.Text.Encoding]::UTF8.GetBytes($ub); $req.ContentLength=$b.Length
    $s=$req.GetRequestStream(); $s.Write($b,0,$b.Length); $s.Close()
    $resp=$req.GetResponse()
    Write-Host "IAM auth OK — token received"
} catch { Write-Host "IAM auth FAILED: $_" }
```

If IAM auth fails with 401:
1. Verify `HW_IAMPASS` is the correct Huawei Cloud console login password
2. Check if account has MFA enabled (not supported by this script)
3. Try logging into console.huaweicloud.com with the same credentials

---

## Decision tree summary

```
Site unreachable?          → /huawei-recover
JS loads but dropdowns empty?
  ├─ Orphan "public specification" in JS?  → fix-inline-config.ps1 + deploy-and-reinstall.ps1
  ├─ INLINE_CONFIG length ~505?            → fix-inline-config.ps1 + deploy-and-reinstall.ps1
  ├─ data/ai-hardware-config.json 404?     → deploy-and-reinstall.ps1
  └─ Credentials missing fields?           → Restore .local/credentials.ps1
IAM 401?                   → Check HW_IAMPASS in credentials.ps1
OBS upload fails?          → Check HW_AK/HW_SK; string-to-sign: PUT\n\nCT\nDate\n/bucket/key
```
