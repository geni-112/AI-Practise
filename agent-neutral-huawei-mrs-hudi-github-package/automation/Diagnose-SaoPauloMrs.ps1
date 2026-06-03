param(
  [string]$Bucket = "docktest-sa-brazil-1"
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$DemoRoot = Join-Path $PackageRoot "demo"
. (Join-Path $PSScriptRoot "Set-AgentHuaweiAuth.ps1") `
  -Region "sa-brazil-1" `
  -ProjectName "sa-brazil-1" `
  -Bucket $Bucket `
  -DemoRoot $DemoRoot

$py = @'
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkmrs.v2 import MrsClient, ShowMrsFlavorsRequest, ShowMrsVersionListRequest
from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion
import os, json, requests

region = "sa-brazil-1"
creds = BasicCredentials(
    os.environ["HUAWEICLOUD_ACCESS_KEY"],
    os.environ["HUAWEICLOUD_SECRET_KEY"],
    os.environ["HUAWEICLOUD_PROJECT_ID"],
).with_security_token(os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"))
client = MrsClient.new_builder().with_credentials(creds).with_region(MrsRegion.value_of(region)).build()
print("MRS_VERSIONS", json.dumps(client.show_mrs_version_list(ShowMrsVersionListRequest()).to_json_object(), ensure_ascii=False))
for az in ["sa-brazil-1a", "sa-brazil-1b", "sa-brazil-1c"]:
    try:
        print("MRS_FLAVORS", az, json.dumps(client.show_mrs_flavors(ShowMrsFlavorsRequest(version_name="MRS 3.5.0-LTS", availability_zone=az)).to_json_object(), ensure_ascii=False))
    except Exception as exc:
        print("MRS_FLAVOR_ERROR", az, type(exc).__name__, str(exc)[:1000])

token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN")
print("NOTE", "ECS quota should be checked by the operator if MRS creation returns memory quota errors. The tested account had 262144 MB RAM quota, below the 5-node MRS minimum in sa-brazil-1a.")
'@

$py | python -

