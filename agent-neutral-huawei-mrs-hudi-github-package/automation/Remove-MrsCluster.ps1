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

$env:DELETE_CLUSTER_ID = $ClusterId
$py = @'
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkmrs.v1 import MrsClient, DeleteClusterRequest
from huaweicloudsdkmrs.v1.region.mrs_region import MrsRegion
import os, json

region = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
creds = BasicCredentials(
    os.environ["HUAWEICLOUD_ACCESS_KEY"],
    os.environ["HUAWEICLOUD_SECRET_KEY"],
    os.environ["HUAWEICLOUD_PROJECT_ID"],
).with_security_token(os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"))
client = MrsClient.new_builder().with_credentials(creds).with_region(MrsRegion.value_of(region)).build()
resp = client.delete_cluster(DeleteClusterRequest(cluster_id=os.environ["DELETE_CLUSTER_ID"]))
print(json.dumps(resp.to_json_object(), ensure_ascii=False))
'@

$py | python -

