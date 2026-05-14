# /huawei-recover — Recover broken ECS server

Restores the live site to a working state by triggering an OS reinstall on the ECS,
which re-runs cloud-init and pulls fresh files from OBS.

Use this when:
- http://110.238.65.209 returns connection refused / timeout / 5xx
- Dropdowns are empty (JavaScript broken — see `/huawei-debug` first)
- nginx has crashed or files are corrupted on the server
- ECS is stuck in an error state

## Quick recovery (most cases)

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File deploy-and-reinstall.ps1
```

This takes ~3 minutes. It will:
1. Upload latest files to OBS (ensures OBS is current)
2. Stop ECS gracefully (SOFT stop)
3. Reinstall OS — cloud-init pulls fresh files from OBS into `/var/www/html/`
4. nginx starts automatically

## Manual recovery steps (if deploy-and-reinstall.ps1 fails)

### Step 1 — Get IAM token

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$raw = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\.local\credentials.ps1" -Raw
function Get-Cred($k) { if ($raw -match "(?m)^\`$$k\s*=\s*`"([^`"]*)`"") {$Matches[1]} }

$DOMAIN  = Get-Cred "HW_DOMAIN";  $PROJECT = Get-Cred "HW_PROJECT"
$PASS    = Get-Cred "HW_IAMPASS"; $REGION  = Get-Cred "HW_REGION"
$SRV     = Get-Cred "HW_ECS_ID";  $ECS_PASS= Get-Cred "HW_ECSPASS"

function Invoke-Api($m,$url,$body="",$h=@{}) {
    $req=[System.Net.HttpWebRequest]::Create($url); $req.Method=$m
    if($m-ne"GET"){$req.ContentType="application/json;charset=utf-8"}
    $req.Accept="application/json"; $req.Timeout=60000
    foreach($k in $h.Keys){$req.Headers.Add($k,$h[$k])}
    if($body){$b=[System.Text.Encoding]::UTF8.GetBytes($body);$req.ContentLength=$b.Length;$s=$req.GetRequestStream();$s.Write($b,0,$b.Length);$s.Close()}elseif($m-ne"GET"){$req.ContentLength=0}
    $resp=$req.GetResponse(); $tok=$resp.Headers["X-Subject-Token"]
    $rd=New-Object System.IO.StreamReader($resp.GetResponseStream(),[System.Text.Encoding]::UTF8)
    $txt=$rd.ReadToEnd(); $rd.Close(); return @{Token=$tok;Body=($txt|ConvertFrom-Json)}
}

$ub="{`"auth`":{`"identity`":{`"methods`":[`"password`"],`"password`":{`"user`":{`"domain`":{`"name`":`"$DOMAIN`"},`"name`":`"$DOMAIN`",`"password`":`"$PASS`"}}}}}"
$ut=(Invoke-Api POST "https://iam.myhuaweicloud.com/v3/auth/tokens" $ub).Token
$sb=@{auth=@{identity=@{methods=@("token");token=@{id=$ut}};scope=@{project=@{id=$PROJECT}}}}|ConvertTo-Json -Depth 10 -Compress
$TOKEN=(Invoke-Api POST "https://iam.myhuaweicloud.com/v3/auth/tokens" $sb).Token
$hdrs=@{"X-Auth-Token"=$TOKEN}
Write-Host "Token: OK"
```

### Step 2 — Check server status

```powershell
$ECS_BASE = "https://ecs.$REGION.myhuaweicloud.com"
$s = (Invoke-Api GET "$ECS_BASE/v1/$PROJECT/cloudservers/$SRV" "" $hdrs).Body.server
Write-Host "Status: $($s.status)  Name: $($s.name)"
```

| Status | Next action |
|--------|-------------|
| `ACTIVE` | Stop it first (Step 3), then reinstall |
| `SHUTOFF` | Go directly to Step 4 (reinstall) |
| `ERROR` | Try stop first; if fails, delete and re-provision |
| `REBOOT` | Wait 2 min, recheck |

### Step 3 — Stop server (if ACTIVE)

```powershell
Invoke-Api POST "$ECS_BASE/v1/$PROJECT/cloudservers/action" "{`"os-stop`":{`"servers`":[{`"id`":`"$SRV`"}],`"type`":`"SOFT`"}}" $hdrs | Out-Null
# Wait for SHUTOFF
for($i=0;$i-lt18;$i++){
    Start-Sleep 10
    $st=(Invoke-Api GET "$ECS_BASE/v1/$PROJECT/cloudservers/$SRV" "" $hdrs).Body.server.status
    Write-Host "  $st"; if($st-eq"SHUTOFF"){break}
}
```

### Step 4 — Reinstall OS

```powershell
$BUCKET = Get-Cred "HW_BUCKET"
$OBS = "https://$BUCKET.obs.$REGION.myhuaweicloud.com"
$init = "#!/bin/bash`napt-get update -y`napt-get install -y nginx curl`nmkdir -p /var/www/html/data`nB=`"$OBS`"`ncurl -sf -o /var/www/html/index.html `"`$B/index.html`"`ncurl -sf -o /var/www/html/styles.css `"`$B/styles.css`"`ncurl -sf -o /var/www/html/dashboard.js `"`$B/dashboard.js`"`ncurl -sf -o /var/www/html/data/ai-hardware-config.json `"`$B/data/ai-hardware-config.json`"`nchown -R www-data:www-data /var/www/html`nsystemctl enable nginx && systemctl restart nginx"
$UD=[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($init))

$rb=@{"os-reinstall"=@{adminpass=$ECS_PASS;userid="09d62df15000f46e1f86c007f5898044";metadata=@{user_data=$UD}}}|ConvertTo-Json -Depth 10 -Compress
$jr=(Invoke-Api POST "$ECS_BASE/v1/$PROJECT/cloudservers/$SRV/reinstallos" $rb $hdrs).Body
$JOB=[string]$jr.job_id
Write-Host "Job: $JOB"

# Poll
for($i=0;$i-lt60;$i++){
    Start-Sleep 15
    $job=(Invoke-Api GET "$ECS_BASE/v1/$PROJECT/jobs/$JOB" "" $hdrs).Body
    Write-Host "  [$($i*15+15)s] $($job.status)"
    if($job.status-eq"SUCCESS"){Write-Host "Done!"; break}
    if($job.status-eq"FAIL"){Write-Host "FAIL: $($job.fail_reason)"; break}
}
```

### Step 5 — Verify recovery

```powershell
Start-Sleep 90   # Wait for cloud-init to finish
$r = Invoke-WebRequest "http://$(Get-Cred 'HW_ECS_EIP')/" -UseBasicParsing
Write-Host "HTTP $($r.StatusCode) — site is $(if($r.Content -match 'AI Capacity'){'UP'}else{'responding but unexpected content'})"
```

## If reinstall keeps failing

```
1. Check credentials.ps1 has HW_ECSPASS and HW_PROJECT populated
2. Verify IAM User ID is still 09d62df15000f46e1f86c007f5898044
   (get fresh: GET https://iam.myhuaweicloud.com/v3/auth/tokens with X-Subject-Token header)
3. If ECS is in ERROR state: delete via console → run /huawei-provision
4. If OBS files are missing: run deploy-to-obs.ps1 first
```
