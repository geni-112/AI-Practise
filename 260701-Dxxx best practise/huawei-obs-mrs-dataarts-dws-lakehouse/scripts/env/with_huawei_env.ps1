param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Exe,

  [Parameter(ValueFromRemainingArguments = $true, Position = 1)]
  [string[]]$ExeArgs
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText([securestring]$Secure) {
  if (-not $Secure) { return $null }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$secretRoot = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata"
$credentialPath = Join-Path $secretRoot "credentials.xml"
$servicePasswordPath = Join-Path $secretRoot "bigdata-service-passwords.xml"
$streamPasswordPath = Join-Path $secretRoot "streaming-service-passwords.xml"

if (-not (Test-Path -LiteralPath $credentialPath)) {
  throw "Missing Huawei credential store: $credentialPath"
}

$cloud = Import-Clixml -LiteralPath $credentialPath
$env:HUAWEICLOUD_ACCESS_KEY = Convert-SecureStringToPlainText $cloud.AccessKey
$env:HUAWEICLOUD_SECRET_KEY = Convert-SecureStringToPlainText $cloud.SecretKey
$env:HUAWEICLOUD_REGION = if ($cloud.Region) { $cloud.Region } elseif ($env:HUAWEICLOUD_REGION) { $env:HUAWEICLOUD_REGION } else { "la-south-2" }
$env:HUAWEICLOUD_PROJECT_ID = if ($cloud.ProjectId) { $cloud.ProjectId } elseif ($env:HUAWEICLOUD_PROJECT_ID) { $env:HUAWEICLOUD_PROJECT_ID } else { "09d63c269e80f5e32f4ec00754ed462d" }

if (Test-Path -LiteralPath $servicePasswordPath) {
  $svc = Import-Clixml -LiteralPath $servicePasswordPath
  if (-not $env:DWS_PASSWORD -and $svc.DwsAdminPassword) {
    $env:DWS_PASSWORD = Convert-SecureStringToPlainText $svc.DwsAdminPassword
  }
  if (-not $env:MRS_PASSWORD -and $svc.MrsAdminPassword) {
    $env:MRS_PASSWORD = Convert-SecureStringToPlainText $svc.MrsAdminPassword
  }
}

if (-not $env:DWS_PASSWORD -and $cloud.DwsAdminPassword) {
  $env:DWS_PASSWORD = Convert-SecureStringToPlainText $cloud.DwsAdminPassword
}

function New-LocalPassword {
  $lower = "abcdefghijkmnopqrstuvwxyz"
  $upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
  $digits = "23456789"
  $special = "!@#%*_+-"
  $all = ($lower + $upper + $digits + $special).ToCharArray()
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  function Pick([string]$chars) {
    $bytes = New-Object byte[] 4
    $rng.GetBytes($bytes)
    $idx = [BitConverter]::ToUInt32($bytes, 0) % $chars.Length
    $chars[$idx]
  }
  $chars = @(
    Pick $lower
    Pick $upper
    Pick $digits
    Pick $special
  )
  for ($i = $chars.Count; $i -lt 22; $i++) {
    $chars += Pick ($lower + $upper + $digits + $special)
  }
  -join ($chars | Sort-Object { Get-Random })
}

if (-not (Test-Path -LiteralPath $streamPasswordPath)) {
  $streamSecrets = [pscustomobject]@{
    RdsAdminUser = "root"
    RdsAdminPassword = ConvertTo-SecureString (New-LocalPassword) -AsPlainText -Force
    KafkaUser = "dockone"
    KafkaPassword = ConvertTo-SecureString (New-LocalPassword) -AsPlainText -Force
    CreatedAt = (Get-Date).ToString("o")
  }
  $streamSecrets | Export-Clixml -LiteralPath $streamPasswordPath
}

$stream = Import-Clixml -LiteralPath $streamPasswordPath
$env:RDS_PGUSER = if ($env:RDS_PGUSER) { $env:RDS_PGUSER } else { $stream.RdsAdminUser }
$env:RDS_PGPASSWORD = if ($env:RDS_PGPASSWORD) { $env:RDS_PGPASSWORD } else { Convert-SecureStringToPlainText $stream.RdsAdminPassword }
$env:RDS_PGDATABASE = if ($env:RDS_PGDATABASE) { $env:RDS_PGDATABASE } else { "postgres" }
$env:RDS_PGPORT = if ($env:RDS_PGPORT) { $env:RDS_PGPORT } else { "5432" }
$env:DMS_KAFKA_USERNAME = if ($env:DMS_KAFKA_USERNAME) { $env:DMS_KAFKA_USERNAME } else { $stream.KafkaUser }
$env:DMS_KAFKA_PASSWORD = if ($env:DMS_KAFKA_PASSWORD) { $env:DMS_KAFKA_PASSWORD } else { Convert-SecureStringToPlainText $stream.KafkaPassword }
$env:DMS_KAFKA_TOPIC = if ($env:DMS_KAFKA_TOPIC) { $env:DMS_KAFKA_TOPIC } else { "dockone.billing.contracts" }

$env:DEPLOYMENT_OBS_BUCKET = if ($env:DEPLOYMENT_OBS_BUCKET) { $env:DEPLOYMENT_OBS_BUCKET } else { "hwstaff-retail-lakehouse-09d63c-20260622" }
$env:DEPLOYMENT_MRS_CLUSTER_ID = if ($env:DEPLOYMENT_MRS_CLUSTER_ID) { $env:DEPLOYMENT_MRS_CLUSTER_ID } else { "2a45044c-7506-4b96-9993-70d8a8397ed5" }
$env:DATAARTS_WORKSPACE_ID = if ($env:DATAARTS_WORKSPACE_ID) { $env:DATAARTS_WORKSPACE_ID } else { "c4fc507387fa4d2983d569c490525f86" }
$env:DWS_HOST = if ($env:DWS_HOST) { $env:DWS_HOST } else { "182.160.26.143" }
$env:DWS_PORT = if ($env:DWS_PORT) { $env:DWS_PORT } else { "8000" }
$env:DWS_DATABASE = if ($env:DWS_DATABASE) { $env:DWS_DATABASE } else { "gaussdb" }
$env:DWS_USER = if ($env:DWS_USER) { $env:DWS_USER } else { "dbaadmin" }

& $Exe @ExeArgs
exit $LASTEXITCODE
