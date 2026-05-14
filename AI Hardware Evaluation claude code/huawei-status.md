# /huawei-status — Check current state of AI Capacity Planner infrastructure

Runs a full health check across OBS, ECS, and the live site in one shot.

---

## Full status check script

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$raw = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\.local\credentials.ps1" -Raw
function Get-Cred($k){if($raw -match "(?m)^\`$$k\s*=\s*`"([^`"]*)`""){$Matches[1]}else{"(missing)"}}

$DOMAIN  = Get-Cred "HW_DOMAIN";  $PROJECT = Get-Cred "HW_PROJECT"
$PASS    = Get-Cred "HW_IAMPASS"; $REGION  = Get-Cred "HW_REGION"
$BUCKET  = Get-Cred "HW_BUCKET";  $SRV     = Get-Cred "HW_ECS_ID"
$EIP     = Get-Cred "HW_ECS_EIP"

Write-Host ""
Write-Host "============================================"
Write-Host " AI Capacity Planner — Status Check"
Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') UTC"
Write-Host "============================================"

# --- SITE HEALTH ---
Write-Host ""
Write-Host "[SITE] http://$EIP"
try {
    $r = Invoke-WebRequest "http://$EIP/" -UseBasicParsing -TimeoutSec 10
    $hasTitle  = $r.Content -match "AI Capacity Planner"
    $hasMatrix = $r.Content -match "allModelsSection"
    Write-Host "  HTTP $($r.StatusCode) — $($r.Content.Length) bytes"
    Write-Host "  Title:  $(if($hasTitle) {'OK'} else {'MISSING'})"
    Write-Host "  Matrix: $(if($hasMatrix){'OK'} else {'MISSING'})"
} catch { Write-Host "  UNREACHABLE: $_" }

try {
    $js = (Invoke-WebRequest "http://$EIP/dashboard.js" -UseBasicParsing -TimeoutSec 10).Content
    $orphan = $js -match '}\s*;\s*public specification'
    Write-Host "  dashboard.js: $($js.Length) bytes  Orphan corruption: $(if($orphan){'YES — run /huawei-debug'}else{'none'})"
} catch { Write-Host "  dashboard.js: MISSING" }

try {
    $cfg = (Invoke-WebRequest "http://$EIP/data/ai-hardware-config.json" -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
    Write-Host "  data JSON: OK — v$($cfg.metadata.version), $($cfg.models.Count) models"
    $cfg.models | ForEach-Object {
        Write-Host "    $($_.id): $($_.quantizations.Count) quants"
    }
} catch { Write-Host "  data JSON: MISSING (404) — ECS cloud-init may not have pulled it" }

# --- OBS HEALTH ---
Write-Host ""
Write-Host "[OBS] $BUCKET.$REGION"
$obsBase = "https://$BUCKET.obs.$REGION.myhuaweicloud.com"
@("index.html","styles.css","dashboard.js","data/ai-hardware-config.json") | ForEach-Object {
    try {
        $or = Invoke-WebRequest "$obsBase/$_" -UseBasicParsing -TimeoutSec 10
        Write-Host "  $($or.StatusCode)  $($or.Content.Length.ToString().PadLeft(7)) bytes  $_"
    } catch { Write-Host "  FAIL  $_" }
}

# --- ECS STATUS via API ---
Write-Host ""
Write-Host "[ECS] $SRV"
function Invoke-Api($m,$url,$body="",$h=@{}) {
    $req=[System.Net.HttpWebRequest]::Create($url); $req.Method=$m
    if($m-ne"GET"){$req.ContentType="application/json;charset=utf-8"}
    $req.Accept="application/json"; $req.Timeout=30000
    foreach($k in $h.Keys){$req.Headers.Add($k,$h[$k])}
    if($body){$b=[System.Text.Encoding]::UTF8.GetBytes($body);$req.ContentLength=$b.Length;$s=$req.GetRequestStream();$s.Write($b,0,$b.Length);$s.Close()}elseif($m-ne"GET"){$req.ContentLength=0}
    try{$resp=$req.GetResponse();$tok=$resp.Headers["X-Subject-Token"];$rd=New-Object System.IO.StreamReader($resp.GetResponseStream(),[System.Text.Encoding]::UTF8);$txt=$rd.ReadToEnd();$rd.Close();return @{Token=$tok;Body=($txt|ConvertFrom-Json)}}
    catch [System.Net.WebException]{$er=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());throw $er.ReadToEnd()}
}
try {
    $ub="{`"auth`":{`"identity`":{`"methods`":[`"password`"],`"password`":{`"user`":{`"domain`":{`"name`":`"$DOMAIN`"},`"name`":`"$DOMAIN`",`"password`":`"$PASS`"}}}}}"
    $ut=(Invoke-Api POST "https://iam.myhuaweicloud.com/v3/auth/tokens" $ub).Token
    $sb=@{auth=@{identity=@{methods=@("token");token=@{id=$ut}};scope=@{project=@{id=$PROJECT}}}}|ConvertTo-Json -Depth 10 -Compress
    $TOKEN=(Invoke-Api POST "https://iam.myhuaweicloud.com/v3/auth/tokens" $sb).Token
    $hdrs=@{"X-Auth-Token"=$TOKEN}
    $s=(Invoke-Api GET "https://ecs.$REGION.myhuaweicloud.com/v1/$PROJECT/cloudservers/$SRV" "" $hdrs).Body.server
    $launched = $s.'OS-SRV-USG:launched_at'
    Write-Host "  IAM: OK"
    Write-Host "  Status:  $($s.status)"
    Write-Host "  Flavor:  $($s.flavor.id)"
    Write-Host "  EIP:     $EIP"
    Write-Host "  Launched: $launched"
} catch { Write-Host "  IAM or ECS API: FAIL — $_" }

# --- CREDENTIALS CHECK ---
Write-Host ""
Write-Host "[CREDENTIALS] .local/credentials.ps1"
@("HW_DOMAIN","HW_AK","HW_SK","HW_REGION","HW_BUCKET","HW_PROJECT","HW_IAMPASS","HW_ECSPASS","HW_ECS_ID","HW_ECS_EIP") | ForEach-Object {
    $ok = $raw -match "(?m)^\`$$_\s*=\s*`"[^`"]+`""
    Write-Host "  $(if($ok){'OK  '}else{'MISS'}) $_"
}

Write-Host ""
Write-Host "============================================"
Write-Host " Status check complete"
Write-Host "============================================"
```

## What each section tells you

| Section | Green state | Action if red |
|---------|-------------|---------------|
| SITE | HTTP 200, both OK, no orphan | None |
| OBS | All 4 files HTTP 200 | Run `deploy-to-obs.ps1` |
| ECS | Status: ACTIVE | Run `/huawei-recover` |
| CREDENTIALS | All 10 fields OK | Edit `.local/credentials.ps1` |

## Quick one-liner: just check if site is up

```powershell
(Invoke-WebRequest "http://110.238.65.209/" -UseBasicParsing -TimeoutSec 5).StatusCode
```

Expected: `200`
