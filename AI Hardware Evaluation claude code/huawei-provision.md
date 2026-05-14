# /huawei-provision — Provision fresh Huawei Cloud environment from zero

Creates all cloud infrastructure from scratch: OBS bucket → ECS server → VPC/Subnet/SG/EIP.
Use this only for a completely new deployment or after deleting the existing environment.

## Prerequisites
- Windows machine with PowerShell 5.1+
- Huawei Cloud account with la-south-2 region enabled
- AK/SK from IAM → My Credentials → Access Keys
- Project root: `C:\Users\Matebook\huawei-ai-hardware-site`

## Step 1 — Populate credentials file

Check if `.local/credentials.ps1` exists and has all required fields:

```powershell
Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\.local\credentials.ps1"
```

Required fields:
```powershell
$HW_DOMAIN  = "your-account-domain-name"   # Huawei Cloud account domain name
$HW_AK      = "your-access-key"            # IAM → My Credentials → Access Keys
$HW_SK      = "your-secret-key"
$HW_REGION  = "la-south-2"
$HW_BUCKET  = "ai-hw-site-9347"            # Must be globally unique
$HW_IAMPASS = "your-iam-account-password"  # Huawei Cloud console login password
$HW_ECSPASS = "Gogogo.0"                   # Root password for new ECS server
```

If any field is missing or wrong, edit the file before continuing.

## Step 2 — Upload site files to OBS

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -ExecutionPolicy Bypass -File deploy-to-obs.ps1
```

This opens a GUI dialog pre-filled from credentials.ps1. Click "Deploy".

Expected: bucket created with public-read ACL, all 4 files uploaded (index.html, styles.css, dashboard.js, data/ai-hardware-config.json).

Verify OBS is working:
```powershell
$url = "https://ai-hw-site-9347.obs.la-south-2.myhuaweicloud.com/index.html"
(Invoke-WebRequest $url -UseBasicParsing).StatusCode   # Should be 200
```

## Step 3 — Provision ECS

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -ExecutionPolicy Bypass -File provision-ecs.ps1
```

If credentials file has HW_DOMAIN + HW_IAMPASS + HW_ECSPASS, the GUI dialog is skipped automatically.

The script creates in order:
1. VPC `ai-hw-vpc` (192.168.0.0/16) — reuses if exists
2. Subnet `ai-hw-subnet` (192.168.1.0/24) — reuses if exists
3. Security Group `ai-hw-sg` (ports 22/80/443 open) — reuses if exists
4. Queries IMS images — filters out GPU/CUDA/ML images
5. Selects flavor (prefers s6.small.1, s6.medium.2, etc.)
6. Creates ECS with cloud-init (pulls files from OBS on boot)
7. Creates EIP and binds to ECS port

Expected time: ~5 minutes. Final output:
```
======================================================
  Provisioning complete!
  Public URL: http://110.238.65.209
  Server ID : 34cabb17-...
======================================================
```

## Step 4 — Save ECS details to credentials file

After provisioning, manually update `.local/credentials.ps1` with:
```powershell
$HW_PROJECT = "..."    # printed during IAM token step
$HW_ECS_ID  = "..."    # Server ID from output
$HW_ECS_EIP = "..."    # Public IP from output
$HW_ECS_URL = "http://..."
```

Also add the IAM User ID (needed for reinstallos API) — get it with:
```powershell
# Run after getting a token; look in the token response user.id field
# Current known value: 09d62df15000f46e1f86c007f5898044
```

## Step 5 — Wait and verify

Cloud-init runs on first boot (~2 min after ECS shows ACTIVE):
```powershell
$r = Invoke-WebRequest "http://{ECS_EIP}/" -UseBasicParsing -TimeoutSec 20
Write-Host "HTTP $($r.StatusCode)"
```

## Known provisioning issues

| Issue | Fix |
|-------|-----|
| "router name has exist" | Script now reuses existing VPC by name — run again |
| "No images found" | IMS query uses unscoped token; check image filter regex |
| GPU image selected → flavor mismatch | Filter: `-notmatch "Tesla\|CUDA\|GPU\|nvidia\|MindSpore\|PyTorch\|TensorFlow\|HPC"` |
| IAM "Project not found" | Script auto-discovers project via `/v3/projects` list |
| EIP already exists at old address | Old EIP still billable — delete from console first |

## After re-provisioning (ECS deleted and recreated)

The EIP will be DIFFERENT. Update credentials.ps1:
- `$HW_ECS_ID` → new server ID
- `$HW_ECS_EIP` → new IP
- `$HW_ECS_URL` → new URL

Then update the RUNBOOK.md with new values.
