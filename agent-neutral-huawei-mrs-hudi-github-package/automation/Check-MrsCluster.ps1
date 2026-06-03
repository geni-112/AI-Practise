param(
  [Parameter(Mandatory = $true)]
  [string]$ClusterId,
  [string]$Region = "la-south-2",
  [string]$ProjectName = ""
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$DemoRoot = Join-Path $PackageRoot "demo"
. (Join-Path $PSScriptRoot "Set-AgentHuaweiAuth.ps1") -Region $Region -ProjectName $ProjectName -DemoRoot $DemoRoot

$env:CHECK_CLUSTER_ID = $ClusterId
$py = @'
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkmrs.v1 import MrsClient as MrsClientV1, ShowClusterDetailsRequest
from huaweicloudsdkmrs.v2 import MrsClient as MrsClientV2, ShowJobExeListNewRequest
from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion
import os, json

region = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
cluster_id = os.environ["CHECK_CLUSTER_ID"]
creds = BasicCredentials(
    os.environ["HUAWEICLOUD_ACCESS_KEY"],
    os.environ["HUAWEICLOUD_SECRET_KEY"],
    os.environ["HUAWEICLOUD_PROJECT_ID"],
).with_security_token(os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"))
client_v1 = MrsClientV1.new_builder().with_credentials(creds).with_region(MrsRegion.value_of(region)).build()
client_v2 = MrsClientV2.new_builder().with_credentials(creds).with_region(MrsRegion.value_of(region)).build()
data = client_v1.show_cluster_details(ShowClusterDetailsRequest(cluster_id=cluster_id)).to_json_object()
cluster = data.get("cluster") or data
print("CLUSTER", json.dumps(cluster, ensure_ascii=False)[:4000])
try:
    jobs = client_v2.show_job_exe_list_new(ShowJobExeListNewRequest(cluster_id=cluster_id, limit=20, offset=1)).to_json_object()
    slim = []
    for job in jobs.get("job_list") or []:
        slim.append({k: job.get(k) for k in ["job_id", "job_name", "job_state", "job_result"]})
    print("JOBS", json.dumps(slim, ensure_ascii=False))
except Exception as exc:
    print("JOBS_ERROR", type(exc).__name__, str(exc)[:1000])
'@

$py | python -

